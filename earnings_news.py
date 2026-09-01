"""
Earnings calendar + company news via Finnhub's free tier. Used two ways:
  1. scanner.py enriches each BUY/SELL alert with "earnings in N days" and any
     very recent headlines, so the alert has context, not just a signal.
  2. morning_digest.py sends one daily summary of everything reporting
     earnings soon, regardless of whether a Bollinger signal fired.
"""

import logging
from datetime import datetime, timedelta

import requests

import config

log = logging.getLogger("sp500_scanner")

BASE_URL = "https://finnhub.io/api/v1"

# Shared across calls so repeated Finnhub requests reuse a pooled keep-alive
# connection instead of paying a fresh TCP+TLS handshake every time.
_session = requests.Session()


def _get(endpoint, params):
    if not config.FINNHUB_API_KEY:
        raise RuntimeError("FINNHUB_API_KEY not configured")
    params = dict(params)
    params["token"] = config.FINNHUB_API_KEY
    resp = _session.get(f"{BASE_URL}/{endpoint}", params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()


def get_upcoming_earnings(tickers, days_ahead=None):
    """
    Returns {ticker: "YYYY-MM-DD"} for any of `tickers` reporting earnings
    within the next `days_ahead` days. Finnhub's calendar endpoint returns
    ALL companies reporting in the window, so we filter down to our universe.
    """
    days_ahead = days_ahead or config.EARNINGS_LOOKAHEAD_DAYS
    today = datetime.now().date()
    end = today + timedelta(days=days_ahead)

    try:
        data = _get("calendar/earnings", {
            "from": today.isoformat(),
            "to": end.isoformat(),
        })
    except Exception as e:
        log.warning(f"Earnings calendar fetch failed: {e}")
        return {}

    wanted = set(tickers)
    result = {}
    for item in data.get("earningsCalendar", []):
        symbol = item.get("symbol")
        if symbol in wanted and symbol not in result:
            result[symbol] = item.get("date")

    return result


def get_recent_news(ticker, hours_back=None, max_items=None):
    """
    Returns a list of {"headline": str, "source": str, "url": str, "summary": str}
    for `ticker`, limited to the last `hours_back` hours and capped at
    `max_items`. "summary" is Finnhub's own short blurb for the article (not
    always present) -- kept around as a fallback for callers that want a
    summary but can't fetch/parse the full article themselves.
    """
    hours_back = hours_back or config.NEWS_LOOKBACK_HOURS
    max_items = max_items or config.MAX_NEWS_PER_TICKER

    today = datetime.now().date()
    start = today - timedelta(days=2)  # Finnhub's news endpoint is date-granular, not hour-granular

    try:
        data = _get("company-news", {
            "symbol": ticker,
            "from": start.isoformat(),
            "to": today.isoformat(),
        })
    except Exception as e:
        log.warning(f"Company news fetch failed for {ticker}: {e}")
        return []

    cutoff = datetime.now() - timedelta(hours=hours_back)
    items = []
    for article in data:
        ts = article.get("datetime")
        if ts and datetime.fromtimestamp(ts) >= cutoff:
            items.append({
                "headline": article.get("headline", ""),
                "source": article.get("source", ""),
                "url": article.get("url", ""),
                "summary": article.get("summary", ""),
            })
        if len(items) >= max_items:
            break

    return items


def get_macro_news(hours_back=None, max_items=None, keywords=None):
    """
    Pulls Finnhub's general market news category and keeps only headlines
    matching config.MACRO_NEWS_KEYWORDS (case-insensitive substring match).
    This is a blunt keyword filter, not real relevance scoring -- it'll miss
    things phrased unexpectedly and occasionally include false positives.
    """
    hours_back = hours_back or config.MACRO_NEWS_LOOKBACK_HOURS
    max_items = max_items or config.MAX_MACRO_NEWS_ITEMS
    keywords = keywords or config.MACRO_NEWS_KEYWORDS

    try:
        data = _get("news", {"category": "general"})
    except Exception as e:
        log.warning(f"General news fetch failed: {e}")
        return []

    cutoff = datetime.now() - timedelta(hours=hours_back)
    keywords_lower = [k.lower() for k in keywords]

    items = []
    for article in data:
        ts = article.get("datetime")
        if not ts or datetime.fromtimestamp(ts) < cutoff:
            continue
        headline = article.get("headline", "")
        if any(kw in headline.lower() for kw in keywords_lower):
            items.append({
                "headline": headline,
                "source": article.get("source", ""),
            })
        if len(items) >= max_items:
            break

    return items
