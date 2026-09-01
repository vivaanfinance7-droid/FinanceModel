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
    (date, slots_ran) so the two daily full scans don't collide and a
    holiday/skipped day doesn't carry over stale state. See scanner.py.
    """
    path = os.path.join(os.path.dirname(__file__), config.STRATEGY_STATE_FILE)
    today = date.today().isoformat()

    if not os.path.exists(path):
        return False
    with open(path, "r") as f:
        saved = json.load(f)
    if saved.get("date") != today:
        return False
    return slot in saved.get("slots_ran", [])


def mark_full_strategy_scan_ran_for_slot(slot):
    path = os.path.join(os.path.dirname(__file__), config.STRATEGY_STATE_FILE)
    today = date.today().isoformat()

    saved = {"date": today, "slots_ran": []}
    if os.path.exists(path):
        with open(path, "r") as f:
            existing = json.load(f)
        if existing.get("date") == today:
            saved["slots_ran"] = existing.get("slots_ran", [])

    if slot not in saved["slots_ran"]:
        saved["slots_ran"].append(slot)

    with open(path, "w") as f:
        json.dump(saved, f)


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
