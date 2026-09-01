"""
Run this once a day (before market open) for a digest covering:
  1. Anything reporting earnings in the next EARNINGS_LOOKAHEAD_DAYS days
  2. General recent news for those same tickers (product launches, guidance,
     analyst notes, etc. -- whatever Finnhub's company-news feed surfaces;
     there's no reliable free way to filter specifically for "product news"
     vs "earnings news" vs anything else, so this is everything recent)
  3. Macro/geopolitical headlines matching config.MACRO_NEWS_KEYWORDS
     (Iran, Fed policy, tariffs, etc. -- see config.py to tune the list)

The text/email alert itself stays a short teaser; the full detail (headlines,
sources) is written to movers.json-adjacent storage the dashboard reads --
see store.py and the /api/digest route in webapp/app.py.
"""

import json
import logging
import os
import sys

import alerts
import config
import earnings_news
import state_manager
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


def _digest_store_path():
    return os.path.join(os.path.dirname(__file__), "digest.json")


def _save_digest(earnings_map, company_news, macro_news):
    payload = {
        "earnings": earnings_map,
        "company_news": company_news,
        "macro_news": macro_news,
    }
    with open(_digest_store_path(), "w") as f:
        json.dump(payload, f, indent=2)


def run_digest():
    if not config.FINNHUB_API_KEY:
        log.warning("FINNHUB_API_KEY not set -- morning digest has nothing to do. Skipping.")
        return

    if state_manager.already_ran_digest_today():
        log.info("Digest already sent today -- skipping.")
        return

    log.info("=== Building morning digest ===")

    tickers = universe.get_sp500_tickers()
    earnings_map = earnings_news.get_upcoming_earnings(tickers)

    company_news = {}
    if config.DIGEST_INCLUDE_GENERAL_COMPANY_NEWS:
        for t in earnings_map:
            items = earnings_news.get_recent_news(t, hours_back=config.NEWS_LOOKBACK_HOURS)
            if items:
                company_news[t] = items

    macro_news = earnings_news.get_macro_news()

    _save_digest(earnings_map, company_news, macro_news)

    message = alerts.build_digest_message(earnings_map, macro_news)
    if message:
        log.info(f"Sending digest teaser: {message}")
        alerts.send(message)
    else:
        log.info("Nothing notable today -- no earnings due, no macro headlines matched. Skipping send.")

    state_manager.mark_digest_ran_today()


if __name__ == "__main__":
    run_digest()
