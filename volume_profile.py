"""
Fixed Range Volume Profile (FRVP): buckets volume by price level over a
historical (never the still-forming current session) window, and reports the
Point of Control (POC -- the price level with the most traded volume) plus
the Value Area High/Low (the ~70%-of-volume band around the POC). Requires
intraday bars -- daily OHLCV is too coarse to build a meaningful histogram
for a 1-day or 3-day window.
"""

from datetime import datetime

import numpy as np

import config
import market_hours


def _completed_trading_days(intraday_df):
    """Distinct calendar dates present in `intraday_df`, excluding today (the
    current session is still forming, so its volume would skew/flicker the
    profile -- matches the FRVP videos' explicit rule to exclude it)."""
    today = datetime.now(market_hours.NY_TZ).date()
    dates = sorted(set(ts.date() for ts in intraday_df.index))
    return [d for d in dates if d < today]


def _window_boundaries(intraday_df, n_trading_days):
    """Returns (start_ts, end_ts) covering the most recent `n_trading_days`
    COMPLETED trading days present in `intraday_df`, or (None, None) if
    there isn't at least one completed day yet (e.g. right after a holiday)."""
    completed = _completed_trading_days(intraday_df)
    if not completed:
        return None, None

    days = set(completed[-n_trading_days:])
    mask = [ts.date() in days for ts in intraday_df.index]
    sub = intraday_df[mask]
    if sub.empty:
        return None, None
    return sub.index.min(), sub.index.max()


def _value_area(edges, bin_volumes, poc_idx):
    total = bin_volumes.sum()
    if total <= 0:
        return None, None

    target = config.FRVP_VALUE_AREA_PCT * total
    lo = hi = poc_idx
    captured = bin_volumes[poc_idx]

    while captured < target and (lo > 0 or hi < len(bin_volumes) - 1):
        vol_below = bin_volumes[lo - 1] if lo > 0 else -1
        vol_above = bin_volumes[hi + 1] if hi < len(bin_volumes) - 1 else -1
        if vol_above >= vol_below:
            hi += 1
            captured += bin_volumes[hi]
        else:
            lo -= 1
            captured += bin_volumes[lo]

    return round(float(edges[hi + 1]), 4), round(float(edges[lo]), 4)


def compute_profile(intraday_df, start_ts, end_ts, bin_count=None):
    """
    Bins volume-at-price for bars in [start_ts, end_ts]. Each bar's volume is
    distributed across every price bin its [Low, High] range overlaps,
    weighted by overlap fraction -- the standard approximation used when
    tick-level trade data isn't available. Returns None if the window has no
    bars.
    """
    bin_count = bin_count or config.FRVP_BIN_COUNT
    window_df = intraday_df[(intraday_df.index >= start_ts) & (intraday_df.index <= end_ts)]
    if window_df.empty:
        return None

    price_min = float(window_df["Low"].min())
    price_max = float(window_df["High"].max())
    if price_max <= price_min:
        price_max = price_min + 0.01

    edges = np.linspace(price_min, price_max, bin_count + 1)
    bin_volumes = np.zeros(bin_count)
    span = price_max - price_min

    for _, row in window_df.iterrows():
        lo, hi = float(row["Low"]), float(row["High"])
        vol = float(row["Volume"]) if "Volume" in row and row["Volume"] == row["Volume"] else 0.0
        if vol <= 0:
            continue

        if hi <= lo:
            idx = min(max(int((lo - price_min) / span * bin_count), 0), bin_count - 1)
            bin_volumes[idx] += vol
            continue

        lo_idx = max(int((lo - price_min) / span * bin_count), 0)
        hi_idx = min(int((hi - price_min) / span * bin_count), bin_count - 1)
        for b in range(lo_idx, hi_idx + 1):
            overlap = max(0.0, min(hi, edges[b + 1]) - max(lo, edges[b]))
            bin_volumes[b] += vol * (overlap / (hi - lo))

    poc_idx = int(np.argmax(bin_volumes))
    poc_price = round(float(edges[poc_idx] + edges[poc_idx + 1]) / 2, 4)
    vah, val = _value_area(edges, bin_volumes, poc_idx)

    bins = [
        {"price_low": round(float(edges[i]), 4), "price_high": round(float(edges[i + 1]), 4),
         "volume": round(float(bin_volumes[i]), 2)}
        for i in range(bin_count)
    ]

    return {"bins": bins, "poc_price": poc_price, "value_area_high": vah, "value_area_low": val,
            "start_ts": start_ts, "end_ts": end_ts}


def get_profile_for_window(intraday_df, n_trading_days, bin_count=None):
    """
    Convenience wrapper (window boundaries + compute_profile) for a single
    window that keeps the full bin histogram -- used by chart_data.py to
    draw the actual volume-at-price overlay. evaluate_windows() below only
    returns the POC/value-area summary, which is all the strategy engine
    needs for movers.json and would otherwise bloat it with ~25 bins per
    window per ticker for no benefit there.
    """
    if intraday_df is None or intraday_df.empty:
        return None
    start_ts, end_ts = _window_boundaries(intraday_df, n_trading_days)
    if start_ts is None:
        return None
    return compute_profile(intraday_df, start_ts, end_ts, bin_count=bin_count)


def evaluate_windows(intraday_df, live_price, windows=None, proximity_pct=None):
    """
    Computes a profile per window (default config.FRVP_WINDOWS: prior_day /
    prior_3d / prior_week) and flags whether `live_price` is "approaching"
    each window's POC (within `proximity_pct`, default config.FRVP_PROXIMITY_PCT).
    Degrades gracefully -- skips a window rather than raising -- if the data
    doesn't yet cover a full window (e.g. a short holiday week).
    """
    windows = windows or config.FRVP_WINDOWS
    proximity_pct = proximity_pct if proximity_pct is not None else config.FRVP_PROXIMITY_PCT

    results = {}
    if intraday_df is None or intraday_df.empty or live_price is None:
        return results

    for key, n_days in windows.items():
        start_ts, end_ts = _window_boundaries(intraday_df, n_days)
        if start_ts is None:
            continue
        profile = compute_profile(intraday_df, start_ts, end_ts)
        if profile is None or not profile["poc_price"]:
            continue

        poc_price = float(profile["poc_price"])
        distance_pct = round(float(abs(live_price - poc_price) / poc_price * 100), 2)
        results[key] = {
            "poc_price": poc_price,
            "distance_pct": distance_pct,
            "approaching": bool(distance_pct <= proximity_pct * 100),
            "value_area_high": profile["value_area_high"],
            "value_area_low": profile["value_area_low"],
        }

    return results
