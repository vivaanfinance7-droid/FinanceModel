"""
Orchestrates the trend-line + FRVP strategy: the one place that turns raw
price data into the movers.json-shaped result dict. Used by three call
sites (see scanner.py / webapp/app.py):

  - run_full_universe_scan(tickers)   -- the once-per-trading-day full scan
  - run_price_only_refresh(companies) -- the cheap price-only runs the rest
                                          of the day (see config.py's cadence
                                          notes)
  - analyze_single_ticker_full(ticker) -- the manual per-ticker "Refresh"
                                          button, extended to the 30-min leg
"""

import logging
from datetime import datetime

import pandas as pd

import config
import data_provider
import indicators
import store
import trade_plan
import trendline_engine
import universe
import volume_profile

log = logging.getLogger("sp500_scanner")


def _line_dict(line):
    if line is None:
        return None
    return {
        "kind": line.kind,
        "touches": [
            [ts.strftime("%Y-%m-%d") if hasattr(ts, "strftime") else str(ts), price]
            for ts, price in line.touches
        ],
        "value_now": round(line.value_now, 4),
    }


def _trend_line_check_dict(cascade, trend_passes):
    breakout_or_bounce = None
    if cascade.signal.startswith("BREAKOUT"):
        breakout_or_bounce = "breakout"
    elif cascade.signal.startswith("BOUNCE"):
        breakout_or_bounce = "bounce"

    return {
        "passes": trend_passes,
        "timeframe": cascade.timeframe,
        "signal": cascade.signal,
        "breakout_or_bounce": breakout_or_bounce,
        "action_line": _line_dict(cascade.action_line),
        "safety_line": _line_dict(cascade.safety_line),
    }


def _reaction_confirmed(daily_df, direction):
    """
    A simplified stand-in for the FRVP video's literal reaction-candlestick
    read (e.g. a bearish engulfing candle at the level) -- the most recent
    COMPLETED daily candle closed in the matching direction.
    """
    if daily_df is None or daily_df.empty or "Open" not in daily_df.columns:
        return False
    last = daily_df.iloc[-1]
    if direction == "BUY":
        return float(last["Close"]) > float(last["Open"])
    if direction == "SELL":
        return float(last["Close"]) < float(last["Open"])
    return False


_MAX_STOP_ATR_MULT = 10.0  # sanity ceiling on how far a safety-line-derived
                            # stop may sit from entry, in ATR multiples --
                            # a line fit on old touch points and linearly
                            # extrapolated a long distance forward (e.g. a
                            # Monthly-timeframe line evaluated years later)
                            # can land somewhere wildly unrealistic. Confirmed
                            # live on AMZN: a safety line extrapolated to
                            # $3632 against a $217 entry -- 1573% away, and
                            # on the "correct" side of price, so the
                            # same-side check alone didn't catch it.


def _derive_trend_stop(safety_line, direction, atr_value, entry_price):
    """Stop just beyond the safety line, buffered by ATR; falls back to a
    flat ATR distance off entry if no safety line exists, if the safety
    line's value has ended up on the wrong side of the current price, or if
    it's on the right side but implausibly far away (see _MAX_STOP_ATR_MULT).
    A support line only means something as a stop reference while it's
    actually below price (above, for resistance) and within a realistic
    distance of it; past either bound it isn't describing anything price is
    still respecting, and trusting it produces a nonsensical stop."""
    atr_value = atr_value or 0
    if safety_line is not None and atr_value > 0:
        base = safety_line.value_now
        valid_side = (base < entry_price) if direction == "BUY" else (base > entry_price)
        within_sane_distance = abs(base - entry_price) <= _MAX_STOP_ATR_MULT * atr_value
        if valid_side and within_sane_distance:
            buffer = config.STOPLOSS_ATR_BUFFER_MULT * atr_value
            return base - buffer if direction == "BUY" else base + buffer

    fallback = config.STOPLOSS_ATR_FALLBACK_MULT * atr_value
    if fallback <= 0:
        return None
    return entry_price - fallback if direction == "BUY" else entry_price + fallback


