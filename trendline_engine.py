"""
Deterministic translation of the manual "draw a ray connecting swing points
that price never crosses" trend-line technique (the "Tori Trades" YouTube
strategy) into an algorithm:

  1. Find swing highs/lows (fractal pivots).
  2. Connect them with the convex hull of the point cloud -- this is exactly
     "as many touch points as possible, with no point ever crossing the
     line," which is what the manual technique is doing by eye. An upward
     (support) line is the LOWER hull of swing lows; a downward (resistance)
     line is the UPPER hull of swing highs.
  3. The line actually traded off of is the hull's most recent edge,
     extended forward as a ray.
  4. Multi-timeframe cascade: each finer timeframe's swing search is
     restricted to bars from the previous (coarser) timeframe's most recent
     touch point onward -- "each new line's point A is the previous line's
     point B," per the videos.
  5. Signal: a BREAKOUT is price crossing a line it was previously on the
     correct side of; a BOUNCE is price nearing an unbroken line from the
     correct side and closing back away from it. Per the videos, a broken
     line's opposite line becomes the "safety line" (stop-loss boundary) on
     a breakout; on a bounce, the SAME line just bounced off is the safety
     line (no line was broken, so there's no "opposite" one to hand off to).
"""

from dataclasses import dataclass, field

import config


@dataclass
class TrendLine:
    kind: str            # "upward" (support) or "downward" (resistance)
    touches: list         # [(pd.Timestamp, price), ...] hull vertices, chronological
    slope: float          # price change per bar index
    intercept: float
    base_len: int          # bar count of the dataframe this line was built from

    def value_at(self, index: int) -> float:
        return self.slope * index + self.intercept

    @property
    def last_touch_ts(self):
        return self.touches[-1][0] if self.touches else None

    @property
    def value_now(self) -> float:
        return self.value_at(self.base_len - 1)


@dataclass
class CascadeResult:
    timeframe: str
    upward: TrendLine = None
    downward: TrendLine = None
    signal: str = "HOLD"          # BREAKOUT_BUY | BREAKOUT_SELL | BOUNCE_BUY | BOUNCE_SELL | HOLD
    action_line: TrendLine = None
    safety_line: TrendLine = None


def resample_ohlcv(daily_df, rule):
    """Resamples a daily OHLCV dataframe to a coarser bar (e.g. 'W-FRI', 'ME')."""
    agg = {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}
    cols = [c for c in agg if c in daily_df.columns]
    out = daily_df[cols].resample(rule).agg({c: agg[c] for c in cols})
    return out.dropna(subset=["Close"]) if "Close" in out.columns else out.dropna(how="all")


def find_swings(df, k):
    """
    Fractal pivot detection: bar i is a swing low if its Low is <= every Low
    within k bars on each side (mirror for swing highs). Returns
    ([(positional_index, price), ...], [(positional_index, price), ...])
    for (swing_lows, swing_highs), positions being 0-based within `df`.
    """
    lows = df["Low"].values
    highs = df["High"].values
    n = len(df)

    swing_lows, swing_highs = [], []
    for i in range(k, n - k):
        window_low = lows[i - k:i + k + 1]
        if lows[i] <= window_low.min():
            swing_lows.append((i, float(lows[i])))
        window_high = highs[i - k:i + k + 1]
        if highs[i] >= window_high.max():
            swing_highs.append((i, float(highs[i])))
    return swing_lows, swing_highs


def _cross(o, a, b):
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def _lower_hull(points):
    """Lower convex hull (support envelope) of (x, y) points, x ascending."""
    pts = sorted(set(points))
    hull = []
    for p in pts:
        while len(hull) >= 2 and _cross(hull[-2], hull[-1], p) <= 0:
            hull.pop()
        hull.append(p)
    return hull


def _upper_hull(points):
    """Upper convex hull (resistance envelope) of (x, y) points, x ascending."""
    pts = sorted(set(points), reverse=True)
    hull = []
    for p in pts:
        while len(hull) >= 2 and _cross(hull[-2], hull[-1], p) <= 0:
            hull.pop()
        hull.append(p)
    return hull


def _hull_to_line(hull_points, kind, df_index):
    """
    Turns a hull point chain into the active TrendLine: the most recent edge
    (walking backward until one actually has the right slope direction --
    upward lines must slope up, downward lines must slope down, per the
    videos' explicit rule), extended forward as a ray.
    """
    if len(hull_points) < 2:
        return None

    for j in range(len(hull_points) - 1, 0, -1):
        x1, y1 = hull_points[j - 1]
        x2, y2 = hull_points[j]
        if x2 == x1:
            continue
        slope = (y2 - y1) / (x2 - x1)
        if (kind == "upward" and slope > 0) or (kind == "downward" and slope < 0):
            intercept = y1 - slope * x1
            touches = [(df_index[x], round(float(y), 4)) for x, y in hull_points[:j + 1]]
            return TrendLine(kind=kind, touches=touches, slope=slope, intercept=intercept,
                              base_len=len(df_index))
    return None


