"""
Configuration for the S&P 500 Bollinger Band Scanner.
Edit the values below to fit your setup. Secrets (Twilio, email password)
should go in environment variables or a local .env file -- see README.md.
"""

import os

from dotenv import load_dotenv

# Loads variables from a .env file in this same folder (if present) into the
# environment. This means: (1) you only set credentials once, in one file,
# instead of re-exporting them in every terminal session, and (2) cron jobs
# work correctly without needing special environment setup -- cron normally
# does NOT see variables you `export`ed in your interactive shell, which is
# a common gotcha. Copy .env.example to .env and fill in your real values.
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

# ---------------------------------------------------------------------------
# BOLLINGER BAND SETTINGS
# ---------------------------------------------------------------------------
BB_WINDOW = 50        # rolling lookback period (days). 20 is the "textbook"
                       # default; 50 (your original idea) reacts more slowly
                       # and flags fewer, more significant extremes.
BB_NUM_STD = 2.0       # number of standard deviations for the bands

# How many days of history to download per ticker. Needs to be comfortably
# larger than BB_WINDOW to get a stable rolling average.
HISTORY_DAYS = BB_WINDOW + 40

# ---------------------------------------------------------------------------
# UNIVERSE
# ---------------------------------------------------------------------------
# Free, actively-maintained CSV of current S&P 500 constituents.
SP500_SOURCE_URL = (
    "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/"
    "master/data/constituents.csv"
)
TICKER_CACHE_FILE = "sp500_tickers.json"
TICKER_CACHE_MAX_AGE_DAYS = 7   # re-fetch the list at most weekly

# ---------------------------------------------------------------------------
# SCAN BEHAVIOR
# ---------------------------------------------------------------------------
# yfinance batch-download settings. Batching in chunks avoids single giant
# requests failing/timing out.
BATCH_SIZE = 100
DOWNLOAD_THREADS = True

# Only run the full scan during regular market hours (America/New_York),
# now including NYSE holiday and early-close awareness via market_hours.py
# (see that module for details). Set to False to allow testing anytime,
# regardless of whether the market is actually open.
RESTRICT_TO_MARKET_HOURS = True

# TEMPORARY off-switch. When True, run_scan() bails out immediately -- no
# network downloads and no indicator math for ~500 tickers -- so the periodic
# scans stop lagging the machine. The market-hours check above is left fully
# intact; this just short-circuits ahead of it. Set back to False to resume.
SCAN_PAUSED = False

# ---------------------------------------------------------------------------
# ADDITIONAL INDICATORS
# ---------------------------------------------------------------------------
# RSI (Relative Strength Index)
RSI_PERIOD = 14
RSI_OVERSOLD = 30      # below this = confirms a BUY
RSI_OVERBOUGHT = 70    # above this = confirms a SELL

# MACD (Moving Average Convergence/Divergence)
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9
# Positive histogram = bullish momentum (confirms BUY), negative = bearish (confirms SELL)

# Volume confirmation: is today's (time-of-day-adjusted) volume unusually high
# vs. the recent average? A band-touch on high volume is a stronger signal.
VOLUME_LOOKBACK = 20
VOLUME_SPIKE_MULTIPLIER = 1.5   # today's projected volume >= 1.5x the 20-day avg

# Minimum number of confirming indicators (RSI, MACD, Volume -- out of 3) required
# on top of the Bollinger Band touch before an alert fires. 0 = alert on every
# band touch (noisiest). 1 is a reasonable default that filters out a lot of
# false positives without being overly strict.
MIN_CONFIRMATIONS = 1

# SMA crossover ("Golden Cross" / "Death Cross") -- dashboard-only indicator,
# fixed at the standard 50/200 definition regardless of the adjustable
# Bollinger window setting.
SMA_CROSSOVER_FAST = 50
SMA_CROSSOVER_SLOW = 200

# ATR (Average True Range) -- dashboard-only volatility measure.
ATR_PERIOD = 14

