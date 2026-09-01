"""
Simple JSON-file storage shared between the scanner/digest scripts (writers)
and the web dashboard (reader) -- movers.json and watchlist.json.
No database needed at this scale; last-write-wins is fine for a single-user
personal tool.
"""

import json
import os
from datetime import datetime

import config


def _path(filename):
    return os.path.join(os.path.dirname(__file__), filename)


# ---------------------------------------------------------------------------
# MOVERS (written by scanner.py after every scan, and by the manual per-
# ticker Refresh action; read by the dashboard). Driven by the trend-line +
# volume-profile strategy engine (strategy_engine.py) -- see that module for
# what a "result" dict looks like.
# ---------------------------------------------------------------------------

def _passed_count(row):
    return int(row["trend_line_check"]["passes"]) + int(row["poc_check"]["approaching"])


_RECOMMENDATION_RANK = {"BUY": 0, "HOLD": 1, "SELL": 2}


def _recommendation_rank(row):
    """BUY rows first, then HOLD, then SELL -- actionable-to-take-now
    ordering. SELL should be rare/absent in practice while LONG_ONLY_MODE
    is on, but the ordering stays correct either way."""
    return _RECOMMENDATION_RANK.get(row["recommendation"], 1)


def _company_row(result, name_by_ticker):
    ticker = result["ticker"]
    return {
        "ticker": ticker,
        "name": name_by_ticker.get(ticker, ticker),
        "recommendation": result["recommendation"],
        "price": result["price"],
        "earnings_soon": result.get("earnings_soon", False),
        "higher_tf_bias": result["higher_tf_bias"],
        "trend_line_check": result["trend_line_check"],
        "poc_check": result["poc_check"],
        "trade_plan": result["trade_plan"],
        "last_full_analysis_at": result["last_full_analysis_at"],
        "last_price_refresh_at": result["last_price_refresh_at"],
    }


def _name_lookup():
    from universe import get_sp500_companies  # lazy import -- avoids import-order coupling
    return {c["symbol"]: c["name"] for c in get_sp500_companies()}


def save_movers(results, summary_text, last_full_scan_date=None):
    """
    results: list of strategy_engine.analyze_ticker()-shaped dicts that
    passed at least one method. Sorted BUY first, then HOLD, then SELL;
    within each group, by how many of the two methods passed (both before
    one), then alphabetically.

    last_full_scan_date: pass only when this save follows a FULL scan --
    the cheap price-only runs the rest of the day omit it, which preserves
    whatever date was already recorded (the actual cadence source of truth
    is state_manager's strategy_state.json; this mirrors it for display).
    """
    name_by_ticker = _name_lookup()
    companies = [_company_row(r, name_by_ticker) for r in results]
    companies.sort(key=lambda c: (_recommendation_rank(c), -_passed_count(c), c["ticker"]))

    existing = load_movers()
    # Every row in a batch scan shares the same market_bias (computed once
    # from SPY, reused across every ticker) -- read it off any row rather
    # than re-fetching SPY here. Determined entirely by SPY's own prior
    # closes, so this is knowable the moment the PREVIOUS day closes, not
    # something that develops during the day itself.
    market_regime = companies[0]["trend_line_check"]["market_bias"] if companies else existing.get("market_regime", "unknown")
    payload = {
        "updated_at": datetime.now().isoformat(),
        "last_full_scan_date": last_full_scan_date or existing.get("last_full_scan_date"),
        "market_regime": market_regime,
        "summary": summary_text,
        "companies": companies,
    }
    with open(_path(config.MOVERS_FILE), "w") as f:
        json.dump(payload, f, indent=2)
    return payload


def upsert_mover(ticker, result):
    """
    Used by the manual per-ticker Refresh action: replaces/inserts/removes
    just that one row (based on whether it currently passes either method),
    without touching the batch-scan-only top-level fields (updated_at/
    summary/last_full_scan_date) or sending an alert.
    """
    data = load_movers()
    companies = [c for c in data.get("companies", []) if c["ticker"] != ticker]

    if result.get("passes"):
        companies.append(_company_row(result, _name_lookup()))

    companies.sort(key=lambda c: (_recommendation_rank(c), -_passed_count(c), c["ticker"]))
    data["companies"] = companies

    with open(_path(config.MOVERS_FILE), "w") as f:
        json.dump(data, f, indent=2)
    return data


