"""
Price data abstraction. Tries Alpaca first (reliable, generous free tier,
real batch requests). If Alpaca isn't configured or a call fails for any
reason, automatically falls back to yfinance for that run so the scan still
completes -- just logs a warning so you know which source was actually used.
"""

import logging
import re
import time as time_module

import pandas as pd

import config

log = logging.getLogger("sp500_scanner")


def chunked(seq, size):
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


_INVALID_SYMBOL_RE = re.compile(r"invalid symbol:\s*([A-Za-z0-9.\-]+)")


def _call_stripping_bad_symbols(batch, call_fn, max_attempts=15):
    """
    Calls call_fn(symbol_list) -> result. Alpaca rejects the ENTIRE request
    if even one symbol in the batch is unrecognized (e.g. class-share tickers
    like BF-B, whose Alpaca-format spelling may differ from the yfinance-style
    spelling this project's ticker list uses). Rather than losing the whole
    batch to the yfinance fallback over one bad symbol, this strips whichever
    symbol Alpaca names as invalid and retries -- so the other 99+ symbols in
    the batch still get served by Alpaca.
    """
    working = list(batch)
    dropped = []

    for _ in range(max_attempts):
        if not working:
            return None, dropped
        try:
            return call_fn(working), dropped
        except Exception as e:
            match = _INVALID_SYMBOL_RE.search(str(e))
            bad_symbol = match.group(1) if match else None
            if bad_symbol and bad_symbol in working:
                working.remove(bad_symbol)
                dropped.append(bad_symbol)
                continue
            raise  # some other error -- let the caller's fallback logic handle it

    log.warning(f"Gave up stripping bad symbols after {max_attempts} attempts; dropped so far: {dropped}")
    return None, dropped


# ---------------------------------------------------------------------------
# ALPACA
# ---------------------------------------------------------------------------

def _alpaca_client():
    from alpaca.data.historical import StockHistoricalDataClient

    if not config.ALPACA_API_KEY or not config.ALPACA_SECRET_KEY:
        raise RuntimeError("Alpaca API keys not configured (ALPACA_API_KEY / ALPACA_SECRET_KEY)")

    return StockHistoricalDataClient(config.ALPACA_API_KEY, config.ALPACA_SECRET_KEY)


def _alpaca_history(tickers, days=None):
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame
    from datetime import datetime, timedelta

    days = days or config.HISTORY_DAYS
    client = _alpaca_client()
    start = datetime.utcnow() - timedelta(days=days * 2)  # buffer for weekends/holidays

    result = {}
    all_dropped = []
    for batch in chunked(tickers, config.BATCH_SIZE):
        def _fetch(symbols):
            req = StockBarsRequest(symbol_or_symbols=symbols, timeframe=TimeFrame.Day, start=start)
            return client.get_stock_bars(req)

        bars, dropped = _call_stripping_bad_symbols(batch, _fetch)
        all_dropped.extend(dropped)

        if bars is None:
            continue
        df_all = bars.df  # MultiIndex (symbol, timestamp)

        if df_all is None or df_all.empty:
            continue

        for t in batch:
            try:
                df_t = df_all.xs(t, level=0).rename(columns={
                    "close": "Close", "volume": "Volume",
                    "open": "Open", "high": "High", "low": "Low",
                })
                if not df_t.empty:
                    result[t] = df_t
            except KeyError:
                continue

        time_module.sleep(0.2)

    if all_dropped:
        log.info(f"Alpaca didn't recognize these symbols (skipped, likely a spelling-convention "
                  f"mismatch for class shares): {sorted(set(all_dropped))}")

    return result


def _alpaca_live_prices(tickers):
    from alpaca.data.requests import StockLatestTradeRequest

    client = _alpaca_client()
    prices = {}
    all_dropped = []
    for batch in chunked(tickers, config.BATCH_SIZE):
        def _fetch(symbols):
            req = StockLatestTradeRequest(symbol_or_symbols=symbols)
            return client.get_stock_latest_trade(req)

        trades, dropped = _call_stripping_bad_symbols(batch, _fetch)
        all_dropped.extend(dropped)

        if trades is None:
            continue
        for t, trade in trades.items():
            prices[t] = float(trade.price)
        time_module.sleep(0.2)

    if all_dropped:
        log.info(f"Alpaca didn't recognize these symbols for live prices (skipped): {sorted(set(all_dropped))}")

    return prices


# ---------------------------------------------------------------------------
# YFINANCE (fallback)
# ---------------------------------------------------------------------------