def _derive_poc_stop(daily_df, direction, atr_value):
    """Stop beyond the confirming reaction candle's high/low, per the FRVP
    video's 'stop above the high' rule -- buffered by ATR for consistency
    with the trend-line method's stop convention."""
    if daily_df is None or daily_df.empty or "High" not in daily_df.columns or "Low" not in daily_df.columns:
        return None
    last = daily_df.iloc[-1]
    buffer = config.STOPLOSS_ATR_BUFFER_MULT * (atr_value or 0)
    return (float(last["Low"]) - buffer if direction == "BUY"
            else float(last["High"]) + buffer)


def _apply_noise_buffer(stop_price, direction, atr_value):
    """Optional extra ATR-based room pushed onto an already-computed stop,
    off by default (config.STOP_NOISE_ATR_MULT == 0.0 leaves stop_price
    untouched) -- see that setting's comment for why this exists."""
    if stop_price is None or not config.STOP_NOISE_ATR_MULT:
        return stop_price
    extra = config.STOP_NOISE_ATR_MULT * (atr_value or 0)
    return stop_price - extra if direction == "BUY" else stop_price + extra


def _confluence_filter(weekly_df, daily_df, atr_series, direction):
    """
    EXPERIMENTAL, off by default (config.CONFLUENCE_FILTER_ENABLED). A
    quality gate on a trend-line signal combining multi-timeframe Bollinger
    Bands and ATR, per the researched design: don't take a breakout that's
    already chasing an extended weekly move, and don't take one when
    volatility is at an extreme (too quiet = likely noise; too chaotic = a
    stop won't hold regardless of placement). Returns (passes: bool,
    squeeze: bool) -- squeeze is informational only, never blocks a signal.
    """
    passes = True

    if weekly_df is not None and len(weekly_df) >= config.BB_WINDOW:
        w_upper, w_lower, _ = indicators.compute_bollinger(weekly_df["Close"], window=config.BB_WINDOW, num_std=config.BB_NUM_STD)
        band_range = w_upper.iloc[-1] - w_lower.iloc[-1]
        if band_range and not pd.isna(band_range) and band_range > 0:
            pct_b = (weekly_df["Close"].iloc[-1] - w_lower.iloc[-1]) / band_range
            if direction == "BUY" and pct_b > config.CONFLUENCE_PCTB_MAX:
                passes = False
            if direction == "SELL" and pct_b < (1 - config.CONFLUENCE_PCTB_MAX):
                passes = False

    if atr_series is not None:
        trailing = atr_series.dropna().iloc[-config.SQUEEZE_LOOKBACK_DAYS:]
        if len(trailing) >= 30:
            current = trailing.iloc[-1]
            pctl = (trailing < current).mean()
            if not (config.ATR_REGIME_MIN_PCTL <= pctl <= config.ATR_REGIME_MAX_PCTL):
                passes = False

    squeeze = False
    if daily_df is not None and len(daily_df) >= config.BB_WINDOW + config.SQUEEZE_LOOKBACK_DAYS:
        d_upper, d_lower, d_mean = indicators.compute_bollinger(daily_df["Close"], window=config.BB_WINDOW, num_std=config.BB_NUM_STD)
        width = (d_upper - d_lower) / d_mean
        trailing_width = width.dropna().iloc[-config.SQUEEZE_LOOKBACK_DAYS:]
        if len(trailing_width) >= 30:
            recent = trailing_width.iloc[-5:].mean()
            pctl = (trailing_width < recent).mean()
            squeeze = bool(pctl <= config.SQUEEZE_PERCENTILE_MAX)

    return passes, squeeze


def _breakout_volume_confirmed(daily_df):
    """
    EXPERIMENTAL, off by default (config.VOLUME_FILTER_ENABLED). Was the
    most recent day's volume elevated relative to its trailing average?
    Per Bulkowski's published breakout research, breakouts on >=50%
    above-average volume succeed far more often than ones on quiet volume --
    a real signal is supposed to draw participation, not happen quietly.
    """
    if daily_df is None or "Volume" not in daily_df.columns or len(daily_df) < config.VOLUME_LOOKBACK + 1:
        return True  # not enough data to judge -- don't block on it
    volumes = daily_df["Volume"]
    today_volume = volumes.iloc[-1]
    avg_volume = volumes.iloc[-(config.VOLUME_LOOKBACK + 1):-1].mean()
    if avg_volume is None or pd.isna(avg_volume) or avg_volume <= 0 or pd.isna(today_volume):
        return True
    return bool((today_volume / avg_volume) >= config.BREAKOUT_VOLUME_MULT)