# ---------------------------------------------------------------------------
# PRICE DATA PROVIDER
# ---------------------------------------------------------------------------
# Tries Alpaca first (free signup, reliable, real batch requests). If Alpaca
# credentials are missing OR a call fails for any reason, automatically falls
# back to yfinance for that run so the scan still completes.
ALPACA_API_KEY = os.environ.get("ALPACA_API_KEY", "")
ALPACA_SECRET_KEY = os.environ.get("ALPACA_SECRET_KEY", "")
ALPACA_PAPER = True   # paper-trading keys work fine for market data, no funding needed

# ---------------------------------------------------------------------------
# NEWS + EARNINGS (Finnhub)
# ---------------------------------------------------------------------------
FINNHUB_API_KEY = os.environ.get("FINNHUB_API_KEY", "")
EARNINGS_LOOKAHEAD_DAYS = 5     # flag earnings reports due within this many days
NEWS_LOOKBACK_HOURS = 24        # only surface news from the last N hours
MAX_NEWS_PER_TICKER = 2         # cap headlines per ticker to keep texts short

# ---------------------------------------------------------------------------
# NEWS SUMMARIZATION (extractive, TextRank -- see text_summarize.py)
# ---------------------------------------------------------------------------
# Rebuilt on every scanner.py run (up to 6x/day) for the tickers the user
# actually looks at (watchlist + current movers) -- fetching and parsing
# full article pages is too slow to do live on a dashboard click, so the
# webapp just reads whatever was precomputed here. Tickers outside that set
# fall back to the existing live headline-only fetch, with no popup.
NEWS_SUMMARIES_FILE = "news_summaries.json"
NEWS_SUMMARY_BULLET_SENTENCES = 2    # sentences shown inline per article
NEWS_SUMMARY_INDEPTH_SENTENCES = 7   # sentences shown in the "read more" popup
ARTICLE_FETCH_TIMEOUT = 12           # seconds, per article page fetch

# ---------------------------------------------------------------------------
# MACRO / GEOPOLITICAL NEWS (morning digest)
# ---------------------------------------------------------------------------
# Finnhub's general news category, filtered locally by keyword match since
# there's no reliable free "is this market-moving geopolitical news" filter.
# This is a blunt instrument -- keyword matching, not real relevance scoring --
# so expect some noise. Tune the list to what you actually care about.
MACRO_NEWS_KEYWORDS = [
    "Iran", "Israel", "war", "conflict", "sanctions", "ceasefire",
    "Federal Reserve", "Fed ", "interest rate", "tariff", "trade war",
    "oil price", "OPEC", "shutdown", "default", "recession",
]
MACRO_NEWS_LOOKBACK_HOURS = 18   # digest runs once/day -- cover since yesterday's digest
MAX_MACRO_NEWS_ITEMS = 5

# Include broader per-company news in the digest (product launches, guidance,
# analyst notes, etc.), not just earnings dates -- for every ticker with
# upcoming earnings AND for every ticker currently on the movers list.
DIGEST_INCLUDE_GENERAL_COMPANY_NEWS = True

# ---------------------------------------------------------------------------
# WEB DASHBOARD
# ---------------------------------------------------------------------------
WEBAPP_HOST = "127.0.0.1"
WEBAPP_PORT = 5000

WATCHLIST_FILE = "watchlist.json"
MOVERS_FILE = "movers.json"          # written by scanner.py after every scan
PROFILE_FILE = "profile.json"        # scaffold for future risk-tolerance / holdings features
PORTFOLIO_FILE = "portfolio.json"    # holdings (ticker -> shares) + per-ticker tracking baseline

# How much daily-bar history to pull per holding for the Portfolio tab's
# week/month/year gain calculations -- comfortably more than a year so the
# year-ago comparison always has data even across weekends/holidays.
PORTFOLIO_HISTORY_DAYS = 400

SITE_TITLE = "Vivaans Dashboard of the S&P 500"