def load_movers():
    path = _path(config.MOVERS_FILE)
    if not os.path.exists(path):
        return {"updated_at": None, "last_full_scan_date": None, "market_regime": "unknown",
                "summary": "No scan has run yet.", "companies": []}
    with open(path, "r") as f:
        data = json.load(f)
    data.setdefault("last_full_scan_date", None)
    data.setdefault("market_regime", "unknown")
    data.setdefault("companies", [])
    return data


def build_movers_summary(results):
    if not results:
        return ("No tickers are currently showing a trend-line signal or approaching a "
                "tracked volume-profile level.")

    buys = sum(1 for r in results if r["recommendation"] == "BUY")
    sells = sum(1 for r in results if r["recommendation"] == "SELL")
    holds = sum(1 for r in results if r["recommendation"] == "HOLD")

    parts = []
    if buys:
        parts.append(f"{buys} BUY")
    if sells:
        parts.append(f"{sells} SELL")
    if holds:
        parts.append(f"{holds} HOLD (volume-profile watch only)")

    return f"{', '.join(parts)} out of {len(results)} flagged."


# ---------------------------------------------------------------------------
# WATCHLIST (read/written by the dashboard; user-managed, unrelated to signals)
# ---------------------------------------------------------------------------

def load_watchlist():
    path = _path(config.WATCHLIST_FILE)
    if not os.path.exists(path):
        return []
    with open(path, "r") as f:
        return json.load(f).get("tickers", [])


def save_watchlist(tickers):
    with open(_path(config.WATCHLIST_FILE), "w") as f:
        json.dump({"tickers": tickers}, f, indent=2)


def add_to_watchlist(ticker):
    tickers = load_watchlist()
    ticker = ticker.upper().strip()
    if ticker not in tickers:
        tickers.append(ticker)
        save_watchlist(tickers)
    return tickers


def remove_from_watchlist(ticker):
    tickers = load_watchlist()
    ticker = ticker.upper().strip()
    tickers = [t for t in tickers if t != ticker]
    save_watchlist(tickers)
    return tickers


# ---------------------------------------------------------------------------
# PORTFOLIO (holdings the user actually owns -- ticker -> share count -- plus
# a per-ticker "baseline" price/date captured the first time that ticker is
# seen, so the dashboard can show gain since tracking started, not just the
# usual trailing day/week/month/year windows.)
# ---------------------------------------------------------------------------

def load_portfolio():
    path = _path(config.PORTFOLIO_FILE)
    if not os.path.exists(path):
        return {"holdings": {}, "baseline": {}}
    with open(path, "r") as f:
        data = json.load(f)
    data.setdefault("holdings", {})
    data.setdefault("baseline", {})
    return data


def save_portfolio(data):
    with open(_path(config.PORTFOLIO_FILE), "w") as f:
        json.dump(data, f, indent=2)


# ---------------------------------------------------------------------------
# NEWS SUMMARIES (written by scanner.py after every scan; read by the
# dashboard instead of live-fetching + parsing articles on each click)
# ---------------------------------------------------------------------------

def load_news_summaries():
    path = _path(config.NEWS_SUMMARIES_FILE)
    if not os.path.exists(path):
        return {"updated_at": None, "tickers": {}}
    with open(path, "r") as f:
        data = json.load(f)
    data.setdefault("tickers", {})
    return data


def save_news_summaries(data):
    with open(_path(config.NEWS_SUMMARIES_FILE), "w") as f:
        json.dump(data, f, indent=2)


# ---------------------------------------------------------------------------
# PROFILE -- scaffold for future risk-tolerance / holdings / asset-management
# features. Nothing in the UI reads or writes this yet; it exists so those
# features have a storage shape and API to build on without a backend rework.
# ---------------------------------------------------------------------------

_DEFAULT_PROFILE = {
    "risk_tolerance": None,   # future: "conservative" / "moderate" / "aggressive"
    "holdings": [],           # future: [{"ticker": "AAPL", "shares": 10, "cost_basis": 150.0}]
    "notes": "",
}


def load_profile():
    path = _path(config.PROFILE_FILE)
    if not os.path.exists(path):
        return dict(_DEFAULT_PROFILE)
    with open(path, "r") as f:
        saved = json.load(f)
    return {**_DEFAULT_PROFILE, **saved}  # merges in any fields added to the default later


def save_profile(profile):
    with open(_path(config.PROFILE_FILE), "w") as f:
        json.dump(profile, f, indent=2)
