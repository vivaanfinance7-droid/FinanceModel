"""
Live snapshot of the user's actual holdings: current price, position value,
and percent gain over several trailing windows (day/week/month/year), plus
a persisted "since I started tracking it here" baseline -- captured the
first time a holding is seen and never overwritten, so that figure keeps
comparing against the same fixed starting point rather than a rolling one.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime

import pandas as pd

import config
import data_provider
import indicators
import store

log = logging.getLogger("sp500_scanner")

# Calendar-day lookback per trailing window, matching the convention already
# used by config.CHART_PERIODS elsewhere in this project (e.g. "1M" -> 30).
PERIOD_DAYS = {"day": 1, "week": 7, "month": 30, "year": 365}


def _pct(current, reference):
    if current is None or reference is None or reference == 0:
        return None
    return round((current - reference) / reference * 100, 2)


def _closest_close_on_or_before(closes, anchor_ts, days_ago):
    target = anchor_ts - pd.Timedelta(days=days_ago)
    prior = closes[closes.index <= target]
    if prior.empty:
        return None
    return float(prior.iloc[-1])


def _fetch_history(ticker):
    try:
        df, _source = data_provider.get_single_ticker_history(ticker, config.PORTFOLIO_HISTORY_DAYS)
        return ticker, df
    except Exception as e:
        log.warning(f"Portfolio history fetch failed for {ticker}: {e}")
        return ticker, None


def get_portfolio_snapshot():
    portfolio = store.load_portfolio()
    holdings = portfolio.get("holdings", {})
    baseline = portfolio.get("baseline", {})

    tickers = list(holdings.keys())
    if not tickers:
        return {"updated_at": datetime.now().isoformat(), "total_value": 0.0, "holdings": []}

    live_prices = data_provider.get_live_prices(tickers)

    with ThreadPoolExecutor(max_workers=min(len(tickers), 8)) as pool:
        history_by_ticker = dict(pool.map(_fetch_history, tickers))

    baseline_changed = False
    today_iso = date.today().isoformat()
    rows = []
    total_value = 0.0

    for ticker, shares in holdings.items():
        price = live_prices.get(ticker)
        gains = {period: None for period in PERIOD_DAYS}
        gains["since_baseline"] = None

        if price is not None and ticker not in baseline:
            baseline[ticker] = {"price": price, "date": today_iso}
            baseline_changed = True

        if price is not None and ticker in baseline:
            gains["since_baseline"] = _pct(price, baseline[ticker]["price"])

        df = history_by_ticker.get(ticker)
        if price is not None and df is not None and not df.empty and "Close" in df.columns:
            # Drop a partial "today" bar if present -- same logic the scanner
            # uses -- so trailing windows compare against completed trading
            # days only, not a same-day price double-counted against itself.
            closes = indicators._exclude_partial_today(df["Close"].dropna())
            if len(closes) > 0:
                anchor_ts = closes.index[-1]
                for period, days_ago in PERIOD_DAYS.items():
                    reference = _closest_close_on_or_before(closes, anchor_ts, days_ago)
                    gains[period] = _pct(price, reference)

        value = round(price * shares, 2) if price is not None else None
        if value is not None:
            total_value += value

        rows.append({
            "ticker": ticker,
            "shares": shares,
            "price": price,
            "value": value,
            "gains": gains,
            "baseline_price": baseline.get(ticker, {}).get("price"),
            "baseline_date": baseline.get(ticker, {}).get("date"),
        })

    if baseline_changed:
        portfolio["baseline"] = baseline
        store.save_portfolio(portfolio)

    return {
        "updated_at": datetime.now().isoformat(),
        "total_value": round(total_value, 2),
        "holdings": rows,
    }
