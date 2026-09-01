"""
Regular-hours check for the US stock market (America/New_York), including
NYSE holidays and early-close (half) days.

Trading-day boundaries -- is there a session today, and when does it open
and close -- come from the official NYSE calendar via
`pandas_market_calendars`, so holidays (Thanksgiving, Christmas, New Year's
Day, MLK Day, Presidents Day, Good Friday, Memorial Day, Juneteenth,
Independence Day, Labor Day -- including when they're "observed" on an
adjacent weekday) correctly report the market as closed, and early-close
days (day after Thanksgiving, Christmas Eve, July 3rd when applicable)
correctly report the real ~1:00pm ET close instead of always assuming 4:00pm.
"""

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pandas_market_calendars as mcal

NY_TZ = ZoneInfo("America/New_York")

_NYSE = mcal.get_calendar("NYSE")

# NY-local date -> (open_dt, close_dt) as tz-aware datetimes in NY_TZ,
# or None if that date is not a trading day (weekend or NYSE holiday).
# Populated lazily; a scan touches ~500 tickers per run via
# elapsed_trading_fraction(), so this avoids recomputing the schedule
# lookup once per ticker -- it's computed at most once per calendar date.
_SESSION_CACHE = {}


def _session_for(day: date):
    if day in _SESSION_CACHE:
        return _SESSION_CACHE[day]

    sched = _NYSE.schedule(start_date=day, end_date=day)

    if sched.empty:
        session = None  # weekend or NYSE holiday
    else:
        open_dt = sched.iloc[0]["market_open"].tz_convert(NY_TZ).to_pydatetime()
        close_dt = sched.iloc[0]["market_close"].tz_convert(NY_TZ).to_pydatetime()
        session = (open_dt, close_dt)

    _SESSION_CACHE[day] = session
    return session


def is_market_hours(now=None):
    now = now or datetime.now(NY_TZ)
    now_ny = now.astimezone(NY_TZ)

    session = _session_for(now_ny.date())
    if session is None:
        return False

    open_dt, close_dt = session
    return open_dt <= now_ny <= close_dt


def elapsed_trading_fraction(now=None, floor=0.05):
    """
    Returns roughly how much of the regular trading session has elapsed, as a
    fraction from 0.0 (market just opened) to 1.0 (market closed). Used to
    project a fair "full day" volume estimate from partial-day volume so
    we're not comparing 45 minutes of volume against a full day's average.
    Uses that day's real close time, so early-close days aren't treated as
    if 4:00pm is still hours away.

    `floor` prevents division-by-near-zero blowups in the first few minutes
    of trading.

    If called on a non-trading day (weekend/holiday) there's no session to
    measure against; callers are expected to gate on `is_market_hours()`
    first (see scanner.py), so this is a defensive fallback only.
    """
    now = now or datetime.now(NY_TZ)
    now_ny = now.astimezone(NY_TZ)

    session = _session_for(now_ny.date())
    if session is None:
        return floor

    open_dt, close_dt = session

    if now_ny <= open_dt:
        return floor
    if now_ny >= close_dt:
        return 1.0

    total_seconds = (close_dt - open_dt).total_seconds()
    elapsed_seconds = (now_ny - open_dt).total_seconds()
    return max(floor, elapsed_seconds / total_seconds)