def market_regime_bias(market_daily_df):
    """
    Higher-timeframe bias of the broader market (SPY), reusing the exact
    same evaluate_bias machinery already built for individual tickers --
    used to gate signals that fight the broader market's own trend (a
    well-established quant-practice principle: even a good individual-stock
    signal tends to underperform fighting a bearish tape). Public (no
    leading underscore) since callers need to fetch and pass this in.
    """
    if market_daily_df is None or market_daily_df.empty:
        return "neutral"
    market_daily_df = market_daily_df.dropna(subset=["Close"])
    if len(market_daily_df) < 10:
        return "neutral"
    m_weekly = trendline_engine.resample_ohlcv(market_daily_df, "W-FRI")
    m_monthly = trendline_engine.resample_ohlcv(market_daily_df, "ME")
    market_price = float(market_daily_df["Close"].iloc[-1])
    return trendline_engine.evaluate_bias(m_monthly, m_weekly, market_price)


def _relative_strength_ok(daily_df, market_daily_df, direction):
    """
    EXPERIMENTAL, off by default (config.RELATIVE_STRENGTH_FILTER_ENABLED).
    Requires the stock to be OUTPERFORMING the broader market (for a BUY)
    or UNDERPERFORMING it (for a SELL) over the trailing lookback -- the
    momentum/relative-strength factor, one of the more robustly replicated
    findings in equity factor research: recent relative winners tend to
    keep winning, and vice versa. A stock-SELECTION filter (is this even a
    good candidate), distinct from the entry-timing filters above.
    """
    lookback = config.RELATIVE_STRENGTH_LOOKBACK_DAYS
    if daily_df is None or market_daily_df is None:
        return True
    if len(daily_df) < lookback + 1 or len(market_daily_df) < lookback + 1:
        return True
    ticker_start, ticker_now = daily_df["Close"].iloc[-(lookback + 1)], daily_df["Close"].iloc[-1]
    market_start, market_now = market_daily_df["Close"].iloc[-(lookback + 1)], market_daily_df["Close"].iloc[-1]
    if pd.isna(ticker_start) or pd.isna(market_start) or ticker_start <= 0 or market_start <= 0:
        return True
    relative_strength = float((ticker_now / ticker_start - 1) - (market_now / market_start - 1))
    return relative_strength > 0 if direction == "BUY" else relative_strength < 0


def _naive_normalized(ts):
    """
    pd.Timestamp(ts).normalize(), stripped of tz if present. `as_of_ts` here
    is usually daily_df.index[-1] -- tz-AWARE UTC when the daily history
    came from Alpaca, tz-naive when it came from yfinance -- while the
    yfinance-sourced comparison index (earnings dates / analyst actions)
    below is always forced tz-naive. Comparing a tz-aware Timestamp against
    a tz-naive DatetimeIndex raises TypeError, so both sides must agree.
    """
    ts = pd.Timestamp(ts)
    if ts.tzinfo is not None:
        ts = ts.tz_localize(None)
    return ts.normalize()


def _upcoming_earnings_within(ticker, as_of_ts, days_ahead):
    """
    Checks whether `ticker` has an earnings report scheduled within
    `days_ahead` days after `as_of_ts`. Uses yfinance's earnings-date
    history rather than Finnhub's calendar (used elsewhere in this project)
    -- Finnhub's free tier only returns current/upcoming dates (confirmed
    empirically: it returns nothing for a past date range), which would
    make this unbacktestable. yfinance's history goes back years and works
    identically for a live "today" call or a historical as_of_ts, since
    `as_of_ts` is always an explicit parameter here, never inferred from
    datetime.now() internally.
    """
    try:
        import yfinance as yf
        dates_df = yf.Ticker(ticker).get_earnings_dates(limit=60)
    except Exception as e:
        log.warning(f"Earnings-date lookup failed for {ticker}: {e}")
        return False
    if dates_df is None or dates_df.empty:
        return False
    idx = dates_df.index.tz_localize(None).normalize()
    as_of_norm = _naive_normalized(as_of_ts)
    window_end = as_of_norm + pd.Timedelta(days=days_ahead)
    return bool(((idx > as_of_norm) & (idx <= window_end)).any())