def evaluate_timeframe(df, k, anchor_ts=None):
    """
    Runs swing detection + hull construction for one timeframe's dataframe,
    optionally restricted to bars from `anchor_ts` onward (the cascade's
    "point A = previous timeframe's point B" rule). Returns (upward, downward).
    """
    sub = df[df.index >= anchor_ts] if anchor_ts is not None else df
    if len(sub) < 2 * k + 1:
        return None, None

    swing_lows, swing_highs = find_swings(sub, k)
    upward = _hull_to_line(_lower_hull(swing_lows), "upward", sub.index) if len(swing_lows) >= 2 else None
    downward = _hull_to_line(_upper_hull(swing_highs), "downward", sub.index) if len(swing_highs) >= 2 else None
    return upward, downward


def evaluate_bias(monthly_df, weekly_df, live_price):
    """
    Higher-timeframe bullish/bearish/neutral read, independent of whether the
    Daily-level breakout/bounce cascade itself fired -- used to give a
    POC-only signal a direction (see strategy_engine.py). For each of
    Month/Week: vote bullish if price sits above that timeframe's active
    support line, bearish if below its active resistance line. Majority vote
    wins; a tie (including "no line either way") is neutral.
    """
    votes = []
    for df, key in [(monthly_df, "month"), (weekly_df, "week")]:
        if df is None or df.empty:
            continue
        upward, downward = evaluate_timeframe(df, config.SWING_K[key])
        if upward is not None and live_price >= upward.value_now:
            votes.append("bullish")
        elif downward is not None and live_price <= downward.value_now:
            votes.append("bearish")

    bulls, bears = votes.count("bullish"), votes.count("bearish")
    if bulls > bears:
        return "bullish"
    if bears > bulls:
        return "bearish"
    return "neutral"


def _classify_signal(upward, downward, live_price, prev_close, atr_value):
    up_val = upward.value_now if upward else None
    down_val = downward.value_now if downward else None

    # BREAKOUT: price crossed a line it was previously on the correct side
    # of. The crossed line becomes the action line; the OPPOSITE line
    # becomes the safety line (the old, now-irrelevant boundary is no
    # longer useful -- the opposite line is the new risk boundary).
    if down_val is not None and prev_close < down_val <= live_price:
        return "BREAKOUT_BUY", downward, upward
    if up_val is not None and prev_close > up_val >= live_price:
        return "BREAKOUT_SELL", upward, downward

    tol = config.TRENDLINE_BOUNCE_ATR_MULT * (atr_value or 0)

    # BOUNCE: price is near an UNBROKEN line from the correct side, and the
    # latest bar closed back away from it. Nothing broke, so the safety line
    # is the SAME line just bounced off (per the videos' worked example),
    # not the opposite one.
    if up_val is not None and live_price >= up_val and (live_price - up_val) <= tol and live_price > prev_close:
        return "BOUNCE_BUY", upward, upward
    if down_val is not None and live_price <= down_val and (down_val - live_price) <= tol and live_price < prev_close:
        return "BOUNCE_SELL", downward, downward

    return "HOLD", None, None


def evaluate_cascade(daily_df, weekly_df, monthly_df, live_price, atr_value, thirtymin_df=None):
    """
    Top-down cascade: Month -> Week -> Day (-> 30-Min if provided), each step
    anchored to the previous step's most recent touch point. Classifies the
    breakout/bounce/hold signal at the finest timeframe present.
    """
    frames = [("month", monthly_df, config.SWING_K["month"]),
              ("week", weekly_df, config.SWING_K["week"]),
              ("day", daily_df, config.SWING_K["day"])]
    if thirtymin_df is not None and not thirtymin_df.empty:
        frames.append(("30min", thirtymin_df, config.SWING_K["30min"]))

    anchor_ts = None
    upward = downward = None
    finest_df, finest_name = None, None

    for name, df, k in frames:
        if df is None or df.empty:
            continue
        u, d = evaluate_timeframe(df, k, anchor_ts=anchor_ts)
        if u is not None:
            upward = u
        if d is not None:
            downward = d

        touch_candidates = [ln.last_touch_ts for ln in (u, d) if ln is not None]
        if touch_candidates:
            anchor_ts = max(touch_candidates)
        finest_df, finest_name = df, name

    if finest_df is None or finest_df.empty:
        return CascadeResult(timeframe=finest_name or "day")

    prev_close = float(finest_df["Close"].iloc[-2]) if len(finest_df) >= 2 else live_price
    signal, action_line, safety_line = _classify_signal(upward, downward, live_price, prev_close, atr_value)

    return CascadeResult(timeframe=finest_name, upward=upward, downward=downward,
                          signal=signal, action_line=action_line, safety_line=safety_line)