def _yfinance_history(tickers, days=None):
    import yfinance as yf
    from datetime import datetime, timedelta

    days = days or config.HISTORY_DAYS
    start = datetime.now() - timedelta(days=days)

    result = {}
    for batch in chunked(tickers, config.BATCH_SIZE):
        try:
            data = yf.download(
                tickers=batch,
                start=start.strftime("%Y-%m-%d"),
                interval="1d",
                group_by="ticker",
                threads=config.DOWNLOAD_THREADS,
                progress=False,
                auto_adjust=True,
            )
        except Exception as e:
            log.error(f"yfinance batch download failed: {e}")
            continue

        for t in batch:
            try:
                df = data[t] if len(batch) > 1 else data
                df = df.dropna(how="all")
                if not df.empty:
                    result[t] = df
            except Exception:
                continue

        time_module.sleep(1)

    return result


def _yfinance_live_prices(tickers):
    import yfinance as yf

    prices = {}
    for batch in chunked(tickers, config.BATCH_SIZE):
        try:
            data = yf.download(
                tickers=batch,
                period="1d",
                interval="1m",
                group_by="ticker",
                threads=config.DOWNLOAD_THREADS,
                progress=False,
                auto_adjust=True,
            )
        except Exception as e:
            log.error(f"yfinance live price batch failed: {e}")
            continue

        for t in batch:
            try:
                df = data[t] if len(batch) > 1 else data
                df = df.dropna(how="all")
                if not df.empty:
                    prices[t] = float(df["Close"].iloc[-1])
            except Exception:
                continue

    return prices


# ---------------------------------------------------------------------------
# PUBLIC INTERFACE -- tries Alpaca, falls back to yfinance automatically
# ---------------------------------------------------------------------------

def get_daily_history(tickers, days=None):
    try:
        result = _alpaca_history(tickers, days=days)
        if result:
            log.info(f"[data source: Alpaca] Got history for {len(result)}/{len(tickers)} tickers")
            return result, "alpaca"
        log.warning("Alpaca returned no data -- falling back to yfinance")
    except Exception as e:
        log.warning(f"Alpaca history fetch failed ({e}) -- falling back to yfinance")

    result = _yfinance_history(tickers, days=days)
    log.info(f"[data source: yfinance] Got history for {len(result)}/{len(tickers)} tickers")
    return result, "yfinance"


def get_live_prices(tickers, source_hint=None):
    if source_hint != "yfinance":
        try:
            result = _alpaca_live_prices(tickers)
            if result:
                log.info(f"[data source: Alpaca] Got live prices for {len(result)}/{len(tickers)} tickers")
                return result
            log.warning("Alpaca returned no live prices -- falling back to yfinance")
        except Exception as e:
            log.warning(f"Alpaca live price fetch failed ({e}) -- falling back to yfinance")

    result = _yfinance_live_prices(tickers)
    log.info(f"[data source: yfinance] Got live prices for {len(result)}/{len(tickers)} tickers")
    return result


def get_single_ticker_history(ticker, days, source_hint=None):
    """
    Fetches `days` of daily history for ONE ticker -- used by the dashboard's
    per-company chart endpoint, where requests come in one at a time rather
    than as a full-universe batch. Returns (DataFrame, source_used).
    """
    if source_hint != "yfinance":
        try:
            from alpaca.data.requests import StockBarsRequest
            from alpaca.data.timeframe import TimeFrame
            from datetime import datetime, timedelta

            client = _alpaca_client()
            start = datetime.utcnow() - timedelta(days=days + 10)
            req = StockBarsRequest(symbol_or_symbols=[ticker], timeframe=TimeFrame.Day, start=start)
            bars = client.get_stock_bars(req)
            df_all = bars.df

            if df_all is not None and not df_all.empty:
                df = df_all.xs(ticker, level=0).rename(columns={
                    "close": "Close", "volume": "Volume",
                    "open": "Open", "high": "High", "low": "Low",
                })
                if not df.empty:
                    return df, "alpaca"
            log.warning(f"Alpaca returned no data for {ticker} -- falling back to yfinance")
        except Exception as e:
            log.warning(f"Alpaca single-ticker fetch failed for {ticker} ({e}) -- falling back to yfinance")

    import yfinance as yf
    from datetime import datetime, timedelta

    start = datetime.now() - timedelta(days=days)
    df = yf.download(ticker, start=start.strftime("%Y-%m-%d"), interval="1d", progress=False, auto_adjust=True)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df.dropna(how="all"), "yfinance"


# ---------------------------------------------------------------------------
# INTRADAY (for the strategy engine's FRVP calculations and the 30-Min chart
# timeframe/cascade leg -- not fetched by the old daily-only Bollinger scan)
# ---------------------------------------------------------------------------

def _alpaca_intraday_single(ticker, minutes, days):
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
    from datetime import datetime, timedelta

    client = _alpaca_client()
    start = datetime.utcnow() - timedelta(days=days + 3)  # small buffer for weekends/holidays
    req = StockBarsRequest(symbol_or_symbols=[ticker], timeframe=TimeFrame(minutes, TimeFrameUnit.Minute), start=start)
    bars = client.get_stock_bars(req)
    df_all = bars.df

    if df_all is None or df_all.empty:
        return None
    df = df_all.xs(ticker, level=0).rename(columns={
        "close": "Close", "volume": "Volume", "open": "Open", "high": "High", "low": "Low",
    })
    return df if not df.empty else None