def _earnings_avoidance_ok(ticker, as_of_ts):
    """
    EXPERIMENTAL, off by default (config.EARNINGS_AVOIDANCE_FILTER_ENABLED).
    Rejects a new signal if the company reports earnings within
    config.EARNINGS_AVOIDANCE_DAYS -- entering right before a report means
    a chunk of the risk is gap risk unrelated to the chart pattern itself.
    NOTE for production scaling: this is one new yfinance call per ticker
    (no batch endpoint), unlike the SPY-based filters above which fetch
    once and reuse across the whole scan -- worth reconsidering the cost at
    full-universe scale before enabling this permanently.
    """
    if not config.EARNINGS_AVOIDANCE_FILTER_ENABLED:
        return True
    return not _upcoming_earnings_within(ticker, as_of_ts, config.EARNINGS_AVOIDANCE_DAYS)


def _analyst_revision_ok(ticker, as_of_ts, direction):
    """
    EXPERIMENTAL, off by default (config.ANALYST_REVISION_FILTER_ENABLED).
    The estimate-revision factor: requires net analyst rating actions
    (upgrades minus downgrades) over the trailing lookback to not be
    clearly working against the signal's direction -- rejects a BUY only
    if revisions are net negative, a SELL only if net positive (a neutral
    or sparse-coverage stock blocks nothing, same lenient convention as the
    regime filter, since many names have thin analyst coverage in any given
    window). Uses yfinance's upgrades_downgrades history, which carries a
    real dated record back to 2012 -- unlike Finnhub's recommendation-trend
    endpoint, confirmed empirically to only return the last ~4 months
    relative to whenever it's queried, not genuine historical snapshots.
    """
    if not config.ANALYST_REVISION_FILTER_ENABLED:
        return True
    try:
        import yfinance as yf
        ud = yf.Ticker(ticker).upgrades_downgrades
    except Exception as e:
        log.warning(f"Analyst upgrades/downgrades lookup failed for {ticker}: {e}")
        return True
    if ud is None or ud.empty:
        return True
    idx = ud.index.tz_localize(None) if getattr(ud.index, "tz", None) is not None else ud.index
    as_of_norm = _naive_normalized(as_of_ts)
    window_start = as_of_norm - pd.Timedelta(days=config.ANALYST_REVISION_LOOKBACK_DAYS)
    window = ud[(idx > window_start) & (idx <= as_of_norm)]
    if window.empty or "Action" not in window.columns:
        return True
    net = int((window["Action"] == "up").sum()) - int((window["Action"] == "down").sum())
    if direction == "BUY":
        return net >= 0
    return net <= 0


def _fundamental_quality_ok(ticker, as_of_ts, direction):
    """
    EXPERIMENTAL, off by default (config.QUALITY_FILTER_ENABLED). A basic
    quality gate: for a BUY, requires the most recently REPORTED quarter
    (as of as_of_ts -- never a quarter that hadn't been reported yet at
    that point) to show positive EPS. Deliberately asymmetric: quality
    investing is fundamentally a long-side concept (avoid buying
    unprofitable companies), so this doesn't restrict SELL signals at all.
    Reuses the same yfinance earnings-date history as the earnings-
    avoidance filter (Reported EPS is a column on that same dataframe) --
    no new data source needed.
    """
    if not config.QUALITY_FILTER_ENABLED or direction != "BUY":
        return True
    try:
        import yfinance as yf
        dates_df = yf.Ticker(ticker).get_earnings_dates(limit=60)
    except Exception as e:
        log.warning(f"Earnings-history lookup failed for {ticker}: {e}")
        return True
    if dates_df is None or dates_df.empty or "Reported EPS" not in dates_df.columns:
        return True
    idx = dates_df.index.tz_localize(None).normalize()
    as_of_norm = _naive_normalized(as_of_ts)
    reported = dates_df[idx <= as_of_norm]  # only quarters already reported by this date
    if reported.empty:
        return True
    eps = reported.iloc[0]["Reported EPS"]  # most recent reported quarter (index is newest-first)
    if eps is None or pd.isna(eps):
        return True
    return bool(eps > 0)


