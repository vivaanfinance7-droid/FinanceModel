"""
Best-effort fetch + extraction of a news article's main body text from its
URL. Many sites block plain HTTP fetches, sit behind a paywall, or render
their content with JavaScript -- all of that is expected to fail here, not
treated as an error. Callers should always have a fallback (e.g. Finnhub's
own short article summary) for when this returns None.
"""

import logging

import requests
import trafilatura

import config

log = logging.getLogger("sp500_scanner")

# A plain requests.get with no User-Agent gets blocked by a lot of news
# sites outright; a normal browser UA meaningfully improves the success
# rate for sites that don't require JS rendering.
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


def fetch_article_text(url):
    """
    Returns the extracted main body text of the article at `url`, or None
    if it couldn't be fetched or no meaningful article text could be
    extracted (paywall, bot-blocked, JS-rendered page, non-article page).
    """
    if not url:
        return None

    try:
        resp = requests.get(
            url,
            timeout=config.ARTICLE_FETCH_TIMEOUT,
            headers={"User-Agent": _USER_AGENT},
        )
        resp.raise_for_status()
    except Exception as e:
        log.info(f"Article fetch failed for {url}: {e}")
        return None

    try:
        text = trafilatura.extract(resp.text, include_comments=False, include_tables=False)
    except Exception as e:
        log.info(f"Article extraction failed for {url}: {e}")
        return None

    return text or None
