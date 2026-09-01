"""
Builds the full chart payload for one company: OHLCV bars for the requested
timeframe (Month/Week/Day/30-Min bar aggregation) and display period, plus
whichever indicator overlays were requested (including the strategy engine's
trend line for that timeframe and, when requested, a Fixed Range Volume
Profile), computed with user-selected lookback settings.
"""

import logging
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd

import config
import data_provider
import indicators as ind
import trendline_engine
import volume_profile

log = logging.getLogger("sp500_scanner")


def _line_series(line, display_positions):
    """Projects a trendline_engine.TrendLine's ray across the displayed bar
    positions (positional indices within the SAME dataframe the line was
    built from -- see evaluate_timeframe's docstring)."""
    if line is None:
        return None
    return [round(float(line.value_at(int(p))), 4) for p in display_positions]


def get_chart_payload(ticker, period_key=None, bb_window=None, rsi_period=None,
                       macd_preset="standard", volume_lookback=None, source_hint=None,
                       timeframe="day", frvp_windows=None):
    period_key = period_key or config.DEFAULT_CHART_PERIOD
    timeframe = timeframe or "day"

    bb_window = bb_window or config.BB_WINDOW
    rsi_period = rsi_period or config.RSI_PERIOD
    volume_lookback = volume_lookback or config.VOLUME_LOOKBACK
    macd_fast, macd_slow, macd_signal = config.MACD_PRESETS.get(macd_preset, config.MACD_PRESETS["standard"])

    intraday_df = None  # fetched lazily; reused for both the 30-Min timeframe and FRVP

    if timeframe == "30min":
        df, source = data_provider.get_intraday_history(
            ticker, minutes=config.FRVP_INTRADAY_MINUTES, days=config.MANUAL_REFRESH_INTRADAY_DAYS,
            source_hint=source_hint,
        )
        intraday_df = df
        display_days = None   # trimmed by bar count below -- intraday bars only span market hours
        swing_k = config.SWING_K["30min"]
    elif timeframe in ("month", "week"):
        daily_df, source = data_provider.get_single_ticker_history(
            ticker, config.TREND_HISTORY_DAYS, source_hint=source_hint)
        if daily_df is None or daily_df.empty:
            df = daily_df
        else:
            df = trendline_engine.resample_ohlcv(daily_df, "ME" if timeframe == "month" else "W-FRI")
        display_days = 1825 if timeframe == "month" else 730   # Month -> 5yr, Week -> 2yr
        swing_k = config.SWING_K[timeframe]
    else:  # "day"
        display_days = config.CHART_PERIODS.get(period_key, config.CHART_PERIODS[config.DEFAULT_CHART_PERIOD])
        # Fetch extra history beyond the display window so indicators computed
        # for the FIRST displayed day still have a full lookback behind them.
        # Includes SMA_CROSSOVER_SLOW (200d) so the crossover has enough
        # history even when the display period itself is short (e.g. "1M").
        buffer_days = max(bb_window, macd_slow, rsi_period, volume_lookback, config.SMA_CROSSOVER_SLOW) * 2 + 30
        df, source = data_provider.get_single_ticker_history(ticker, display_days + buffer_days, source_hint=source_hint)
        swing_k = config.SWING_K["day"]

    if df is None or df.empty or "Close" not in df.columns:
        return None

    df = df.dropna(subset=["Close"])
    closes = df["Close"]
    volumes = df["Volume"] if "Volume" in df.columns else pd.Series(0, index=df.index)

    upper, lower, mean = ind.compute_bollinger(closes, window=bb_window)
    rsi_series = ind.compute_rsi(closes, period=rsi_period)
    macd_line, signal_line, hist = ind.compute_macd(closes, fast=macd_fast, slow=macd_slow, signal=macd_signal)
    vol_avg = volumes.rolling(volume_lookback).mean()
    sma_fast, sma_slow = ind.compute_sma_crossover(closes)
    if "High" in df.columns and "Low" in df.columns:
        atr_series = ind.compute_atr(df["High"], df["Low"], closes, period=config.ATR_PERIOD)
    else:
        atr_series = pd.Series(float("nan"), index=df.index)

    # Trim to the requested DISPLAY window now that indicators are computed
    # over the full buffered history. Use an actual calendar-date cutoff for
    # Day/Week/Month (NOT a row-count slice, since trading days are ~5/7 of
    # calendar days); 30-Min bars only span market hours, so they're trimmed
    # by bar count instead.
    if display_days is not None:
        cutoff_date = df.index[-1] - pd.Timedelta(days=display_days)
        display_mask = df.index >= cutoff_date
    else:
        bars_per_session = max(1, int(390 / config.FRVP_INTRADAY_MINUTES))  # ~6.5h regular session
        keep = min(len(df), bars_per_session * 10)
        display_mask = df.index >= df.index[-keep]

    display_positions = np.where(display_mask)[0]

    def _trim(series):
        return series[display_mask]

    if timeframe == "30min":
        dates = [int(d.timestamp()) for d in df.index[display_mask]]
    else:
        dates = [d.strftime("%Y-%m-%d") for d in df.index[display_mask]]

    def _clean_list(series):
        return [None if pd.isna(v) else round(float(v), 4) for v in _trim(series)]

    # Fit over the DISPLAYED closes only (not the full buffer) so the line
    # reflects the trend over whatever period is currently selected, and
    # refits whenever the period changes -- already aligned 1:1 with `dates`.
    trend_series = ind.compute_trendline(_trim(closes))
    trend_values = [None if pd.isna(v) else round(float(v), 4) for v in trend_series]

    # The swing-hull trend line FOR THIS DISPLAYED TIMEFRAME specifically --
    # not the cross-timeframe Month->Week->Day decision cascade (that's a
    # separate concept computed by strategy_engine.py for the Movers tab /
    # manual refresh). This just draws what the line looks like on the bars
    # currently on screen.
    upward_line, downward_line = trendline_engine.evaluate_timeframe(df, swing_k)
    strategy_trend_lines = {
        "upward": _line_series(upward_line, display_positions),
        "downward": _line_series(downward_line, display_positions),
    }

    frvp = None
    if frvp_windows:
        if intraday_df is None:
            intraday_df, _ = data_provider.get_intraday_history(
                ticker, minutes=config.FRVP_INTRADAY_MINUTES, days=config.MANUAL_REFRESH_INTRADAY_DAYS,
                source_hint=source,
            )
        try:
            # Approximates "live price" with the most recent close in the
            # currently displayed data -- good enough for a visual chart
            # overlay; the Movers tab's actual POC-proximity check uses a
            # real live quote (see strategy_engine.py).
            reference_price = float(closes.iloc[-1])
            frvp = {}
            for key in frvp_windows:
                n_days = config.FRVP_WINDOWS.get(key)
                if n_days is None:
                    continue
                profile = volume_profile.get_profile_for_window(intraday_df, n_days)
                if profile is None:
                    continue
                poc_price = profile["poc_price"]
                distance_pct = round(abs(reference_price - poc_price) / poc_price * 100, 2) if poc_price else None
                frvp[key] = {
                    "poc_price": poc_price,
                    "distance_pct": distance_pct,
                    "approaching": distance_pct is not None and distance_pct <= config.FRVP_PROXIMITY_PCT * 100,
                    "value_area_high": profile["value_area_high"],
                    "value_area_low": profile["value_area_low"],
                    "bins": profile["bins"],
                }
        except Exception as e:
            log.warning(f"FRVP computation failed for {ticker}: {e}")
            frvp = None

    return {
        "ticker": ticker,
        "source": source,
        "period": period_key,
        "timeframe": timeframe,
        "dates": dates,
        "open": _clean_list(df["Open"]) if "Open" in df.columns else None,
        "high": _clean_list(df["High"]) if "High" in df.columns else None,
        "low": _clean_list(df["Low"]) if "Low" in df.columns else None,
        "close": _clean_list(closes),
        "volume": _clean_list(volumes),
        "bollinger": {
            "window": bb_window,
            "upper": _clean_list(upper),
            "lower": _clean_list(lower),
            "mean": _clean_list(mean),
        },
        "rsi": {
            "period": rsi_period,
            "values": _clean_list(rsi_series),
            "oversold": config.RSI_OVERSOLD,
            "overbought": config.RSI_OVERBOUGHT,
        },
        "macd": {
            "preset": macd_preset,
            "macd": _clean_list(macd_line),
            "signal": _clean_list(signal_line),
            "histogram": _clean_list(hist),
        },
        "volume_avg": {
            "window": volume_lookback,
            "values": _clean_list(vol_avg),
        },
        "trendline": {
            "values": trend_values,
        },
        "sma_crossover": {
            "fast_window": config.SMA_CROSSOVER_FAST,
            "slow_window": config.SMA_CROSSOVER_SLOW,
            "fast": _clean_list(sma_fast),
            "slow": _clean_list(sma_slow),
        },
        "atr": {
            "period": config.ATR_PERIOD,
            "values": _clean_list(atr_series),
        },
        "strategy_trend_lines": strategy_trend_lines,
        "frvp": frvp,
    }