def _sector_crowding_ok(ticker, recommendation, sector_map, peer_recommendations):
    """
    See config.SECTOR_CROWDING_FILTER_ENABLED for the backtest evidence.
    Requires at least one OTHER ticker in the same GICS sector to ALSO have
    the same recommendation on this scan -- an isolated single-stock signal
    tested at exact breakeven (33.3%, n=21) vs. 54.5% (n=143) when at least
    one sector peer confirms. peer_recommendations is {ticker: recommendation}
    for the rest of the current scan (or the last full scan, for a manual
    single-ticker refresh -- see analyze_single_ticker_full).
    """
    if not config.SECTOR_CROWDING_FILTER_ENABLED or recommendation == "HOLD":
        return True
    sector = sector_map.get(ticker)
    if not sector:
        return True  # unknown sector -- don't block on missing data
    return any(
        t != ticker and sector_map.get(t) == sector and rec == recommendation
        for t, rec in peer_recommendations.items()
    )


def _apply_sector_crowding_gate(results):
    """Post-processing pass over a full scan's results -- needs the WHOLE
    batch at once (cross-sectional context no single-ticker analyze_ticker
    call has), so it can't live inside analyze_ticker itself. Demotes an
    isolated signal to HOLD rather than leaving it silently unflagged."""
    if not config.SECTOR_CROWDING_FILTER_ENABLED:
        return results
    sector_map = universe.get_sector_map()
    peer_recommendations = {r["ticker"]: r["recommendation"] for r in results}
    for r in results:
        if r["recommendation"] == "HOLD":
            r["trend_line_check"]["sector_crowding_blocked"] = False
            continue
        if _sector_crowding_ok(r["ticker"], r["recommendation"], sector_map, peer_recommendations):
            r["trend_line_check"]["sector_crowding_blocked"] = False
        else:
            r["recommendation"] = "HOLD"
            r["trade_plan"] = None
            r["earnings_soon"] = False  # badge only applies to an active recommendation
            r["trend_line_check"]["sector_crowding_blocked"] = True
    return results


