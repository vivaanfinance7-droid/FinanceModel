"""
Fetches the "Fidelity-style" side panel data for a company: current quote,
$ and % change, basic company profile, dividend yield, and recent earnings
history. All via Finnhub's free tier -- gracefully degrades to nulls (shown
as "N/A" in the UI) for anything the free tier doesn't cover for a given
ticker, rather than failing the whole page.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
from concurrent.futures import ThreadPoolExecutor

import earnings_news  # reuses its Finnhub _get() helper and API key check

log = logging.getLogger("sp500_scanner")


def _fetch_quote(ticker):
    try:
        return earnings_news._get("quote", {"symbol": ticker})
    except Exception as e:
        log.warning(f"Quote fetch failed for {ticker}: {e}")
        return {}


def _fetch_profile(ticker):
    try:
        return earnings_news._get("stock/profile2", {"symbol": ticker})
    except Exception as e:
        log.warning(f"Profile fetch failed for {ticker}: {e}")
        return {}


def _fetch_metrics(ticker):
    try:
        return earnings_news._get("stock/metric", {"symbol": ticker, "metric": "all"}).get("metric", {})
    except Exception as e:
        log.warning(f"Metrics fetch failed for {ticker}: {e}")
        return {}


def _fetch_earnings(ticker):
    try:
        data = earnings_news._get("stock/earnings", {"symbol": ticker})
        return data[:4] if isinstance(data, list) else []
    except Exception as e:
        log.warning(f"Earnings history fetch failed for {ticker}: {e}")
        return []


def _fetch_description(ticker):
    # yfinance, not Finnhub -- Finnhub's free-tier stock/profile2 has no text
    # description field. yfinance's .info is heavier/slower than a plain quote
    # call and occasionally flaky, so this degrades to None like every other
    # sub-fetch here rather than failing the whole page.
    try:
        import yfinance as yf
        return yf.Ticker(ticker).info.get("longBusinessSummary") or None
    except Exception as e:
        log.warning(f"Description fetch failed for {ticker}: {e}")
        return None


def get_company_info(ticker):
    # These 5 fetches are independent of each other -- fire them concurrently
    # instead of one after another so the wall-clock cost is roughly the
    # slowest single call instead of the sum of all 5.
    with ThreadPoolExecutor(max_workers=5) as pool:
        quote_f = pool.submit(_fetch_quote, ticker)
        profile_f = pool.submit(_fetch_profile, ticker)
        metrics_f = pool.submit(_fetch_metrics, ticker)
        earnings_f = pool.submit(_fetch_earnings, ticker)
        description_f = pool.submit(_fetch_description, ticker)

        quote = quote_f.result()
        profile = profile_f.result()
        metrics = metrics_f.result()
        recent_earnings = earnings_f.result()
        description = description_f.result()

    return {
        "ticker": ticker,
        "price": quote.get("c"),
        "change": quote.get("d"),
        "change_percent": quote.get("dp"),
        "previous_close": quote.get("pc"),
        "day_high": quote.get("h"),
        "day_low": quote.get("l"),
        "name": profile.get("name"),
        "industry": profile.get("finnhubIndustry"),
        "exchange": profile.get("exchange"),
        "market_cap_millions": profile.get("marketCapitalization"),
        "logo": profile.get("logo"),
        "website": profile.get("weburl"),
        "dividend_yield_pct": metrics.get("dividendYieldIndicatedAnnual") or metrics.get("currentDividendYieldTTM"),
        "eps_ttm": metrics.get("epsTTM"),
        "pe_ttm": metrics.get("peTTM"),
        "week_52_high": metrics.get("52WeekHigh"),
        "week_52_low": metrics.get("52WeekLow"),
        "description": description,
        "recent_earnings": [
            {
                "period": e.get("period"),
                "eps_actual": e.get("actual"),
                "eps_estimate": e.get("estimate"),
                "surprise_percent": e.get("surprisePercent"),
            }
            for e in recent_earnings
        ],
    }
