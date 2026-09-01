"""
Technical indicator calculations and the combined multi-factor signal logic.

Design: a Bollinger Band touch is the PRIMARY trigger (required). RSI, MACD,
and volume are CONFIRMING factors -- each either supports the signal or
doesn't. config.MIN_CONFIRMATIONS controls how many of the 3 confirmations
are required before an alert actually fires, which cuts down on false
positives from a stock simply "walking the band" in a strong trend.
"""

from dataclasses import dataclass, field
from datetime import datetime

import numpy as np
import pandas as pd

import config
import market_hours


@dataclass
class SignalResult:
    ticker: str
    signal: str              # "BUY" or "SELL"
    price: float
    upper_band: float
    lower_band: float
    mean_band: float          # the rolling average the bands are centered on
    rsi: float
    macd_histogram: float
    volume_ratio: float
    confirmations: list = field(default_factory=list)   # e.g. ["RSI", "Volume"]

    @property
    def num_confirmations(self):
        return len(self.confirmations)

    @property
    def passes_threshold(self):
        return self.num_confirmations >= config.MIN_CONFIRMATIONS

    @property
    def potential_pct(self):
        """
        Signed % move from the current price back to the band's mean (the
        classic mean-reversion target) -- positive for a BUY (upside to the
        average), negative for a SELL (downside if it reverts). This is a
        distance-from-average figure, not a price forecast or guarantee.
        """
        if not self.price:
            return 0.0
        return (self.mean_band - self.price) / self.price * 100

    def summary(self):
        conf = "+".join(self.confirmations) if self.confirmations else "no confirmation"
        return (f"{self.ticker} {self.signal} @ {self.price:.2f} "
                f"[{conf}] (RSI {self.rsi:.0f}, MACD hist {self.macd_histogram:+.2f}, "
                f"vol {self.volume_ratio:.1f}x avg, potential {self.potential_pct:+.1f}% to mean)")


def compute_bollinger(closes: pd.Series, window: int = None, num_std: float = None):
    """Returns (upper_band, lower_band, mean) using the given (or config default) window."""
    window = window or config.BB_WINDOW
    num_std = num_std if num_std is not None else config.BB_NUM_STD
    rolling_mean = closes.rolling(window).mean()
    rolling_std = closes.rolling(window).std()
    upper = rolling_mean + num_std * rolling_std
    lower = rolling_mean - num_std * rolling_std
    return upper, lower, rolling_mean


def compute_rsi(closes: pd.Series, period: int = None):
    """
    Classic Wilder-smoothed RSI. Returns a pandas Series aligned with `closes`.
    """
    period = period or config.RSI_PERIOD
    delta = closes.diff()

    gains = delta.clip(lower=0)
    losses = -delta.clip(upper=0)

    avg_gain = gains.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = losses.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()

    rs = avg_gain / avg_loss.replace(0, 1e-10)
    rsi = 100 - (100 / (1 + rs))
    return rsi


def compute_macd(closes: pd.Series, fast: int = None, slow: int = None, signal: int = None):
    """Returns (macd_line, signal_line, histogram) as pandas Series."""
    fast = fast or config.MACD_FAST
    slow = slow or config.MACD_SLOW
    signal = signal or config.MACD_SIGNAL
    ema_fast = closes.ewm(span=fast, adjust=False).mean()
    ema_slow = closes.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def compute_trendline(closes: pd.Series):
    """
    Least-squares best-fit line through whatever series is passed. The
    caller controls the window -- chart_data.py passes only the currently
    DISPLAYED (period-trimmed) closes, so the line reflects "the trend over
    the period you're looking at right now" and refits whenever you change
    the period button, rather than being a single fixed line.
    """
    clean = closes.dropna()
    if len(clean) < 2:
        return pd.Series(index=closes.index, dtype=float)
    x = np.arange(len(clean))
    slope, intercept = np.polyfit(x, clean.values, 1)
    return pd.Series(slope * x + intercept, index=clean.index).reindex(closes.index)


def compute_sma_crossover(closes: pd.Series, fast_window: int = None, slow_window: int = None):
    """
    Returns (fast_sma, slow_sma) -- the standard 50/200-day "Golden Cross /
    Death Cross" moving averages. Fixed at these lengths by default
    regardless of the adjustable Bollinger window, since 50/200 is the
    conventional definition traders mean by that name.
    """
    fast_window = fast_window or config.SMA_CROSSOVER_FAST
    slow_window = slow_window or config.SMA_CROSSOVER_SLOW
    return closes.rolling(fast_window).mean(), closes.rolling(slow_window).mean()