def analyze_ticker(ticker, daily_df, intraday_df, live_price, include_30min=False, thirtymin_df=None, market_daily_df=None):
    """Runs both methods for one ticker and returns the combined result dict,
    or None if there isn't enough data to say anything. market_daily_df
    (SPY's own daily bars, same lookback depth) is optional -- when given,
    its higher-timeframe bias is always computed and surfaced as
    trend_line_check.market_bias (a visible factor), and (when
    config.REGIME_GATED_RECOMMENDATIONS_ENABLED, on by default) used to
    gate which signal source is trusted to drive a recommendation.
    Callers should fetch market_daily_df once and reuse it across every
    ticker in a scan rather than refetching per ticker."""
    if daily_df is None or daily_df.empty or live_price is None:
        return None

    daily_df = daily_df.dropna(subset=["Close"]) if "Close" in daily_df.columns else daily_df
    if len(daily_df) < 10:
        return None

    weekly_df = trendline_engine.resample_ohlcv(daily_df, "W-FRI")
    monthly_df = trendline_engine.resample_ohlcv(daily_df, "ME")

    if "High" in daily_df.columns and "Low" in daily_df.columns:
        atr_series = indicators.compute_atr(daily_df["High"], daily_df["Low"], daily_df["Close"])
        atr_last = atr_series.iloc[-1]
        atr_value = float(atr_last) if not pd.isna(atr_last) else None
    else:
        atr_series = None
        atr_value = None

    # Breakout/bounce classification and higher-timeframe bias are evaluated
    # against the last CONFIRMED daily close, never a live intraday quote --
    # every backtest this session used a closed candle here (as_of's own
    # close is always final in a backtest), so this is what "validated"
    # actually means; a live intraday snapshot can spike through a line and
    # reverse before the day ends (a classic breakout fakeout -- see the
    # trend-line source material's own warning on this). live_price itself
    # is still used below for the trade plan's entry/target/stop and for
    # FRVP proximity (both legitimately want "what would I actually pay
    # right now," not a confirmed close).
    confirmed_price = float(daily_df["Close"].iloc[-1])
    cascade = trendline_engine.evaluate_cascade(
        daily_df, weekly_df, monthly_df, confirmed_price, atr_value,
        thirtymin_df=thirtymin_df if include_30min else None,
    )
    bias = trendline_engine.evaluate_bias(monthly_df, weekly_df, confirmed_price)

    # "Forming" signal: a live, UNCONFIRMED preview of whether price is
    # currently testing a line intraday -- purely informational. Reuses the
    # exact same lines and classification function as the real signal, just
    # fed the live price instead of waiting for today's close. This must
    # NEVER touch recommendation/trade_plan/any gate below -- the whole
    # point of the candle-close fix earlier this session was to stop
    # reacting to intraday wicks, and this field exists so a person can see
    # "something's happening" without the system acting on it prematurely.
    forming_raw, _, _ = trendline_engine._classify_signal(
        cascade.upward, cascade.downward, live_price, confirmed_price, atr_value)
    forming_direction = {"BREAKOUT_BUY": "BUY", "BOUNCE_BUY": "BUY",
                          "BREAKOUT_SELL": "SELL", "BOUNCE_SELL": "SELL"}.get(forming_raw)
    forming_blocked = config.LONG_ONLY_MODE and forming_direction == "SELL"
    forming_signal = forming_raw if (forming_direction and not forming_blocked) else None

    poc_windows = volume_profile.evaluate_windows(intraday_df, live_price) if intraday_df is not None else {}
    poc_approaching = any(w["approaching"] for w in poc_windows.values())

    trend_passes = cascade.signal != "HOLD"
    trend_direction = {
        "BREAKOUT_BUY": "BUY", "BOUNCE_BUY": "BUY",
        "BREAKOUT_SELL": "SELL", "BOUNCE_SELL": "SELL",
    }.get(cascade.signal)

    poc_direction = None
    poc_reaction_confirmed = False
    if poc_approaching and bias in ("bullish", "bearish"):
        poc_direction = "BUY" if bias == "bullish" else "SELL"
        poc_reaction_confirmed = _reaction_confirmed(daily_df, poc_direction)

    # Multi-timeframe Bollinger + ATR confluence gate on the trend-line
    # signal -- experimental, off by default. Doesn't change what
    # trend_line_check.passes reports (that's still the raw signal), only
    # whether it's trusted enough to drive the recommendation.
    trend_confluence_ok, squeeze = True, False
    if trend_passes and config.CONFLUENCE_FILTER_ENABLED:
        trend_confluence_ok, squeeze = _confluence_filter(weekly_df, daily_df, atr_series, trend_direction)

    volume_confirmed = True
    if trend_passes and config.VOLUME_FILTER_ENABLED:
        volume_confirmed = _breakout_volume_confirmed(daily_df)

    # market_bias is ALWAYS computed (when market_daily_df is available) --
    # kept as a visible factor/indicator regardless of gating below.
    market_bias = market_regime_bias(market_daily_df)

    # Market-regime gate on which signal SOURCE is trusted to drive a
    # recommendation -- see config.REGIME_GATED_RECOMMENDATIONS_ENABLED's
    # comment for the backtest evidence. Trend-line signals are trusted only
    # when the broader market isn't already bullish; POC never supplies a
    # recommendation under this gate -- it underperformed in BOTH regimes.
    regime_trusts_trend = (not config.REGIME_GATED_RECOMMENDATIONS_ENABLED) or (market_bias != "bullish")
    regime_trusts_poc = not config.REGIME_GATED_RECOMMENDATIONS_ENABLED

    relative_strength_ok = True
    if trend_passes and config.RELATIVE_STRENGTH_FILTER_ENABLED:
        relative_strength_ok = _relative_strength_ok(daily_df, market_daily_df, trend_direction)

    earnings_ok = True
    if trend_passes and config.EARNINGS_AVOIDANCE_FILTER_ENABLED:
        earnings_ok = _earnings_avoidance_ok(ticker, daily_df.index[-1])

    analyst_revision_ok = True
    if trend_passes and config.ANALYST_REVISION_FILTER_ENABLED:
        analyst_revision_ok = _analyst_revision_ok(ticker, daily_df.index[-1], trend_direction)

    quality_ok = True
    if trend_passes and config.QUALITY_FILTER_ENABLED:
        quality_ok = _fundamental_quality_ok(ticker, daily_df.index[-1], trend_direction)

    # Long-only mode: a stated trading preference (not a performance
    # experiment), on by default -- never recommend entering a SELL/short
    # position. A blocked SELL still falls through to check the POC method
    # independently below, rather than just giving up, so a real long
    # opportunity there isn't missed just because the trend-line read was
    # bearish. trend_line_check.passes/signal are untouched by this (still
    # show the raw bearish read, for information) -- only the recommendation
    # and trade_plan are affected.
    long_only_blocks_trend = config.LONG_ONLY_MODE and trend_direction == "SELL"
    long_only_blocks_poc = config.LONG_ONLY_MODE and poc_direction == "SELL"

    trend_signal_ok = (trend_confluence_ok and volume_confirmed and regime_trusts_trend
                        and relative_strength_ok and earnings_ok
                        and analyst_revision_ok and quality_ok
                        and not long_only_blocks_trend)

    # Precedence: the trend-line method is "the main analysis" -- its
    # direction wins whenever it fired and clears whichever gates above are
    # enabled. Only then does a CONFIRMED POC direction (proximity +
    # matching bias + reaction candle) supply the recommendation, and only
    # if the regime gate hasn't retired POC as a source entirely. Otherwise
    # genuinely HOLD.
    if trend_passes and trend_signal_ok:
        recommendation = trend_direction
        stop_price = _derive_trend_stop(cascade.safety_line, recommendation, atr_value, live_price)
    elif regime_trusts_poc and poc_direction and poc_reaction_confirmed and not long_only_blocks_poc:
        recommendation = poc_direction
        stop_price = _derive_poc_stop(daily_df, recommendation, atr_value)
    else:
        recommendation = "HOLD"
        stop_price = None

    stop_price = _apply_noise_buffer(stop_price, recommendation, atr_value)

    plan = (trade_plan.build_trade_plan(recommendation, live_price, stop_price, atr_value)
            if recommendation != "HOLD" else None)

    # Display-only "earnings soon" badge -- only computed for the handful of
    # tickers with an active recommendation, not the full universe (see
    # config.EARNINGS_BADGE_DAYS's comment on why this stays a per-ticker
    # yfinance call rather than something run for all 500 tickers).
    earnings_soon = (recommendation != "HOLD"
                      and _upcoming_earnings_within(ticker, daily_df.index[-1], config.EARNINGS_BADGE_DAYS))

    now = datetime.now().isoformat()

    return {
        "ticker": ticker,
        "recommendation": recommendation,
        "price": round(live_price, 2),
        "earnings_soon": bool(earnings_soon),
        "higher_tf_bias": bias,
        "trend_line_check": {
            **_trend_line_check_dict(cascade, trend_passes),
            "confluence_ok": trend_confluence_ok,
            "squeeze": squeeze,
            "volume_confirmed": volume_confirmed,
            "market_bias": market_bias,
            "regime_trusted": regime_trusts_trend,
            "relative_strength_ok": relative_strength_ok,
            "earnings_ok": earnings_ok,
            "analyst_revision_ok": analyst_revision_ok,
            "quality_ok": quality_ok,
            "long_only_blocked": bool(long_only_blocks_trend),
            # Only surfaced when there's no confirmed recommendation already --
            # redundant (and potentially confusing) to show a "forming" watch
            # on a ticker that already has a real, confirmed trade plan.
            "forming_signal": forming_signal if recommendation == "HOLD" else None,
        },
        "poc_check": {
            "approaching": poc_approaching,
            "direction": poc_direction,
            "reaction_confirmed": poc_reaction_confirmed,
            "windows": poc_windows,
        },
        "trade_plan": None if plan is None else {
            "entry": plan.entry, "stop": plan.stop, "target": plan.target,
            "qty": plan.qty, "risk_dollars": plan.risk_dollars, "reward_risk": plan.reward_risk,
            "atr": plan.atr,
        },
        "passes": trend_passes or poc_approaching,
        "last_full_analysis_at": now,
        "last_price_refresh_at": now,
    }