def _yfinance_intraday_single(ticker, minutes, days):
    import yfinance as yf

    # Yahoo caps 30m-interval history at ~60 days -- clamp with a warning
    # rather than erroring, since FRVP/the 30-min cascade only need a much
    # shorter window anyway (see config.MANUAL_REFRESH_INTRADAY_DAYS).
    clamped = min(days, 59)
    if clamped < days:
        log.warning(f"yfinance {minutes}m interval caps history at ~60 days -- "
                    f"clamping {ticker} intraday fetch from {days}d to {clamped}d")

    df = yf.download(ticker, period=f"{clamped}d", interval=f"{minutes}m", progress=False, auto_adjust=True)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.dropna(how="all")
    return df if not df.empty else None


def get_intraday_history(ticker, minutes=30, days=10, source_hint=None):
    """Single-ticker intraday bars -- used for the manual per-ticker Refresh
    (30-min cascade leg + FRVP) and the detail page's 30-Min chart timeframe."""
    if source_hint != "yfinance":
        try:
            df = _alpaca_intraday_single(ticker, minutes, days)
            if df is not None:
                log.info(f"[data source: Alpaca] Got {minutes}m intraday history for {ticker}")
                return df, "alpaca"
            log.warning(f"Alpaca returned no intraday data for {ticker} -- falling back to yfinance")
        except Exception as e:
            log.warning(f"Alpaca intraday fetch failed for {ticker} ({e}) -- falling back to yfinance")

    df = _yfinance_intraday_single(ticker, minutes, days)
    if df is None:
        log.warning(f"[data source: yfinance] No intraday data for {ticker}")
        return pd.DataFrame(), "yfinance"
    log.info(f"[data source: yfinance] Got {minutes}m intraday history for {ticker}")
    return df, "yfinance"


def _alpaca_intraday_batch(tickers, minutes, days):
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
    from datetime import datetime, timedelta

    client = _alpaca_client()
    start = datetime.utcnow() - timedelta(days=days + 3)
    timeframe = TimeFrame(minutes, TimeFrameUnit.Minute)

    result = {}
    all_dropped = []
    for batch in chunked(tickers, config.BATCH_SIZE):
        def _fetch(symbols):
            req = StockBarsRequest(symbol_or_symbols=symbols, timeframe=timeframe, start=start)
            return client.get_stock_bars(req)

        bars, dropped = _call_stripping_bad_symbols(batch, _fetch)
        all_dropped.extend(dropped)

        if bars is None:
            continue
        df_all = bars.df
        if df_all is None or df_all.empty:
            continue

        for t in batch:
            try:
                df_t = df_all.xs(t, level=0).rename(columns={
                    "close": "Close", "volume": "Volume", "open": "Open", "high": "High", "low": "Low",
                })
                if not df_t.empty:
                    result[t] = df_t
            except KeyError:
                continue

        time_module.sleep(0.2)

    if all_dropped:
        log.info(f"Alpaca didn't recognize these symbols for intraday history (skipped): {sorted(set(all_dropped))}")

    return result


def get_intraday_history_batch(tickers, minutes=30, days=10):
    """
    Full-universe intraday fetch for the once-per-trading-day strategy scan's
    FRVP pass. If Alpaca is unavailable, falls back to sequential per-ticker
    yfinance calls -- there's no yfinance batch endpoint for intraday bars,
    so this fallback path is meaningfully slower at ~500-ticker scale.
    """
    try:
        result = _alpaca_intraday_batch(tickers, minutes, days)
        if result:
            log.info(f"[data source: Alpaca] Got {minutes}m intraday history for {len(result)}/{len(tickers)} tickers")
            return result, "alpaca"
        log.warning("Alpaca returned no intraday data for any ticker -- falling back to yfinance (sequential, slow at scale)")
    except Exception as e:
        log.warning(f"Alpaca intraday batch fetch failed ({e}) -- falling back to yfinance (sequential, slow at scale)")

    log.warning(f"Fetching {minutes}m intraday history for {len(tickers)} tickers sequentially via yfinance -- "
                f"no batch endpoint exists for this, so it can take several minutes at S&P 500 scale.")
    result = {}
    for t in tickers:
        df, _ = get_intraday_history(t, minutes=minutes, days=days, source_hint="yfinance")
        if df is not None and not df.empty:
            result[t] = df
    log.info(f"[data source: yfinance] Got {minutes}m intraday history for {len(result)}/{len(tickers)} tickers")
    return result, "yfinance"
