# S&P 500 Multi-Factor Signal Scanner

Scans the S&P 500 six times a day. For each stock it checks whether the price
has touched its 50-day Bollinger Band, then looks for confirmation from RSI,
MACD, and volume before texting you. A separate daily job flags upcoming
earnings reports and recent news for anything you're tracking.

**This is a personal decision-support tool, not financial advice.** Every
alert is a mechanically computed signal from public data — it doesn't know
your risk tolerance, portfolio, or goals. Treat it as a research assistant
that does the tedious scanning for you, not as a recommendation.

---

## Do I need VS Code?

No — VS Code is a code editor, not something the code depends on. What
actually runs this is **Python**, via a terminal. VS Code is just a
convenient place to do that from, since it bundles a terminal and a file
browser in one window. If you already have VS Code, use it; if you'd rather
use Terminal (Mac) / Command Prompt (Windows) directly, that works exactly
the same way — every command below is identical either way.

**Getting started in VS Code, concretely:**
1. Unzip `sp500_bollinger.zip` somewhere on your computer.
2. In VS Code: File -> Open Folder -> select the unzipped `sp500_bollinger` folder.
3. Open a terminal inside VS Code: Terminal -> New Terminal (or `` Ctrl+` ``).
   This opens a real terminal, already pointed at the project folder —
   everything below runs there.
4. Check Python is installed: type `python3 --version`. If that errors,
   install Python from https://python.org first (get 3.10+).
5. Follow steps 1-6 below, typing each command into that terminal.

(Optional but nice: install the "Python" extension in VS Code — Extensions
icon in the left sidebar, search "Python", install Microsoft's official one.
Gives you syntax highlighting and lets you run/debug files with the Run
button instead of the terminal, if you prefer.)

## 1. Install

```bash
cd sp500_bollinger
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## 2. Get your (free) accounts

### Alpaca — price data (primary source)
1. Sign up at https://alpaca.markets (no funding required — the free
   "Basic" market data plan works with a paper-trading account).
2. From the dashboard, generate an API key + secret.
3. Free tier gives you real-time IEX-exchange data and 15-minute-delayed
   full-market data, at 200 requests/minute — plenty for this scanner.
4. If Alpaca is ever unreachable or misconfigured, the scanner automatically
   falls back to yfinance for that run and logs a warning, so it won't just
   silently fail.

### Finnhub — earnings calendar + news (optional but recommended)
1. Sign up at https://finnhub.io (free tier: 60 calls/minute).
2. Grab your API key from the dashboard.
3. If you skip this, the scanner still works — it just won't add earnings
   dates or news headlines to your alerts.

### ntfy — free push notifications (recommended default channel)
1. Install the ntfy app (iOS/Android) or just use a browser at ntfy.sh.
2. Pick a **private, hard-to-guess topic name** (e.g. `sp500-jt-8271`) —
   anyone who knows your topic name can read your alerts, since public
   topics on ntfy.sh aren't authenticated.
3. Subscribe to that topic in the app.
4. No account, no cost, ever.