def _fetch_market_daily(days, source_hint=None):
    """SPY's own daily history, fetched once and reused across an entire
    scan -- backs the market_bias factor (see market_regime_bias) for every
    ticker without refetching per ticker. Failure just means market_bias
    reports "neutral" for this run rather than aborting the scan."""
    try:
        market_df, _ = data_provider.get_single_ticker_history("SPY", days, source_hint=source_hint)
        return market_df
    except Exception as e:
        log.warning(f"SPY fetch for market_bias failed ({e}) -- market_bias will report 'neutral' this run.")
        return None


def run_full_universe_scan(tickers):
    """The once-per-trading-day full scan: both methods, the whole universe."""
    daily_hist, source = data_provider.get_daily_history(tickers, days=config.TREND_HISTORY_DAYS)
    if not daily_hist:
        log.warning("Strategy scan: no daily history returned for any ticker.")
        return []

    scanned = list(daily_hist.keys())
    intraday_hist, _ = data_provider.get_intraday_history_batch(
        scanned, minutes=config.FRVP_INTRADAY_MINUTES, days=config.FRVP_FETCH_DAYS,
    )
    live_prices = data_provider.get_live_prices(scanned, source_hint=source)
    market_daily_df = _fetch_market_daily(config.TREND_HISTORY_DAYS, source_hint=source)

    results = []
    for ticker, daily_df in daily_hist.items():
        price = live_prices.get(ticker)
        if price is None:
            continue
        try:
            result = analyze_ticker(ticker, daily_df, intraday_hist.get(ticker), price, market_daily_df=market_daily_df)
        except Exception as e:
            log.warning(f"Strategy analysis failed for {ticker}: {e}")
            continue
        if result:
            results.append(result)

    results = _apply_sector_crowding_gate(results)

    log.info(f"Full strategy scan analyzed {len(results)}/{len(tickers)} tickers.")
    return results


