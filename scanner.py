"""
Main entry point. Run this several times a day via cron / Task Scheduler
(currently 7 triggers -- see Task Scheduler task "SP500Scanner").

Drives the Movers tab and alerts using the trend-line + volume-profile
strategy engine (strategy_engine.py) -- see config.py's "STRATEGY ENGINE"
section for the cadence design:

  1. The FULL scan (both methods, the whole S&P 500 universe) runs at the
     two fixed times in config.STRATEGY_SCAN_TIMES_ET each trading day --
     tracked by state_manager's persisted (date, slots_ran), matched within
     a tolerance window rather than assuming a trigger fires at the exact
     second. Each full scan unconditionally sends a phone alert listing the
     current top-5 (alphabetical) BUY signals with entry/stop/target.
  2. Every other scheduled run that day is a cheap PRICE-ONLY refresh: just
     updates the price shown for tickers already on the Movers tab. No
     re-analysis, no news rebuild, no alerts.

(A per-ticker manual "Refresh" -- see webapp/app.py's /api/company/<ticker>/refresh
route -- runs the full method for one ticker on demand, any time, independent
of this daily cadence; it upserts movers.json directly via store.upsert_mover
and never sends a push alert.)
"""

import logging
import os
import sys
from datetime import date

import alerts
import config
import market_hours
import news_summaries
import state_manager
import store
import strategy_engine
import universe

os.makedirs(os.path.join(os.path.dirname(__file__), "logs"), exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(os.path.dirname(__file__), config.LOG_FILE)),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("sp500_scanner")


def run_scan():
    if config.SCAN_PAUSED:
        log.info("Scans paused (config.SCAN_PAUSED=True) -- skipping.")
        return

    if config.RESTRICT_TO_MARKET_HOURS and not market_hours.is_market_hours():
        log.info("Outside market hours -- skipping scan.")
        return

    slot = state_manager.current_scan_slot()
    is_full_scan = slot is not None and not state_manager.already_ran_full_strategy_scan_for_slot(slot)

    if is_full_scan:
        log.info(f"=== Full strategy scan [{slot} slot] (trend-line + volume-profile, full S&P 500 universe) ===")
        tickers = universe.get_sp500_tickers()
        results = strategy_engine.run_full_universe_scan(tickers)
        if not results:
            log.warning("Full strategy scan produced no results (data fetch may have failed) -- "
                        "leaving movers.json untouched; will retry on the next scheduled run today.")
            return
        state_manager.mark_full_strategy_scan_ran_for_slot(slot)
        qualifying = [r for r in results if r.get("passes")]
        log.info(f"Full scan analyzed {len(results)} tickers; {len(qualifying)} passed a method.")

        # Only for tickers actually clearing as BUY (a small set) -- finds
        # the real intraday moment each one crossed its line today, so the
        # alert can say "crossed 10:30 AM" instead of just "seen at this
        # check," which can land well after the actual cross (see EBAY,
        # 2026-09-01).
        strategy_engine.find_crossing_times(results)

        # Snapshot BEFORE recording this run's tickers, so the alert can
        # correctly tell "already seen earlier today" apart from "brand new
        # this check" -- see alerts.build_top5_message.
        seen_today_before = state_manager.get_seen_today()
        for r in results:
            if r.get("recommendation") == "BUY" and r.get("trade_plan"):
                state_manager.mark_seen_today(r["ticker"], r["trade_plan"]["entry"], slot)
    else:
        log.info("=== Price-only refresh (outside a market-analysis slot, or it already ran) ===")
        qualifying = strategy_engine.run_price_only_refresh(store.load_movers().get("companies", []))

    # Always refresh the dashboard's movers list with the CURRENT full set,
    # regardless of whether any of them are "new" since the last text alert --
    # the site should always reflect what's true right now.
    summary = store.build_movers_summary(qualifying)
    last_full_scan_date = date.today().isoformat() if is_full_scan else None
    store.save_movers(qualifying, summary, last_full_scan_date=last_full_scan_date)

    if not is_full_scan:
        log.info("Price-only refresh complete -- prices updated, no news rebuild, no alerts.")
        return

    # Rebuild news summaries (extractive bullets + in-depth extracts) for the
    # tickers the user actually looks at -- their watchlist plus whatever
    # just got flagged. This is the slow part of the scan (fetching and
    # parsing full article pages), which is exactly why it's precomputed
    # here rather than done live when someone clicks into a company.
    try:
        watchlist_tickers = store.load_watchlist()
        mover_tickers = [r["ticker"] for r in qualifying]
        news_summaries.build_and_save(set(watchlist_tickers) | set(mover_tickers))
    except Exception as e:
        log.warning(f"News summary build failed: {e}")

    # Unlike the old dedup'd alert, this fires every time a full scan runs
    # (twice a trading day -- see config.STRATEGY_SCAN_TIMES_ET) with
    # whatever's true RIGHT NOW, including "0 signals" -- a twice-daily
    # market-analysis check-in, not a one-time ping the first time a setup
    # appears. Price-only refreshes never reach this point.
    message = alerts.build_top5_message(results, slot_label=slot, seen_today=seen_today_before)
    log.info(f"Sending alert: {message}")
    alerts.send(message)


if __name__ == "__main__":
    run_scan()
