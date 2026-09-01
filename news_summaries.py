"""
Builds richer per-article news summaries -- a short extractive "bullet" and
a longer "in-depth" extract -- for the tickers the user actually looks at
(their watchlist plus whatever the most recent scan flagged). Runs as part
of every scanner.py run (up to 6x/day) since fetching and parsing full
article pages is too slow to do live on a dashboard click; the webapp just
reads the precomputed result from news_summaries.json.

Falls back gracefully to Finnhub's own short article "summary" field (or,
failing that, the headline) whenever the source article can't be fetched or
parsed -- that happens for a lot of sites (paywalls, JS-rendered pages,
bot-blocking, dead links) and is expected, not an error.
"""

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import article_extract
import config
import earnings_news
import store
import text_summarize

log = logging.getLogger("sp500_scanner")


def _summarize_one_article(article):
    headline = article.get("headline", "")
    source = article.get("source", "")
    url = article.get("url", "")
    finnhub_summary = article.get("summary") or ""

    full_text = article_extract.fetch_article_text(url) if url else None

    if full_text and len(full_text.split()) >= 40:
        extracted = text_summarize.summarize_article(full_text)
        bullet = " ".join(extracted["bullet"]) if extracted["bullet"] else (finnhub_summary or headline)
        indepth = extracted["indepth"]
    else:
        bullet = finnhub_summary or headline
        indepth = [finnhub_summary] if finnhub_summary else []

    return {
        "headline": headline,
        "source": source,
        "url": url,
        "bullet": bullet,
        "indepth": indepth,
        "has_indepth": bool(indepth),
    }


def _build_for_ticker(ticker):
    try:
        articles = earnings_news.get_recent_news(
            ticker, hours_back=config.NEWS_LOOKBACK_HOURS, max_items=config.MAX_NEWS_PER_TICKER
        )
    except Exception as e:
        log.warning(f"News fetch failed for {ticker} while building summaries: {e}")
        return ticker, []

    if not articles:
        return ticker, []

    with ThreadPoolExecutor(max_workers=min(len(articles), 4)) as pool:
        results = list(pool.map(_summarize_one_article, articles))
    return ticker, results


def build_and_save(tickers):
    if not config.FINNHUB_API_KEY:
        log.info("FINNHUB_API_KEY not set -- skipping news summary build.")
        return

    tickers = sorted(set(tickers))
    if not tickers:
        log.info("No tickers to build news summaries for.")
        return

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = dict(pool.map(_build_for_ticker, tickers))

    payload = {
        "updated_at": datetime.now().isoformat(),
        "tickers": results,
    }
    store.save_news_summaries(payload)

    article_count = sum(len(v) for v in results.values())
    log.info(f"Built news summaries: {len(results)} tickers, {article_count} articles.")