# Chart display range options (like a normal investing site's period buttons)
CHART_PERIODS = {
    "1M": 30, "3M": 90, "6M": 180, "1Y": 365, "2Y": 730, "5Y": 1825,
}
DEFAULT_CHART_PERIOD = "6M"

# Per-indicator lookback options exposed as settings in the UI
BB_WINDOW_OPTIONS = [20, 50, 100, 200]
RSI_PERIOD_OPTIONS = [7, 14, 21]
MACD_PRESETS = {
    "standard": (12, 26, 9),
    "fast": (5, 35, 5),
}
VOLUME_LOOKBACK_OPTIONS = [10, 20, 50]

# How far ahead to look for upcoming earnings when building a company detail
# page's "Outlook" section -- deliberately separate from the scanner/digest's
# own EARNINGS_LOOKAHEAD_DAYS (5) above, since this is a longer, more casual
# "heads up" window for someone browsing the dashboard, not an alert trigger.
OUTLOOK_EARNINGS_LOOKAHEAD_DAYS = 14
# List of channels to send every alert to. Any combination of:
#   "ntfy"       -> free push notification via ntfy.sh (no signup, no cost)
#   "twilio"     -> real SMS via the Twilio API (~$0.008/text + $1.15/mo number)
#   "email"      -> a real email to your inbox via SMTP (free with Gmail etc.)
#   "email_sms"  -> legacy carrier email-to-SMS gateway (mostly dead -- see README)
ALERT_METHODS = ["ntfy", "twilio"]

# The dashboard URL to point people at in the short "check the site" alerts.
DASHBOARD_URL = os.environ.get("DASHBOARD_URL", f"http://127.0.0.1:{5000}")

# --- ntfy settings ---
NTFY_SERVER = os.environ.get("NTFY_SERVER", "https://ntfy.sh")
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "")  # pick a private, hard-to-guess topic name

# --- Twilio settings ---
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")
TWILIO_FROM_NUMBER = os.environ.get("TWILIO_FROM_NUMBER", "")   # e.g. "+15551234567"
ALERT_TO_NUMBER = os.environ.get("ALERT_TO_NUMBER", "")         # your phone, e.g. "+15557654321"