def compute_atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = None):
    """
    Average True Range -- a volatility measure (typical daily price range),
    Wilder-smoothed the same way compute_rsi() smooths gains/losses.
    """
    period = period or config.ATR_PERIOD
    prev_close = close.shift(1)
    true_range = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return true_range.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()


def compute_volume_ratio(volumes: pd.Series, now=None):
    """
    Compares a time-of-day-adjusted projection of today's volume against the
    trailing average. Returns the ratio (e.g. 1.8 = 80% above average).
    `volumes` should include today's (possibly partial) bar as the last value.
    """
    if len(volumes) < config.VOLUME_LOOKBACK + 1:
        return 1.0  # not enough history -- treat as neutral, don't block on it

    today_volume_so_far = volumes.iloc[-1]
    avg_volume = volumes.iloc[-(config.VOLUME_LOOKBACK + 1):-1].mean()

    if avg_volume <= 0:
        return 1.0

    fraction = market_hours.elapsed_trading_fraction(now)
    projected_today = today_volume_so_far / fraction

    return projected_today / avg_volume


def _exclude_partial_today(closes: pd.Series, now=None):
    """
    If the data provider's last row is dated today, drop it before computing
    Bollinger/RSI/MACD. Since the scanner only runs while the market is open
    (see market_hours.is_market_hours), any "today" row we'd see is by
    definition incomplete -- and the live price we compare against is fetched
    independently, so leaving it in would mean comparing the live price
    against a band that has that same live price baked into one of its
    inputs. Excluding it keeps the two properly independent.
    """
    if len(closes) == 0:
        return closes

    now = now or datetime.now(market_hours.NY_TZ)
    now_ny = now.astimezone(market_hours.NY_TZ)

    last_ts = closes.index[-1]
    last_date = last_ts.date() if hasattr(last_ts, "date") else last_ts

    if last_date == now_ny.date():
        return closes.iloc[:-1]
    return closes


def evaluate_ticker(ticker: str, history_df: pd.DataFrame, live_price: float, now=None):
    """
    Runs all indicators for one ticker and returns a SignalResult if the
    Bollinger Band was touched, or None if price is inside the bands.
    """
    full_closes = history_df["Close"].dropna()
    volumes = history_df["Volume"].dropna()  # keep today's partial volume -- the
                                              # spike-ratio calc needs it and already
                                              # excludes it from its own average

    closes = _exclude_partial_today(full_closes, now=now)

    if len(closes) < max(config.BB_WINDOW, config.MACD_SLOW) + 1:
        return None  # not enough completed-day history to compute indicators reliably

    upper, lower, mean = compute_bollinger(closes)
    upper_val, lower_val, mean_val = upper.iloc[-1], lower.iloc[-1], mean.iloc[-1]

    if live_price <= lower_val:
        signal = "BUY"
    elif live_price >= upper_val:
        signal = "SELL"
    else:
        return None  # inside the bands -- nothing to report

    rsi_series = compute_rsi(closes)
    rsi_val = rsi_series.iloc[-1]

    _, _, hist_series = compute_macd(closes)
    hist_val = hist_series.iloc[-1]

    vol_ratio = compute_volume_ratio(volumes, now=now)

    confirmations = []
    if signal == "BUY":
        if not pd.isna(rsi_val) and rsi_val <= config.RSI_OVERSOLD:
            confirmations.append("RSI")
        if not pd.isna(hist_val) and hist_val > 0:
            confirmations.append("MACD")
    else:  # SELL
        if not pd.isna(rsi_val) and rsi_val >= config.RSI_OVERBOUGHT:
            confirmations.append("RSI")
        if not pd.isna(hist_val) and hist_val < 0:
            confirmations.append("MACD")

    if vol_ratio >= config.VOLUME_SPIKE_MULTIPLIER:
        confirmations.append("Volume")

    return SignalResult(
        ticker=ticker,
        signal=signal,
        price=live_price,
        upper_band=upper_val,
        lower_band=lower_val,
        mean_band=mean_val if not pd.isna(mean_val) else live_price,
        rsi=rsi_val if not pd.isna(rsi_val) else 50.0,
        macd_histogram=hist_val if not pd.isna(hist_val) else 0.0,
        volume_ratio=vol_ratio,
        confirmations=confirmations,
    )