def run_price_only_refresh(current_companies):
    """Cheap refresh: just updates displayed price for tickers already on
    the Movers tab. Does not touch trend_line_check/poc_check/trade_plan."""
    tickers = [c["ticker"] for c in current_companies]
    if not tickers:
        return []

    live_prices = data_provider.get_live_prices(tickers)
    now = datetime.now().isoformat()

    patched = []
    for c in current_companies:
        c = dict(c)
        price = live_prices.get(c["ticker"])
        if price is not None:
            c["price"] = round(price, 2)
        c["last_price_refresh_at"] = now
        patched.append(c)
    return patched


def analyze_single_ticker_full(ticker):
    """The manual per-ticker Refresh action: full method, one ticker, on
    demand, extended to the 30-minute cascade leg."""
    ticker = ticker.upper().strip()

    daily_df, source = data_provider.get_single_ticker_history(ticker, config.TREND_HISTORY_DAYS)
    if daily_df is None or daily_df.empty:
        raise ValueError(f"No historical data available for {ticker}")

    intraday_df, _ = data_provider.get_intraday_history(
        ticker, minutes=config.FRVP_INTRADAY_MINUTES, days=config.MANUAL_REFRESH_INTRADAY_DAYS,
        source_hint=source,
    )
    live_price = data_provider.get_live_prices([ticker], source_hint=source).get(ticker)
    if live_price is None:
        raise ValueError(f"No live price available for {ticker}")

    market_daily_df = _fetch_market_daily(config.TREND_HISTORY_DAYS, source_hint=source) if ticker != "SPY" else daily_df

    result = analyze_ticker(ticker, daily_df, intraday_df, live_price,
                             include_30min=True, thirtymin_df=intraday_df, market_daily_df=market_daily_df)
    if result is None:
        raise ValueError(f"Strategy analysis failed for {ticker}")

    # Sector crowding needs cross-sectional context this single-ticker call
    # doesn't have on its own -- reuse the last full scan's movers.json as
    # the peer set rather than re-scanning the whole sector for one click.
    if config.SECTOR_CROWDING_FILTER_ENABLED and result["recommendation"] != "HOLD":
        sector_map = universe.get_sector_map()
        peer_recommendations = {c["ticker"]: c["recommendation"] for c in store.load_movers().get("companies", [])}
        if not _sector_crowding_ok(ticker, result["recommendation"], sector_map, peer_recommendations):
            result["recommendation"] = "HOLD"
            result["trade_plan"] = None
            result["earnings_soon"] = False
            result["trend_line_check"]["sector_crowding_blocked"] = True
        else:
            result["trend_line_check"]["sector_crowding_blocked"] = False
    else:
        result["trend_line_check"]["sector_crowding_blocked"] = False

    return result
