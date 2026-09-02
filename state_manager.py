"""
Tracks the strategy scan's twice-daily full-scan cadence (see
config.STRATEGY_SCAN_TIMES_ET) and the once-daily morning digest. State
resets automatically at the start of each new trading day.
"""

import json
import os
from datetime import date, datetime

import config
import market_hours


def _strategy_state_path():
    return os.path.join(os.path.dirname(__file__), config.STRATEGY_STATE_FILE)


def _load_strategy_state():
    """
    {"date": "...", "slots_ran": [...], "seen_today": {ticker: {"first_price":..., "first_slot":...}}}
    Resets to a fresh empty shape whenever the stored date isn't today.
    """
    today = date.today().isoformat()
    path = _strategy_state_path()

    if os.path.exists(path):
        with open(path, "r") as f:
            saved = json.load(f)
        if saved.get("date") == today:
            saved.setdefault("slots_ran", [])
            saved.setdefault("seen_today", {})
            return saved

    return {"date": today, "slots_ran": [], "seen_today": {}}


def _save_strategy_state(state):
    with open(_strategy_state_path(), "w") as f:
        json.dump(state, f)


def current_scan_slot():
    """
    Whether "right now" (America/New_York time) falls within
    config.STRATEGY_SCAN_SLOT_TOLERANCE_MINUTES of one of the configured
    full-scan times (config.STRATEGY_SCAN_TIMES_ET). Returns that slot's
    label (e.g. "09:35") if so, else None. Matching by tolerance window
    rather than exact time keeps this robust to a scheduled trigger firing
    a few minutes late.
    """
    now = datetime.now(market_hours.NY_TZ)
    for slot in config.STRATEGY_SCAN_TIMES_ET:
        hh, mm = (int(p) for p in slot.split(":"))
        target = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if abs((now - target).total_seconds()) <= config.STRATEGY_SCAN_SLOT_TOLERANCE_MINUTES * 60:
            return slot
    return None


def already_ran_full_strategy_scan_for_slot(slot):
    """
    Whether the full strategy scan (trend-line + FRVP, full universe) has
    already run today for this particular slot (e.g. "09:35") -- tracked by
    (date, slots_ran) so the daily full scans don't collide and a
    holiday/skipped day doesn't carry over stale state. See scanner.py.
    """
    return slot in _load_strategy_state()["slots_ran"]


def mark_full_strategy_scan_ran_for_slot(slot):
    state = _load_strategy_state()
    if slot not in state["slots_ran"]:
        state["slots_ran"].append(slot)
    _save_strategy_state(state)


def get_seen_today():
    """
    {ticker: {"first_price": float, "first_slot": "09:35"}} for every BUY
    candidate any full scan has found so far today, keyed by the price/slot
    it FIRST appeared at -- used to flag "you've already seen this one
    today" (and how far it's moved since) in the phone alert, so a signal
    that's been running since the morning check doesn't read as fresh at
    1:45. Resets automatically at the start of each new trading day.
    """
    return _load_strategy_state()["seen_today"]


def mark_seen_today(ticker, price, slot):
    """First-seen-wins: does nothing if `ticker` is already recorded today."""
    state = _load_strategy_state()
    if ticker not in state["seen_today"]:
        state["seen_today"][ticker] = {"first_price": price, "first_slot": slot}
        _save_strategy_state(state)


def already_ran_digest_today():
    import json
    import os
    from datetime import date

    path = os.path.join(os.path.dirname(__file__), config.DIGEST_STATE_FILE)
    today = date.today().isoformat()

    if not os.path.exists(path):
        return False
    with open(path, "r") as f:
        saved = json.load(f)
    return saved.get("date") == today


def mark_digest_ran_today():
    import json
    import os
    from datetime import date

    path = os.path.join(os.path.dirname(__file__), config.DIGEST_STATE_FILE)
    with open(path, "w") as f:
        json.dump({"date": date.today().isoformat()}, f)
