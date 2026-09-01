"""
Fetches and locally caches the current list of S&P 500 tickers (and company
names, for the dashboard's search/autocomplete). Re-downloads at most once
every TICKER_CACHE_MAX_AGE_DAYS to avoid hammering the source and to keep
runs fast.
"""

import json
import logging
import os
from datetime import datetime, timedelta

import pandas as pd

import config

log = logging.getLogger("sp500_scanner")


def _cache_path():
    return os.path.join(os.path.dirname(__file__), config.TICKER_CACHE_FILE)


def _load_cache():
    path = _cache_path()
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r") as f:
            payload = json.load(f)
        fetched_at = datetime.fromisoformat(payload["fetched_at"])
        age = datetime.now() - fetched_at
        if age > timedelta(days=config.TICKER_CACHE_MAX_AGE_DAYS):
            return None
        return payload["companies"]
    except Exception as e:
        log.warning(f"Could not read ticker cache, will refetch: {e}")
        return None


def _save_cache(companies):
    path = _cache_path()
    payload = {"fetched_at": datetime.now().isoformat(), "companies": companies}
    with open(path, "w") as f:
        json.dump(payload, f, indent=2)


def get_sp500_companies(force_refresh=False):
    """
    Returns a list of {"symbol": str, "name": str, "sector": str} for the
    current S&P 500, sorted by symbol. "symbol"/"name" back the dashboard's
    ticker search/autocomplete; "sector" (GICS Sector, free from the same
    source CSV) backs the sector-crowding factor -- see get_sector_map().
    """
    if not force_refresh:
        cached = _load_cache()
        if cached and cached[0].get("sector") is not None:
            log.info(f"Using cached company list ({len(cached)} companies)")
            return cached
        elif cached:
            log.info("Cached company list predates sector data -- refreshing once.")

    log.info(f"Fetching fresh S&P 500 company list from {config.SP500_SOURCE_URL}")
    df = pd.read_csv(config.SP500_SOURCE_URL)

    # yfinance/Alpaca-style symbols use '-' instead of '.' e.g. BRK.B -> BRK-B
    df["Symbol"] = df["Symbol"].str.replace(".", "-", regex=False)
    companies = (
        df[["Symbol", "Security", "GICS Sector"]]
        .rename(columns={"Symbol": "symbol", "Security": "name", "GICS Sector": "sector"})
        .sort_values("symbol")
        .to_dict(orient="records")
    )

    _save_cache(companies)
    log.info(f"Fetched and cached {len(companies)} companies")
    return companies


def get_sector_map(force_refresh=False):
    """Returns {ticker: GICS sector}. Used by the sector-crowding factor
    (see strategy_engine.py) to check how many peers in the same sector
    also have a signal on the same scan."""
    return {c["symbol"]: c["sector"] for c in get_sp500_companies(force_refresh=force_refresh)}


def get_sp500_tickers(force_refresh=False):
    """Returns just the list of ticker symbols (str) -- what the scanner needs."""
    return [c["symbol"] for c in get_sp500_companies(force_refresh=force_refresh)]


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    companies = get_sp500_companies(force_refresh=True)
    print(f"Got {len(companies)} companies. First 5: {companies[:5]}")