### Email (optional, free)
If you'd rather get a real email than SMS/push, set `ALERT_METHODS` to include
`"email"` and set `EMAIL_TO` to your inbox address, plus `SMTP_USERNAME` /
`SMTP_PASSWORD` (for Gmail, use an App Password, not your normal password --
generate one at https://myaccount.google.com/apppasswords).

### Twilio — real SMS (optional, ~$1-2/month)
1. Sign up at https://twilio.com, verify your phone number.
2. Buy a phone number (~$1.15/month).
3. Grab your Account SID and Auth Token from the console.
4. Note: AT&T's and T-Mobile's free email-to-text gateways were shut down
   in 2025; Verizon's is being phased out by March 2027. Twilio is the
   reliable paid alternative — a few cents a day covers this use case.

## 3. Configure

Copy `.env.example` to a new file named `.env` (same folder), then open it
and fill in whichever values apply to you — leave the rest blank, those
features/channels just stay disabled:

```bash
cp .env.example .env
```

Then edit `.env` in VS Code (click it in the file browser) and fill in, e.g.:

```
ALPACA_API_KEY=your-key-here
ALPACA_SECRET_KEY=your-secret-here
FINNHUB_API_KEY=your-key-here
NTFY_TOPIC=sp500-yourname-1234
```

`config.py` loads `.env` automatically on every run — no need to `export`
anything in your shell, and it works correctly under cron too (cron doesn't
see variables you manually `export`ed in a terminal, which trips a lot of
people up — the `.env` file sidesteps that entirely). **Never commit or
share your `.env` file** — it holds real credentials.

Then open `config.py` and review:
- `BB_WINDOW` / `BB_NUM_STD` — Bollinger Band period and width
- `RSI_OVERSOLD` / `RSI_OVERBOUGHT`, `MACD_*`, `VOLUME_SPIKE_MULTIPLIER` — confirmation thresholds
- `MIN_CONFIRMATIONS` — how many of {RSI, MACD, Volume} must agree (0-3)
- `ALERT_METHODS` — which channels fire (`["ntfy", "twilio"]` by default)

## 4. Test it once, manually

```bash
python3 scanner.py
python3 morning_digest.py
```

Check `logs/scanner.log` for what happened — it logs every band touch it
saw, even ones that didn't meet the confirmation threshold, so you can
tune `MIN_CONFIRMATIONS` based on real output.

## 5. Run the dashboard

```bash
python3 webapp/app.py
```

Open http://127.0.0.1:5000 in your browser. Two tabs:
- **Watchlist** — companies you add yourself (input box at the top). Persisted in `watchlist.json`.
- **Movers** — whatever the most recent scan flagged, refreshed every scan run (not just the ones that texted you — the dashboard always reflects the current state, texts are deduped separately so you're not spammed). Includes the morning digest's earnings/macro news at the bottom.

Click any company to open its detail page: a candlestick chart with period buttons (1M/3M/6M/1Y/2Y/5Y) like a normal investing site, toggleable indicator overlays (Bollinger/RSI/MACD/Volume), a settings row to change each indicator's own lookback period independent of the chart's display range, a Fidelity-style info panel (quote, company profile, dividends, recent earnings, recent news), and a plain-English summary of what each indicator is currently showing.

The dashboard reads `movers.json` (written by `scanner.py`) and `digest.json` (written by `morning_digest.py`) -- keep the scheduled jobs running so this stays current. Chart/company-detail data is fetched live on each click, not pre-computed.

**Note:** the interpretive summary at the bottom of a company page is rule-based text describing what the indicator values currently show -- not AI-generated commentary, and not financial advice. Treat it as a fast way to read the numbers, not a recommendation.

## 6. Schedule it

### Mac/Linux (cron)
Run `crontab -e` and add (times are Eastern -- see the timezone note below;
the script double-checks market hours itself and exits immediately if the
market's closed, so it's harmless if cron fires slightly early/late or on a
weekend/holiday):

```cron
# Morning digest: 90 minutes before the open, so you see it before the day starts
0  8  * * 1-5  cd /path/to/sp500_bollinger && venv/bin/python morning_digest.py

# Scanner: 6 evenly-spaced checks, 5 min after open to 10 min before close
35 9  * * 1-5  cd /path/to/sp500_bollinger && venv/bin/python scanner.py
50 10 * * 1-5  cd /path/to/sp500_bollinger && venv/bin/python scanner.py
5  12 * * 1-5  cd /path/to/sp500_bollinger && venv/bin/python scanner.py
20 13 * * 1-5  cd /path/to/sp500_bollinger && venv/bin/python scanner.py
35 14 * * 1-5  cd /path/to/sp500_bollinger && venv/bin/python scanner.py
50 15 * * 1-5  cd /path/to/sp500_bollinger && venv/bin/python scanner.py
```

**Timezone matters here.** Cron uses your machine's local system time, but
the market operates on Eastern time. Check your system's timezone with
`timedatectl` (Linux) or `date` (Mac) before entering these lines:
- If your machine's clock is already set to America/New_York: use the times above as-is.
- If it's Pacific: subtract 3 hours (e.g. `35 6 * * 1-5 ...`).
- If it's Central: subtract 1 hour.
- Safest option if unsure: set the system timezone to America/New_York, or
  (on cron implementations that support it) add `CRON_TZ=America/New_York`
  as the first line of your crontab.

### Windows (Task Scheduler)
Create a Basic Task for each run time:
1. Task Scheduler → Create Task → Triggers → New → Daily, set the time,
   repeat weekdays only.
2. Actions → New → Program: `C:\path\to\venv\Scripts\python.exe`,
   Arguments: `scanner.py`, Start in: `C:\path\to\sp500_bollinger`.
3. Repeat for each of the 6 times, plus one daily task for
   `morning_digest.py`.

## How the signal logic works

1. **Bollinger Band touch is the trigger** — price at/below the lower band
   (BUY candidate) or at/above the upper band (SELL candidate).
2. **Confirmations** (each optional, tracked separately):
   - RSI oversold/overbought
   - MACD histogram sign agrees with the direction
   - Volume unusually high vs. the 20-day average (time-of-day adjusted)
3. Alerts only fire once `MIN_CONFIRMATIONS` is met, which filters out a lot
   of the false positives you'd get from Bollinger Bands alone (a stock can
   "walk the band" for days in a strong trend without actually reversing).
4. Each ticker/signal combination only alerts once per trading day — the
   scanner won't text you 6 times about the same AAPL dip.

## Known limitations (be aware of these)

- ~~No market holiday calendar~~ **Fixed** -- `market_hours.py` now uses the
  official NYSE calendar (via `pandas_market_calendars`), so the scanner
  correctly skips holidays and adjusts for early-close (half) days instead
  of assuming a fixed 9:30-16:00 session every weekday.
- **Alpaca's free tier is IEX-only for real-time data** — a single exchange,
  not the full consolidated tape. Good enough for "did this stock move
  meaningfully," not for precise NBBO pricing.
- **Finnhub's earnings calendar isn't filtered server-side** — the scanner
  downloads the whole calendar for the date window and filters locally,
  which is fine at S&P 500 scale but worth knowing.
- **This uses daily bars for the Bollinger Band shape**, checked against a
  live/current price. If you want the bands themselves recalculated from
  true intraday candles, that's a bigger lift — happy to build that next,
  especially if you narrow to a smaller personal watchlist instead of all
  500 (see the intraday-data discussion — Alpaca's free tier handles a
  watchlist of dozens of names easily).