# --- Email-to-SMS settings (legacy, most carriers have discontinued this) ---
SMTP_SERVER = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USERNAME = os.environ.get("SMTP_USERNAME", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
SMS_GATEWAY_ADDRESS = os.environ.get("SMS_GATEWAY_ADDRESS", "")
EMAIL_TO = os.environ.get("EMAIL_TO", "")   # your real inbox, used when "email" is in ALERT_METHODS

# Run the once-a-day earnings/news digest at this local hour (24h, before/at
# market open is typical). Actual timing is controlled by cron -- see README.
DIGEST_STATE_FILE = "digest_state.json"

# ---------------------------------------------------------------------------
# STRATEGY ENGINE (trend-line cascade + Fixed Range Volume Profile) -- this is
# now the MAIN market analysis driving the Movers tab and alerts, replacing
# the Bollinger scan in that role (the Bollinger/RSI/MACD/SMA-crossover/ATR
# settings above are untouched -- they still power the per-ticker detail
# page's Outlook section via chart_data.py/indicators.py).
#
# Cadence: the full scan (both methods, full S&P 500 universe) runs at the
# fixed times listed in STRATEGY_SCAN_TIMES_ET below -- TWICE per trading
# day -- tracked by STRATEGY_STATE_FILE's persisted (date, slots_ran), not by
# assuming a scheduled run fires at exactly that second (see
# state_manager.current_scan_slot -- matches within
# STRATEGY_SCAN_SLOT_TOLERANCE_MINUTES of a configured time). Every other
# scheduled run that day (see the Task Scheduler job's other trigger times)
# is a cheap price-only refresh: updates the price shown on the Movers tab
# for tickers already there, no re-analysis, no alert (see scanner.py).
# A per-ticker manual "Refresh" button (see webapp/app.py) re-runs the full
# method for one ticker on demand, extending the cascade one step further
# (down to 30-minute bars) since that only costs one ticker's intraday fetch.
# ---------------------------------------------------------------------------
STRATEGY_STATE_FILE = "strategy_state.json"   # tracks {"date":..., "slots_ran": [...]}

# The two full-scan ("market analysis") times each trading day, in
# America/New_York local time, 24h "HH:MM". Only a scan that lands within
# STRATEGY_SCAN_SLOT_TOLERANCE_MINUTES of one of these (and hasn't already
# run for that slot today) does the full analysis + sends a phone alert;
# every other scheduled run that day is a silent price-only refresh.
STRATEGY_SCAN_TIMES_ET = ["09:35", "13:45"]
STRATEGY_SCAN_SLOT_TOLERANCE_MINUTES = 10

# Deep daily history so the Monthly/Weekly cascade legs have enough swing
# structure to work with -- separate from HISTORY_DAYS above (still used by
# the detail page's own Bollinger/RSI/MACD indicator calls).
TREND_HISTORY_DAYS = 1825   # ~5 years

# Fractal swing-pivot detection: a bar's low/high must be the lowest/highest
# within k bars on each side to count as a swing point. Monthly only has
# ~60 bars even over 5 years, so k is smaller there than Daily/Weekly.
SWING_K = {"month": 1, "week": 2, "day": 2, "30min": 3}

TREND_TIMEFRAMES_AUTO = ["month", "week", "day"]                # full-universe scan
TREND_TIMEFRAMES_MANUAL = ["month", "week", "day", "30min"]     # manual per-ticker refresh

# How close (as a multiple of ATR) price needs to be to an unbroken trend
# line, while closing back away from it, to count as a BOUNCE.
TRENDLINE_BOUNCE_ATR_MULT = 0.5

# Stop-loss buffer beyond the safety line / POC reaction candle, as a
# fraction of ATR -- gives the stop a little room rather than sitting exactly
# on the line/candle extreme.
STOPLOSS_ATR_BUFFER_MULT = 0.25
# Fallback stop distance (ATR multiple) used only if no safety line exists yet.
STOPLOSS_ATR_FALLBACK_MULT = 1.0

# An additional ATR-based noise buffer applied AFTER the stop above is
# computed, pushing it further away from entry -- stops a stop-loss from
# being clipped by ordinary day-to-day volatility before a correctly-called
# move has time to play out. Made permanent 2026-08-29 after a pooled
# 86-signal paired backtest (5 independent draws, same config each time)
# showed +0.151R expectancy / 38.4% win rate at this stop width, vs. -0.088R
# at the original tight (0.25x-ATR-buffer-only) stop on the same signals --
# a clean, repeated, isolated improvement, not a one-off. 95% CI [28.8%,
# 48.9%] -- still can't rule out a losing system with full confidence, but
# this is the best-supported configuration tested across every method tried.
STOP_NOISE_ATR_MULT = 1.0

# --- Fixed Range Volume Profile ---
FRVP_BIN_COUNT = 25
FRVP_WINDOWS = {
    "prior_day": 1,    # most recent COMPLETED trading day (never today -- see
    "prior_3d": 3,     # volume_profile.py: today's session is still forming,
    "prior_week": 5,   # so including it would skew/flicker the profile)
}
FRVP_PROXIMITY_PCT = 0.002      # 0.2% of price -- "approaching POC" threshold (tightened
                                 # from an initial 0.75% after a live test showed that default
                                 # flagged 55% of the S&P 500 as "approaching" -- normal daily
                                 # price wobble, not a notable event; 0.2% was calibrated against
                                 # real data to a much more selective ~11% per-window hit rate)
FRVP_VALUE_AREA_PCT = 0.70      # standard 70% value-area convention
FRVP_INTRADAY_MINUTES = 30
FRVP_FETCH_DAYS = 10                # full-universe FRVP pass -- cheap, runs once/day
MANUAL_REFRESH_INTRADAY_DAYS = 55   # single-ticker fetch depth (30min cascade leg +
                                     # FRVP both drawn from this); kept under yfinance's
                                     # ~60-day cap on 30-minute interval history

# --- Position sizing / trade plan ("not financial advice") ---
RISK_BUDGET_DOLLARS = 75.0
REWARD_RISK_RATIO = 2.0
TRADE_QTY_DECIMALS = 2   # fractional shares, matches portfolio.json's existing precision

# A stated trading preference, not a performance experiment -- on by default.
# Never recommend entering a SELL/short position; only long entries, exited
# later at a target or stop. A trend-line or POC read that would have been a
# SELL just falls through to HOLD (or to the other method, if it
# independently supports a BUY) rather than being suppressed outright -- see
# strategy_engine.analyze_ticker's long_only_blocks_trend/_poc handling.
LONG_ONLY_MODE = True

# Multi-timeframe Bollinger Band + ATR quality gate on the trend-line signal
# (see strategy_engine._confluence_filter). Made permanent 2026-08-29
# alongside STOP_NOISE_ATR_MULT above -- see that setting's comment for the
# backtest evidence (the two were tested and pooled together as "COMBINED").
CONFLUENCE_FILTER_ENABLED = True
CONFLUENCE_PCTB_MAX = 0.85       # reject a breakout already this far up its Weekly Bollinger Band (or, mirrored, down it for a SELL)
ATR_REGIME_MIN_PCTL = 0.10       # reject if current ATR is below this percentile of its trailing history (too quiet -- likely noise)
ATR_REGIME_MAX_PCTL = 0.90       # reject if above this percentile (too chaotic -- a stop won't hold regardless of placement)
SQUEEZE_LOOKBACK_DAYS = 90       # trailing window used for both the ATR-regime percentile and the squeeze-detection percentile
SQUEEZE_PERCENTILE_MAX = 0.20    # Daily Bollinger Band width in the bottom 20% of its trailing history counts as a "squeeze" (informational bonus, not a gate)

# EXPERIMENTAL, off by default: require elevated volume on the breakout day
# itself (see strategy_engine._breakout_volume_confirmed). Per Bulkowski's
# published breakout research, breakouts on >=50% above-average volume
# succeed far more often than ones on quiet volume.
VOLUME_FILTER_ENABLED = False
BREAKOUT_VOLUME_MULT = 1.5

# Market-regime gating on which signal source is trusted. Made permanent
# 2026-08-29, replacing the old unvalidated/never-enabled REGIME_FILTER_ENABLED
# speculative gate (which only blocked the "fighting a bearish tape" case --
# a reasonable a priori guess that real testing didn't back up).
#
# What actually held up across 3 independent out-of-sample draws this
# session: pooled win rate was 58.3% (n=36) when SPY's own regime was NOT
# already bullish, vs 33.6% (n=131, essentially breakeven) when it was.
# Digging further, the edge in the non-bullish case is concentrated almost
# entirely in trend-line-driven signals specifically -- trend-line +
# non-bullish hit 59.5% (n=37), while POC + non-bullish was the single
# WORST segment found all session (14.3%, n=14). In a bullish regime
# NEITHER method cleared breakeven (trend-line 30.0% n=100, POC 30.2% n=86)
# -- so there's no validated substitute to fall back on there either.
#
# So: trust trend-line signals only, and only when market_regime_bias(SPY)
# is NOT "bullish". POC never drives `recommendation` under this gate --
# poc_check.* is still computed and shown (proximity, direction, reaction
# confirmation all remain visible/useful information), it just isn't
# trusted to pick a trade's direction. See strategy_engine.analyze_ticker.
REGIME_GATED_RECOMMENDATIONS_ENABLED = True

# EXPERIMENTAL stock-SELECTION filters, off by default -- distinct from the
# entry-TIMING filters above (confluence/volume/regime): these ask "is this
# even a good candidate to trade," not "is this the right moment."
#
# Relative strength / momentum factor (see strategy_engine._relative_strength_ok):
# require the stock to be outperforming (BUY) or underperforming (SELL) the
# broader market over the trailing lookback. One of the more robustly
# replicated findings in equity factor research.
RELATIVE_STRENGTH_FILTER_ENABLED = False
RELATIVE_STRENGTH_LOOKBACK_DAYS = 63   # ~3 months, a standard momentum-factor formation window

# Earnings-proximity avoidance (see strategy_engine._earnings_avoidance_ok):
# reject a new signal if the company reports earnings within this many days
# -- entering right before a report means part of the risk is gap risk
# unrelated to the chart pattern. Uses yfinance's earnings-date history
# (Finnhub's free-tier calendar only has current/upcoming dates -- confirmed
# empirically, which would make this unbacktestable).
EARNINGS_AVOIDANCE_FILTER_ENABLED = False
EARNINGS_AVOIDANCE_DAYS = 5

# Display-only "earnings soon" badge (the "E" marker on the Movers tab) --
# separate from the filter above, which stays off since it was never
# validated. This never blocks a recommendation, it just flags it, so it's
# only computed for tickers that already have an active BUY/SELL (a
# handful per scan, not all 500) -- yfinance has no batch endpoint for
# earnings dates, so this stays a per-ticker call, cheap only because the
# recommended set is small.
EARNINGS_BADGE_DAYS = 7

# Analyst estimate-revision momentum (see strategy_engine._analyst_revision_ok):
# net upgrades minus downgrades over the trailing lookback must not clearly
# oppose the signal's direction. Uses yfinance's upgrades_downgrades history
# (real dated records back to 2012) -- Finnhub's recommendation-trend
# endpoint was checked and confirmed to only return ~4 months relative to
# whenever it's queried, not genuine historical snapshots, so it can't be
# used for backtesting this.
ANALYST_REVISION_FILTER_ENABLED = False
ANALYST_REVISION_LOOKBACK_DAYS = 90

# Basic fundamental quality pre-filter (see strategy_engine._fundamental_quality_ok):
# requires the most recently REPORTED quarter (as of the signal's date) to
# show positive EPS, for BUY signals only -- deliberately asymmetric, since
# quality investing (avoid buying unprofitable companies) is a long-side
# concept. Reuses the same yfinance earnings-history data as the earnings-
# avoidance filter above.
QUALITY_FILTER_ENABLED = False

# Sector crowding. Looked strong in 2 small draws (pooled 33.3% n=21 alone
# vs 54.5% n=143 crowded) but did NOT hold up under a 3rd draw (50.0% n=8
# vs 48.7% n=76, no distinguishable gap) or a 4th, much larger 400-signal
# draw (46.7% n=60 vs 49.8% n=323). Pooled across all 4 rounds (631 signals
# total): alone=43.8% n=89 95% CI [34.0%, 54.2%] vs crowded=50.9% n=542 95%
# CI [46.7%, 55.1%] -- the CIs now overlap heavily and the gap that looked
# real at n=29/n=219 has converged toward zero with more data. The 2-3 peer
# gradient (hoped to show "more peers = better") is also just noise: 0=46.7%,
# 1=55.7%, 2=43.8%, 3+=50.3%, no monotonic pattern. Conclusion: the original
# signal was small-sample noise, not a real effect. Disabled 2026-08-31 --
# see strategy_engine._apply_sector_crowding_gate for the (now-inert) gate
# logic, left in place in case a genuinely different crowding definition is
# worth testing later.
SECTOR_CROWDING_FILTER_ENABLED = False

# ---------------------------------------------------------------------------
# LOGGING
# ---------------------------------------------------------------------------
LOG_FILE = "logs/scanner.log"
