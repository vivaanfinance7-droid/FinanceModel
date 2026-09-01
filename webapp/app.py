"""
Local dashboard. Run with `python webapp/app.py` and open http://127.0.0.1:5000
Two views: Movers (what today's scans flagged) and Watchlist (tickers you
add yourself). Click into any company for a chart with adjustable indicators
and timeframe, a Fidelity-style info panel, and a plain-English summary.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import logging
from concurrent.futures import ThreadPoolExecutor

from flask import Flask, jsonify, render_template, request

import chart_data
import company_info
import interpretation
import portfolio_data

import config
import earnings_news
import store
import strategy_engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("sp500_scanner")

app = Flask(__name__)


# ---------------------------------------------------------------------------
# PAGE
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html", site_title=config.SITE_TITLE)


@app.route("/api/companies")
def api_companies():
    """Full S&P 500 symbol+name list, for the watchlist search/autocomplete.
    Fetched once by the frontend and filtered client-side as the user types."""
    import universe
    return jsonify(universe.get_sp500_companies())


# ---------------------------------------------------------------------------
# PROFILE (scaffold for future risk-tolerance / holdings features -- no UI
# uses this yet, but the storage + endpoint shape is ready to build on)
# ---------------------------------------------------------------------------

@app.route("/api/profile", methods=["GET"])
def api_profile_get():
    return jsonify(store.load_profile())


@app.route("/api/profile", methods=["POST"])
def api_profile_post():
    body = request.get_json(force=True, silent=True) or {}
    profile = store.load_profile()
    profile.update(body)
    store.save_profile(profile)
    return jsonify(profile)


# ---------------------------------------------------------------------------
# MOVERS
# ---------------------------------------------------------------------------

@app.route("/api/movers")
def api_movers():
    return jsonify(store.load_movers())


# ---------------------------------------------------------------------------
# GUIDE (TRADING_GUIDE.md, rendered to HTML for the Guide tab -- kept up to
# date manually alongside every new feature; see that file's own header)
# ---------------------------------------------------------------------------

@app.route("/api/guide")
def api_guide():
    import markdown as md_lib

    guide_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "TRADING_GUIDE.md")
    try:
        with open(guide_path, "r", encoding="utf-8") as f:
            raw = f.read()
    except FileNotFoundError:
        return jsonify({"html": "<p>TRADING_GUIDE.md not found.</p>"})

    html = md_lib.markdown(raw, extensions=["extra", "sane_lists", "toc"])
    return jsonify({"html": html})


# ---------------------------------------------------------------------------
# PORTFOLIO (holdings the user actually owns, with live gain figures)
# ---------------------------------------------------------------------------

@app.route("/api/portfolio")
def api_portfolio():
    try:
        return jsonify(portfolio_data.get_portfolio_snapshot())
    except Exception as e:
        log.warning(f"Portfolio snapshot failed: {e}")
        return jsonify({"error": "Failed to load portfolio data"}), 500


# ---------------------------------------------------------------------------
# DIGEST (earnings / company news / macro news from the morning run)
# ---------------------------------------------------------------------------

@app.route("/api/digest")
def api_digest():
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "digest.json")
    if not os.path.exists(path):
        return jsonify({"earnings": {}, "company_news": {}, "macro_news": []})
    with open(path, "r") as f:
        return jsonify(json.load(f))


# ---------------------------------------------------------------------------
# WATCHLIST
# ---------------------------------------------------------------------------

@app.route("/api/watchlist", methods=["GET"])
def api_watchlist_get():
    tickers = store.load_watchlist()
    quotes = []
    for t in tickers:
        try:
            info = company_info.get_company_info(t)
            quotes.append(info)
        except Exception as e:
            log.warning(f"Watchlist quote failed for {t}: {e}")
            quotes.append({"ticker": t, "price": None, "name": None})
    return jsonify({"tickers": tickers, "quotes": quotes})


@app.route("/api/watchlist", methods=["POST"])
def api_watchlist_add():
    body = request.get_json(force=True, silent=True) or {}
    ticker = (body.get("ticker") or "").upper().strip()
    if not ticker:
        return jsonify({"error": "ticker is required"}), 400
    tickers = store.add_to_watchlist(ticker)
    return jsonify({"tickers": tickers})


@app.route("/api/watchlist/<ticker>", methods=["DELETE"])
def api_watchlist_remove(ticker):
    tickers = store.remove_from_watchlist(ticker)
    return jsonify({"tickers": tickers})


# ---------------------------------------------------------------------------
# COMPANY DETAIL (chart + indicators + info panel + interpretation)
# ---------------------------------------------------------------------------

def _safe_company_info(ticker):
    try:
        return company_info.get_company_info(ticker)
    except Exception as e:
        log.warning(f"Company info failed for {ticker}: {e}")
        return {}


def _safe_recent_news(ticker):
    # Prefer the precomputed extractive summaries (bullet + in-depth extract
    # per article) built by the scanner for the user's watchlist/movers --
    # reading a local JSON file is instant, versus fetching+parsing full
    # article pages live on every click. Tickers outside that precomputed
    # set (e.g. an ad-hoc Compare pick) fall back to the existing live
    # headline-only fetch, with no bullet/in-depth fields -- the frontend
    # just shows plain headlines for those, no popup.
    try:
        precomputed = store.load_news_summaries().get("tickers", {}).get(ticker)
        if precomputed:
            return precomputed
    except Exception as e:
        log.warning(f"Failed to read precomputed news summaries for {ticker}: {e}")

    try:
        return earnings_news.get_recent_news(ticker, hours_back=72, max_items=5)
    except Exception as e:
        log.warning(f"News fetch failed for {ticker}: {e}")
        return []


def _movers_entry(ticker):
    """Whatever the strategy engine last found for this ticker (from the
    last full scan or a manual refresh), if it currently qualifies for the
    Movers tab -- None otherwise (most watchlist tickers, most of the time)."""
    try:
        companies = store.load_movers().get("companies", [])
        return next((c for c in companies if c["ticker"] == ticker), None)
    except Exception as e:
        log.warning(f"Movers lookup failed for {ticker}: {e}")
        return None


def _safe_upcoming_earnings(ticker):
    try:
        result = earnings_news.get_upcoming_earnings([ticker], days_ahead=config.OUTLOOK_EARNINGS_LOOKAHEAD_DAYS)
        return result.get(ticker)
    except Exception as e:
        log.warning(f"Upcoming earnings fetch failed for {ticker}: {e}")
        return None


@app.route("/api/company/<ticker>")
def api_company(ticker):
    ticker = ticker.upper().strip()

    period = request.args.get("period", config.DEFAULT_CHART_PERIOD)
    bb_window = request.args.get("bb_window", type=int)
    rsi_period = request.args.get("rsi_period", type=int)
    macd_preset = request.args.get("macd_preset", "standard")
    volume_lookback = request.args.get("volume_lookback", type=int)
    timeframe = request.args.get("timeframe", "day")
    frvp_windows_param = request.args.get("frvp_windows", "")
    frvp_windows = [w for w in frvp_windows_param.split(",") if w] or None

    # Price history and the info/news/earnings calls are all independent of
    # each other -- fire them concurrently instead of one after another so
    # the slow, external-network parts of this request overlap instead of
    # stacking up in sequence. info_f runs unconditionally (it now includes
    # a yfinance-sourced description with no Finnhub dependency, and every
    # Finnhub sub-fetch inside it already degrades independently); news_f
    # and earnings_f stay gated since they have no non-Finnhub fallback.
    with ThreadPoolExecutor(max_workers=4) as pool:
        chart_f = pool.submit(
            chart_data.get_chart_payload,
            ticker,
            period_key=period,
            bb_window=bb_window,
            rsi_period=rsi_period,
            macd_preset=macd_preset,
            volume_lookback=volume_lookback,
            timeframe=timeframe,
            frvp_windows=frvp_windows,
        )
        info_f = pool.submit(_safe_company_info, ticker)
        news_f = pool.submit(_safe_recent_news, ticker) if config.FINNHUB_API_KEY else None
        earnings_f = pool.submit(_safe_upcoming_earnings, ticker) if config.FINNHUB_API_KEY else None

        payload = chart_f.result()
        info = info_f.result()
        news = news_f.result() if news_f else []
        upcoming_earnings_date = earnings_f.result() if earnings_f else None

    if payload is None:
        return jsonify({"error": f"No chart data available for {ticker}"}), 404

    summary_lines = interpretation.build_interpretation(payload, news_items=news)
    outlook = interpretation.build_outlook(payload, news_items=news, upcoming_earnings_date=upcoming_earnings_date)

    return jsonify({
        "chart": payload,
        "info": info,
        "news": news,
        "summary_lines": summary_lines,
        "outlook": outlook,
        "strategy": _movers_entry(ticker),
        "settings": {
            "period_options": list(config.CHART_PERIODS.keys()),
            "bb_window_options": config.BB_WINDOW_OPTIONS,
            "rsi_period_options": config.RSI_PERIOD_OPTIONS,
            "macd_presets": list(config.MACD_PRESETS.keys()),
            "volume_lookback_options": config.VOLUME_LOOKBACK_OPTIONS,
            "timeframe_options": ["month", "week", "day", "30min"],
            "frvp_window_options": [
                {"key": "prior_day", "label": "Prior Day"},
                {"key": "prior_3d", "label": "Prior 3 Days"},
                {"key": "prior_week", "label": "Prior Week"},
            ],
        },
    })


@app.route("/api/company/<ticker>/refresh", methods=["POST"])
def api_company_refresh(ticker):
    """
    Manual per-ticker "Refresh" action: re-runs the full trend-line + FRVP
    strategy for just this ticker (extended to the 30-min cascade leg, since
    it's only one ticker's worth of intraday data), on demand, any time.
    Upserts movers.json but never sends a push alert -- the user is already
    looking at the page. Independent of the once-daily full-scan cadence.
    """
    ticker = ticker.upper().strip()
    try:
        result = strategy_engine.analyze_single_ticker_full(ticker)
    except Exception as e:
        log.warning(f"Manual strategy refresh failed for {ticker}: {e}")
        return jsonify({"error": f"Refresh failed for {ticker}: {e}"}), 500

    store.upsert_mover(ticker, result)
    return jsonify(result)


if __name__ == "__main__":
    app.run(host=config.WEBAPP_HOST, port=config.WEBAPP_PORT, debug=True)
