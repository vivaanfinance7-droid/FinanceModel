# Learning to Trade With This Tool

This document explains what this dashboard does, the trading ideas behind each
feature, and why it was built the way it was. It's written for someone who is
new to investing — every concept is explained from scratch, not assumed.

**This file is kept up to date.** Every time a new feature gets added to the
project, this guide gets a new section explaining it the same way.

---

## What This Is (And Isn't)

This is a personal dashboard that watches the S&P 500 — the 500 largest
publicly traded U.S. companies — and flags stocks that look "stretched,"
meaning their price has moved unusually far from where it's been trading
recently. It does this using a handful of well-known, mechanical technical
indicators (more on what that means below), and it shows you the results in
a web dashboard you can browse.

**This is not financial advice, and nothing here can predict the future.**
Every number in this tool is a calculation from public price, volume, and
news data — not a forecast, not a recommendation, and not a guarantee. Treat
it the way you'd treat a smoke detector: it tells you something is worth a
closer look, not what to do about it. If you're new to investing, please
also read real educational material and consider talking to a licensed
financial advisor before making decisions with real money.

With that said — everything below is genuinely useful to learn, because
these are the same tools professional and everyday traders have used for
decades. Here's how this project uses them, and why.

---

## The Core Idea: Mean Reversion

Most of this tool is built around one idea: **prices tend to wander around
an average, and when they get too far from that average, they often (not
always) drift back toward it.** This is called "mean reversion" — "mean"
just means average.

Picture a dog on a leash, walking next to its owner. The dog wanders left
and right, sometimes pulling hard in one direction — but the leash (the
average) tends to pull it back eventually. Stock prices behave a bit like
that dog: they bounce around a trend, and big departures from that trend
tend to attract attention — bargain hunters if the price dropped
unusually far, or profit-takers if it rose unusually far.

This isn't universally true. Sometimes a stock is genuinely re-rating up or
down because something fundamental changed — a bad earnings report, a
lawsuit, a product breakthrough — and it never "reverts." That's exactly why
this tool doesn't rely on one signal alone. It looks for several different,
independent things to agree before it's worth a look. That's the whole
design philosophy in one sentence: **one signal is a hint, several
agreeing signals are worth your attention.**

---

## The Indicators, Explained

Every indicator below answers a different question about a stock's recent
behavior. None of them "know" anything about the company itself (its
products, its management, its financial health) — they only look at the
numbers: price and volume over time. This is called **technical analysis**,
as opposed to **fundamental analysis** (which studies the actual business —
revenue, profit, debt, competitive position). This tool is entirely
technical; it has no opinion on whether a company is well-run.

### Bollinger Bands — "Is the price unusually stretched?"

This is the primary trigger for everything else in the tool. A Bollinger
Band is built from two ingredients:

1. A **rolling average** of the closing price over some number of days (this
   project uses 50 days by default). "Rolling" means it's recalculated every
   day using the most recent 50 days — like a moving window.
2. The **standard deviation** of price over that same window — a statistical
   measure of how much the price has been bouncing around that average.
   A calmer stock has a small standard deviation; a volatile one has a large
   one.

The bands are drawn at the average, plus and minus 2 standard deviations.
Statistically, if price movements were perfectly random, you'd expect the
price to stay inside those bands about 95% of the time — so when price
actually touches or crosses a band, that's a genuinely unusual event for
*that specific stock*, not an arbitrary line.

- Price at or below the **lower band** → historically an oversold /
  potential-buy zone.
- Price at or above the **upper band** → historically an overbought /
  potential-sell zone.

**The catch:** in a strong trend, a stock can "walk the band" for days —
hugging the upper or lower band without ever reverting. A band touch by
itself is a weak signal. That's why this tool treats it as only the
*trigger*, and requires confirmation from other indicators before it counts
as a real alert (see "How Signals Combine" below).

### RSI (Relative Strength Index) — "How fast has price been moving, and in
which direction?"

RSI is a momentum indicator on a 0–100 scale. It looks at recent up-moves
versus recent down-moves (14 days by default) and boils them into a single
number:

- **Below 30** is traditionally considered "oversold" — the stock has been
  falling fast enough that a bounce becomes more likely.
- **Above 70** is traditionally considered "overbought" — the stock has been
  rising fast enough that a pullback becomes more likely.
- Anywhere in between is considered neutral.

RSI answers a different question than Bollinger Bands do. Bollinger Bands
ask "how far from average is the price, in dollar terms?" RSI asks "how hot
has the recent buying or selling pressure been?" A stock can touch its lower
Bollinger Band while RSI is still neutral (a slow, gentle drift down) or
deeply oversold (a sharp, fast drop) — those are different situations, which
is exactly why using both together is more informative than either alone.

### MACD (Moving Average Convergence/Divergence) — "Is momentum shifting?"

MACD compares two moving averages of price — a fast one (12-day) and a slow
one (26-day) — by subtracting the slow from the fast. When the fast average
is above the slow one, that's generally a bullish (upward) sign; below is
bearish (downward). A third line (the "signal line," a 9-day average of the
MACD line itself) is used to smooth things out, and the difference between
the MACD line and its signal line is called the **histogram**.

This tool uses the histogram's sign as a confirming vote:

- **Positive histogram** → bullish momentum, confirms a BUY signal.
- **Negative histogram** → bearish momentum, confirms a SELL signal.

Think of MACD as answering "is the *trend* of the trend changing?" — it's
slower-moving and less noisy than RSI, which makes it good at confirming
that a move has real follow-through rather than being a one-day blip.

### Volume — "Does anyone actually care about this move?"

Volume is simply how many shares traded. This tool compares today's volume
(projected to a full day, since it checks throughout the trading session —
see "Market Hours Awareness" below) against the 20-day average volume. If
today's volume is running at least 1.5x the recent average, that's treated
as a confirming signal.

The idea: a price move on **unusually high volume** reflects real conviction
— lots of people are actively trading, not just a couple of orders drifting
the price. The same size price move on **thin volume** is much easier to
dismiss or reverse. Volume doesn't have a "direction" of its own (it's not
bullish or bearish by itself) — it's a *confidence* multiplier on whatever
direction the other indicators are already pointing.

### Trendline — "What's the overall direction, at a glance?"

This is the simplest indicator on the dashboard: a straight best-fit line
drawn through the closing prices over whatever time period you're currently
viewing (1 month, 6 months, 1 year, etc.). It's recalculated every time you
change the period. If the line slopes up, the stock has trended up over that
window; if it slopes down, it's trended down. It doesn't predict anything —
it's a fast visual summary of "which way has this actually been going."

### SMA 50/200 Crossover — "Golden Cross" and "Death Cross"

This plots two **simple moving averages** (SMAs) of price: a 50-day average
and a 200-day average. These are two of the most widely-watched lines in all
of finance, because so many traders watch them that the crossovers become
somewhat self-fulfilling:

- **Golden Cross**: the 50-day average crosses *above* the 200-day average —
  a classic, widely-recognized bullish signal, usually meaning a stock has
  transitioned from a longer-term downtrend into an uptrend.
- **Death Cross**: the 50-day average crosses *below* the 200-day average —
  the bearish mirror image.

Unlike RSI or Bollinger Bands, this is a **slow, long-horizon** indicator —
it reacts to months of price history, not days. It's better at identifying
"what kind of market are we in right now" than at timing a specific entry
or exit.

### ATR (Average True Range) — "How much does this stock normally move in a
day?"

ATR measures volatility in dollar terms — roughly, the typical size of a
day's price range over the last 14 days. It doesn't tell you *which
direction* a stock is going; it tells you how much "normal noise" to expect.

Why this matters: a 2% move in a stock that normally moves 0.5% a day is a
big deal. A 2% move in a stock that normally moves 3% a day is unremarkable.
ATR is mainly useful for calibrating expectations and — for people who
actually trade — sizing a stop-loss or price target relative to a stock's
own normal behavior, rather than using the same fixed dollar or percentage
amount for every stock.

---

## How Signals Combine

None of the indicators above are used alone. The logic is:

1. **A Bollinger Band touch is required** — price has to actually reach the
   upper or lower band. This is the trigger.
2. **Confirmations are then checked**: does RSI agree (oversold/overbought
   in the same direction)? Does the MACD histogram agree? Is volume
   unusually high? Each "yes" counts as one confirmation.
3. A signal only becomes an alert once a minimum number of confirmations is
   met (configurable — the default requires at least 1 of the 3).

This filters out a lot of the false positives you'd get from Bollinger Bands
alone. Remember the "walking the band" problem mentioned earlier — a stock
that's genuinely trending can sit at its band for days without reversing.
Requiring agreement from an independent indicator (momentum, or unusual
volume) meaningfully cuts down on those false alarms, though it can never
eliminate them entirely — no combination of technical indicators can.

Each ticker/signal only alerts once per trading day, so you're not re-pinged
six times about the same dip.

---

## The Trend-Line Strategy — Now the Main Signal

Everything above (Bollinger Bands, RSI, MACD, Volume, the Outlook box) still
runs and still powers the individual company detail page. But the Movers tab
and the alerts sent to your phone are now driven by a **different, more
manual-feeling strategy**, learned from trading educators on YouTube and
turned into a repeatable, mechanical process. The idea behind it is old and
simple: draw a line connecting a stock's recent highs or lows, and watch what
price does when it reaches that line.

### Swing points: the "corners" of a price chart

A **swing low** is a point where price stopped falling and turned back up —
the bar's low is lower than the bars on either side of it. A **swing high**
is the mirror image: a point where price stopped rising and turned back down.
These are the natural "corners" of a price chart — the places a human eye is
drawn to when looking for a pattern.

### Drawing the line: support and resistance

Once you have a series of swing lows, you can draw a line connecting them —
angled upward, running underneath the price. As long as price never actually
drops below that line, it's called an **upward trend line**, or **support**:
it's a level the stock has repeatedly bounced off of. The mirror image — a
line connecting swing highs, angled downward, running above the price — is a
**downward trend line**, or **resistance**.

The rule that makes this meaningful (and the reason it's not just eyeballing
a chart) is strict: the line has to connect as many touch points as possible
**without ever having price cross through it**. This dashboard finds that
line mathematically — the tightest possible envelope around the swing points
that price hasn't broken — rather than a human drawing it by hand, but the
concept is exactly the same one traders have used for decades.

### Zooming in: Month, then Week, then Day

A trend line drawn on a full year of monthly candles tells you the big
picture; a line drawn on the last few weeks of daily candles tells you what's
happening right now. Neither view alone is enough — a stock can be in a
multi-year uptrend (bullish on the Month chart) while pulling back sharply
this week (bearish on the Day chart), and knowing both matters.

So the automated scan works top-down: it draws the trend line on **Month**
bars first, then **Week** bars, then **Day** bars — each finer view "handing
off" from the most recent touch point of the coarser one, the way a real
chart gets progressively more detailed as you zoom in. The Day-level line is
what actually triggers a signal. (When you click **Refresh** on a specific
company's page, one more zoom level gets added — **30-Minute** bars — for a
more precise, right-now view of that one stock. This isn't part of the
automatic scan, since fetching that much detail for all 500 companies every
few minutes would be slow and unnecessary.)

### Two ways a line produces a signal: Breakout and Bounce

- **A Bounce** is what happens when price reaches a trend line and turns
  away from it again — the line held. This is read as a **continuation**:
  if price bounces off support, that's a bullish continuation signal (BUY);
  if it bounces off resistance, that's bearish (SELL).
- **A Breakout** is what happens when price actually crosses through a
  trend line that had been holding. This is read as a **reversal**: the
  line that got broken is called the **action line**, and the opposite line
  becomes the **safety line** — the level that, if price falls back past it,
  tells you the breakout has failed. Breaking up through a resistance line
  is bullish (BUY); breaking down through a support line is bearish (SELL).

Either way, the **safety line** (the support/resistance line that's still
holding — the one being bounced off, or the opposite line after a breakout)
is what a stop-loss gets placed just beyond, as explained below.

---

## Fixed Range Volume Profile — A Second, Independent Signal

The second thing the scan checks is completely different from trend lines:
instead of looking at *price*, it looks at *where trading actually happened*.

Every trade happens at some price, and a **volume profile** is just a
histogram of how much trading volume happened at each price level over some
window of time — turned sideways, so it sits next to the price chart. Price
levels where a lot of shares changed hands are called **high volume nodes**;
levels with very little trading are **low volume nodes**.

The single price level with the *most* volume is called the **Point of
Control (POC)** — the level where the most buyers and sellers agreed on a
price. The idea is that a POC represents real, contested interest, so when
price returns to that level later, it often causes some kind of reaction —
either bouncing off it (if it now acts like support or resistance) or
slicing right through it (if the earlier interest has faded). This dashboard
also computes the **Value Area** — the tighter band of prices, around the
POC, that captured about 70% of all the volume in that window — shown for
context on a company's detail page.

**"Fixed Range"** means the profile is built from a specific *past* window
of time, not including today's still-in-progress trading session (today's
volume is incomplete and would skew the picture). This dashboard checks
three fixed windows: the **prior trading day**, the **prior 3 days**, and
the **prior week**. You can turn on one, two, or all three at once on a
company's chart as checkboxes, each drawn in its own color.

### Turning "near the POC" into a direction

Being near a POC by itself doesn't tell you *which way* price is likely to
react — that depends on the bigger picture. This dashboard borrows the same
top-down Month/Week trend-line read described above as a **bias**: if the
higher-timeframe structure looks bullish, a POC below the current price is
read as likely support (a BUY read); if it looks bearish, a POC above the
current price is read as likely resistance (a SELL read). And just like the
trend-line strategy, being "close to" a level isn't itself a trigger — this
dashboard waits for a **confirming candle** (the most recent full day's
candle closing in the expected direction) before treating it as an actual
signal, rather than reacting to mere proximity.

**This part of the guide is now out of date on one important point, kept
here so you can see how the thinking evolved:** for a while, an unconfirmed
volume-profile read that the trend-line method didn't otherwise catch could
still become a BUY or SELL on its own. That's no longer true. After
backtesting real historical outcomes (see "What We Tested and What We
Learned" below), volume-profile-driven signals turned out to perform
meaningfully worse than trend-line-driven ones — badly enough that they were
retired as a source of recommendations entirely. The "Near POC" checkmark,
direction, and confirming-candle read are all still computed and shown, for
context and because they're genuinely interesting — they just no longer
drive what shows up as a BUY or SELL. Only the trend-line method does now.

---

## Turning a Signal Into a Trade Plan (Not Financial Advice)

When either method above produces a BUY or SELL, the dashboard also
calculates a mechanical, no-judgment trade plan: an **entry** price, a
**stop-loss**, a **target**, and a **quantity**. This is entirely arithmetic
— nothing here is a recommendation, and it should be read as "here's what
the math works out to," not "here's what to do."

- **Entry** is simply the current price at the time of the signal.
- **Stop-loss** is placed just beyond whichever line justified the signal —
  the safety line for a trend-line signal, or the confirming candle's high
  or low for a volume-profile signal — with a small buffer so it isn't
  sitting exactly on top of it.
- **Target** is set so the trade's potential reward is **twice** its
  potential risk (a "2:1 reward-to-risk ratio") — if you could lose $1,
  the target is set so you'd gain $2 if it's reached.
- **Quantity** is sized so that if the stop-loss is hit, the loss comes out
  to about **$75** — a fixed risk budget per trade, regardless of which
  stock it is or how expensive its shares are. A stock with a tight stop
  (a small dollar distance to the stop-loss) gets a larger quantity; a
  stock with a wide stop gets a smaller one, so the dollar risk stays
  roughly the same either way. Quantities can be fractional shares (e.g.
  "12.75 shares") to hit that $75 figure precisely, matching how the
  Portfolio tab already tracks fractional holdings.

This is standard, textbook risk management — professional traders use some
version of "risk a fixed amount, aim for a multiple of it back" on nearly
every trade — but it is still just math applied to a signal that could be
wrong. Nothing about a clean-looking entry/stop/target box makes the
underlying signal any more likely to work out.

Two more things get checked before a trend-line signal is trusted enough to
turn into a recommendation at all, both added after backtesting real
historical outcomes:

- **A quality filter (confluence check).** Even a real breakout can be a bad
  trade if it happens after the stock has already run too far, too fast, or
  during freakishly quiet or freakishly wild volatility (a stop-loss doesn't
  mean much if the stock could gap past it in either direction). This check
  looks at the weekly Bollinger Bands and recent ATR history and rejects a
  signal that's already too stretched or in too extreme a volatility regime,
  even if the trend-line break itself was real.
- **A wider stop-loss (the "ATR noise buffer").** The first version of this
  tool placed the stop-loss right up against the safety line, with only a
  small buffer. Backtesting real outcomes showed this was too tight — normal,
  everyday price wiggle was knocking trades out before the actual move had
  time to play out. The stop is now pushed an extra distance away, sized to
  that stock's own ATR, specifically to survive ordinary noise.

---

## Longs Only — No Short Selling

This tool will never recommend betting that a stock will go *down* (a
"short" position). It only ever recommends buying, and later selling at a
target or stop. This was a deliberate choice, not a technical limitation —
and it turned out to be backed up by the data, not just a preference:
backtesting showed long trades (betting on a rise) meaningfully outperformed
short trades (betting on a fall) using this same method, by a wide enough
margin that shorting wasn't worth keeping around. If the trend-line method
would have flagged a SELL, that reading just gets quietly dropped — it
doesn't become a recommendation, though it may still let a *different*,
independent BUY signal through for the same stock if one exists.

---

## Market Regime — Is Today Even a Good Day to Trade?

Before any individual stock's signal is trusted, this tool asks a bigger
question first: **what is the overall stock market doing right now?** It
answers this by running the exact same trend-line technique described above
on the S&P 500 index itself (using the SPY fund as a stand-in), classifying
the broader market as **bullish**, **neutral**, or **bearish**.

This turned out to matter enormously — more than almost anything else
tested. Backtesting real historical outcomes found that this strategy's
individual-stock signals performed well when the overall market was
*neutral or bearish* (roughly a 58-60% win rate), but performed poorly —
close to a coin flip, actually below break-even — when the overall market
was *already bullish*. That's the opposite of the intuitive guess ("the
market's going up, ride the wave"). The likely explanation: when the whole
market is already rallying, individual "breakouts" are more often just
random stocks getting carried along with everything else, not a genuine,
stock-specific signal. When the market itself is flat or pulling back, a
stock breaking its own trend line is a more meaningful, standalone event.

Because of this finding, **the tool now only trusts trend-line signals when
the broader market is NOT already bullish.** On a day the market itself is
bullish, you'll see no confirmed BUY recommendations at all — not because
nothing happened, but because the evidence says nothing that happens on a
day like that is trustworthy enough to act on.

A banner at the top of the Movers tab shows today's read at a glance —
green ("trusted") for neutral/bearish, amber ("not trusted") for bullish.
One convenient fact about this: it's determined entirely by the market's own
already-completed closing prices, so it doesn't change during the trading
day, and doesn't depend on anything happening today. You can check it the
evening before, or first thing before the market opens, and it'll already be
accurate for the day ahead.

---

## Timing: Why "When You Check" Doesn't Change What You See (Mostly)

A natural question: does it matter whether you check this dashboard at 9:30
in the morning versus 2:00 in the afternoon? For whether a trend-line
signal fires, the answer is **no** — and that's deliberate.

Signals are only ever based on a stock's **fully completed** closing price
from the day before, never a live, still-moving intraday price. This
matters because of a well-known trading trap called a **fakeout**: price
spikes past a line for an hour, looks like a real breakout, and then
reverses and closes back on the original side before the day ends. If this
tool reacted to that intraday spike, it would recommend a trade based on a
move that never actually held. Waiting for the day to fully close before
trusting a break is the standard, textbook fix for this — the tradeoff is a
one-day delay: a breakout that happens and holds today is only confirmed and
recommended starting on the *next* check (after today's close, or tomorrow
morning), never the same day it happens.

So checking at 9:30 AM and checking at 2:00 PM the same day will show you
the same set of confirmed recommendations either way — the only thing that
changes with the time of day is the *live price* used for sizing the entry,
since that's a real, moving number.

### The "Watching" Badge — A Heads-Up, Not a Signal

Even with the above, it can be useful to know *something's happening* to a
stock right now, without jumping the gun on it. A dashed gray **"Watching"**
badge shows up next to a stock currently HOLD-rated whose live price is, at
this very moment, testing one of its trend lines intraday — as if today's
close happened right now, it would count as a breakout or bounce.

This is purely informational. It never gets a trade plan, an entry, a stop,
or a target, and it can never turn into a recommendation on its own — it
exists so you can note "keep an eye on this one" and check back after the
close or tomorrow, rather than being surprised by a fresh recommendation you
never saw coming. If the move reverses before the close, the badge just
quietly disappears — nothing was ever entered, so nothing was lost.

---

## The Earnings Badge ("E")

A small yellow **"E"** badge next to a recommended stock means that company
is scheduled to report earnings within the next 7 days. This is shown for
awareness, not as a filter that blocks a trade — a filter that *rejects*
signals near earnings was actually tested, and the evidence for it wasn't
strong enough to justify turning it on.

The reasoning behind flagging it anyway: a stock can gap sharply, in either
direction, the morning after an earnings report — a jump that has nothing to
do with the chart pattern that triggered the trade. That's a different kind
of risk than the ones this tool's math already accounts for (a stop-loss
protects against a *gradual* move against you; it does much less against an
overnight gap straight past it). Worth a quick personal judgment call before
entering, even though the system itself doesn't act on it.

---

## The "Potential Move" Number

On the Movers tab and on each company's detail page, you'll see a number
like "+15.2%" or "-8.7%" next to a stock. **This is not a price prediction.**
It's the mathematical distance, right now, from the current price back to
that stock's rolling average (the same average the Bollinger Bands are
centered on). If a stock is 10% below its average, this shows +10% — the
size of the move *if* it fully reverted to the average, not a promise that
it will.

This number is deliberately separate from **today's price change** (the
plain day-over-day percent move shown near the stock's quote) — those are
two completely different measurements, and it's easy to mix them up at a
glance. "Today's change" tells you what already happened today. "Potential
move to average" tells you how stretched the stock currently is relative to
its own recent history. A stock can be up sharply today (today's change)
while still being far below its 50-day average overall (a large potential
move) — both numbers are true and independent of each other.

---

## Market Hours & Holiday Awareness

The scanner is designed to only do real work while the market is actually
open. It checks the real NYSE trading calendar — not just "is it a weekday"
— so it correctly skips holidays (Thanksgiving, Christmas, etc.) and
correctly handles early-close "half days" (like the day after Thanksgiving,
when the market closes around 1pm instead of 4pm) using the market's real
open/close time for that specific date, rather than assuming every day looks
the same.

This matters for a subtler reason too: volume comparisons ("is today's
volume unusually high?") need to know how much of the trading day has
actually elapsed, so a fair comparison can be made — 45 minutes into the
session shouldn't be judged against a full day's average volume without
adjusting for that.

---

## The Dashboard Tabs

### Watchlist

Companies you've chosen to track yourself, independent of any signal. This
is just a personal list — add any S&P 500 company and its live price/change
shows up here.

### Movers

A table of whatever the trend-line and volume-profile strategies (above)
currently flag — one row per stock, showing its recommendation (BUY/SELL/
HOLD), a checkmark for each method it passed, its current price, and its
mechanical entry/stop/target/quantity if one was generated. A banner at the
top shows today's market regime (see above) before you even look at the
table. Rows are sorted with BUY recommendations first, then HOLD, then SELL
(SELL should never actually appear, since this tool is long-only — see
above); within each group, by how many of the two methods each stock passed.

The full analysis (both methods, the whole S&P 500) only runs **once per
trading day** — it's a meaningfully heavier calculation than the old
Bollinger scan (it needs several years of history and a day's worth of
intraday data per stock), so doing it 6 times a day the way the old scan did
would be wasteful and slow. The other scheduled runs each day just refresh
the displayed **price** for whatever's already on the table — they don't
re-run the analysis or send new alerts. If you want a fresh, full read on
one specific stock without waiting for tomorrow's scan, open its detail page
and click **Refresh** — that re-runs the complete analysis for just that one
stock, right now (and, uniquely, extends the trend-line zoom down to
30-minute bars for a more precise view).

### Portfolio

Your actual real holdings (ticker + share count you own), with live
position values and percent gains over several time windows: day, week,
month, year, and "since I started tracking it here" (a fixed baseline price
captured the first time each holding was added, so that figure accumulates
over time rather than resetting). The bar chart shows all of this at a
glance — bars growing upward are gains, downward are losses, colored
green/red to reinforce direction.

### Compare

Pick any two companies and see their full detail — charts, indicators,
quotes, dividends, everything — side by side, sharing one set of period and
indicator controls so the comparison is apples-to-apples.

### Company Detail Page

Clicking into any stock (from Watchlist, Movers, or Compare) opens a full
view: a candlestick price chart with adjustable indicator overlays, a
Fidelity-style info panel (quote, company profile, dividends, recent
earnings), and a plain-English summary of what each indicator currently
shows. Small "i" info buttons next to each indicator toggle explain what
that indicator means, in case you forget or are seeing it for the first
time.

Above the chart, a **timeframe selector** switches the chart's bar
aggregation between Month, Week, Day, and 30-Minute — this changes what a
single candle *represents* (a whole month vs. a single day), not just how
much history is shown. Toggling **Support/Resistance** overlays the current
timeframe's trend line(s); toggling the **POC** checkboxes overlays one or
more Fixed Range Volume Profile windows as a sideways histogram, with a line
at each window's Point of Control. A **Strategy** box (near the top of the
info column) shows this stock's current trend-line and volume-profile read
in full, plus its trade plan if it has one, with a **Refresh** button to
re-run the complete analysis for just this stock on demand.

---

## The "Outlook" Section — What It Is and Isn't

Each company page has two separate BUY/HOLD/SELL boxes now, and it's worth
being clear about the difference. The **Strategy** box (described above) is
the trend-line + volume-profile read — the one that actually drives the
Movers tab and alerts. The **Outlook** box below it is older and separate:
a mechanical BUY/HOLD/SELL "lean," based on a simple majority vote across
the directional indicators (Bollinger, RSI, MACD, and the SMA crossover) —
plus context like whether earnings are coming up soon, or whether there's
been recent news. It's kept around because it's still a useful, honestly-
labeled second opinion built from a different set of indicators — just no
longer the one that decides what shows up on the Movers tab.

This was deliberately built as a **rule-based tally**, not a prediction. It
is explicitly not able to tell you "the stock will move up X% tomorrow" —
and that's on purpose, not a limitation the tool happens to have. No
mechanical system — this one or any other — can honestly compute a specific
future price move from public data. Any tool that claims to is either
overselling what it does, or quietly gambling with a number it can't really
justify. This tool would rather tell you "3 of 4 signals lean bullish" (true,
verifiable, and exactly as confident as it should be) than invent a
specific number that sounds more precise than it actually is.

---

## Recent News, Summarized

Each company's recent news headlines are shown as short bullet points. If
you click one, a popup shows a longer excerpt and a link to the original
article.

The way this works is worth understanding, because it's a different
approach than the "AI writes you a summary" pattern you might expect. This
tool uses a technique called **extractive summarization** (specifically an
algorithm called TextRank): instead of generating new sentences, it reads
the actual article and picks out the handful of existing sentences that are
most "central" to the piece — the ones most connected to everything else
being said — and shows you those, word for word, in their original order.

The tradeoff: it can't rewrite something complex into simpler language the
way a person (or a language model) could. What you gain in exchange is that
it can **never invent something an article didn't actually say** — every
word you read was written by the original journalist, not generated. For a
tool whose whole design philosophy is "don't claim more certainty than the
data supports," that felt like the right tradeoff.

When an article can't be fetched or read (paywalls and bot-blocking are
common on news sites), it falls back to a short blurb from the news
provider, or just the headline — so you still see *something*, honestly
labeled as less complete rather than silently missing.

---

## Automation

The scanner runs on a schedule (via Windows Task Scheduler) six times during
each trading day, plus once each morning before the market opens for a
digest of upcoming earnings and notable news. You don't need to manually run
anything day to day — alerts arrive as push notifications or texts, and the
dashboard is always showing the latest scan's results whenever you open it.

Of those six runs, only the **first one each trading day** does the full
trend-line + volume-profile analysis (see "The Trend-Line Strategy" above
for why — it's a heavier calculation than the old scan). Which run that is
isn't hardcoded to a specific time of day; the scanner just checks "have I
already done today's full analysis?" and does it on whichever run is first
to ask. The remaining runs that day just refresh prices. (Scans can also be
paused entirely without touching this schedule — see `config.SCAN_PAUSED`
— which stops all scanning, full or price-only, useful if you want the
dashboard to keep showing its last results without your computer doing any
background work.)

---

## What We Tested, and What We Learned

Everything described above as "backed up by backtesting" came from actually
replaying this strategy against years of real historical price data — not
just reasoning about whether an idea *sounds* right. That process turned up
some real findings, and just as importantly, ruled out a lot of ideas that
sounded promising but didn't hold up. Both kinds of result matter, and it's
worth being honest about which is which.

**What held up, after being checked multiple times against fresh data:**

- **Market regime** (described above) — the single biggest factor found.
  Confirmed across several independent tests.
- **Long trades over short trades** — a clear, consistent gap in favor of
  longs, which is why shorting was dropped entirely.
- **The wider ATR-based stop-loss** and the **confluence quality filter** —
  each measurably improved outcomes on repeated testing.
- **Volume-profile signals underperforming trend-line signals badly enough**
  to justify no longer letting them drive recommendations on their own.

**What was tried and did NOT hold up** (each of these sounded reasonable
going in, and each was tested, sometimes more than once, before being set
aside):

- Whether a stock trading unusually quietly right before breaking out (a
  "squeeze") predicts a better outcome — no measurable effect.
- Whether a stock outperforming the broader market recently (relative
  strength) predicts a better outcome — no measurable effect.
- Whether unusually high volume on the breakout day predicts a better
  outcome — inconclusive (this event turned out to be too rare to test
  properly with the data available).
- Whether a trend line with more historical touch points is more reliable —
  no measurable effect.
- Whether multiple stocks in the same industry sector breaking out on the
  same day (rather than just one, alone) predicts a better outcome — this
  one actually looked real and was **briefly turned on**, but a larger,
  more careful re-test showed the effect had been a small-sample coincidence
  all along. It was turned back off.
- Whether recent analyst upgrades/downgrades, or a basic company-profitability
  check, improve stock selection — no measurable effect found so far.
- Whether requiring a stock to also clear a recent horizontal price level (not
  just its diagonal trend line) improves the odds — no measurable effect,
  possibly slightly worse.
- Whether waiting for price to break a line, pull back, and "retest" it
  before entering (a classic technique) would help — this one couldn't
  really be tested at all, because it turned out to almost never happen:
  the signals this tool already generates tend to just run, not offer a
  clean retest opportunity.

The point of listing the failures alongside the successes isn't just
honesty for its own sake — it's a warning against a very real trap called
**overfitting**: if you test enough different ideas, some will look good
purely by chance, the same way flipping enough coins will eventually turn up
ten heads in a row. The only real defense is testing everything against
*fresh* data before trusting it, and being willing to walk something back
(like sector-crowding above) the moment a bigger test contradicts a smaller
one. A method that "sounds smart" is worth exactly nothing until it's
actually been checked against what really happened.

One important, honest consequence of all this: **there is currently no
proven way to rank one of a day's BUY recommendations as better than
another.** Every factor tested so far that tried to do this either showed
nothing, or didn't survive being re-tested. If several stocks are flagged on
the same day, treat them as equally good bets — not a ranked list with a
secret "best" one hiding at the top.

---

## A Simple Way to Decide What to Trade Each Day

Putting all of the above into an actual daily routine:

1. **Check the market regime banner first** — ideally the evening before, or
   first thing before the market opens, since it's already locked in from
   the prior day's close and won't change today. Bullish means don't expect
   (or force) any trades today. Neutral or bearish means it's worth checking
   further once the market opens.
2. **Look at the confirmed BUY list any time during market hours** — the
   exact time you check doesn't change which signals are confirmed, only
   the live entry price.
3. **If there are more than 5, don't hunt for a "best" one** — there isn't a
   proven way to find it (see above). Instead, narrow down using practical,
   non-performance reasons:
   - Skip or deprioritize anything showing the **"E" earnings badge** first.
   - Check the **capital required** for each (entry price × quantity) and
     make sure your total across all picks actually fits comfortably.
   - If still choosing among more than 5, spread across different sectors
     rather than stacking similar companies — a risk-reduction habit, not a
     performance edge.
4. **Take fewer than 5 if fewer than 5 show up.** Don't force a trade just
   to fill a number.
5. **Once entered, let the stop and target do their job.** This isn't a
   day-trading system — trades often take a week or two to resolve. Don't
   expect same-day results.
6. **Treat "Watching" badges as tomorrow's heads-up, not today's action.**
   Acting on one early defeats the entire point of waiting for the close.
7. **Track what actually happens over time** — win, loss, or still open —
   against the backtested win rate, so real results can be honestly compared
   to what the data predicted, rather than just trusted blindly.

---

## A Few Honest Limitations, Worth Knowing

- **Technical indicators describe the past, not the future.** Every number
  on this dashboard is computed from price/volume history that has already
  happened. That history can inform expectations, but it cannot guarantee
  what happens next.
- **All of these indicators can and do disagree with each other**, and with
  what actually happens afterward. That's normal, not a sign something is
  broken.
- **There's a deliberate one-day lag between a real breakout happening and
  this tool telling you about it**, because it waits for the day to fully
  close before trusting the move (see "Timing" above). A genuine breakout
  that happens and holds today won't show up as a recommendation until the
  next check. This is a tradeoff made on purpose, to avoid reacting to
  intraday fakeouts — not an oversight.
- **There's currently no proven way to rank one day's BUY signals against
  each other.** Several ideas for this were tested and none held up (see
  "What We Tested and What We Learned"). Treat every signal on a given day
  as equally good until that changes.
- **This tool has no idea what a company actually does, how healthy its
  business is, or what's about to be announced.** It only reads price,
  volume, and headlines — it's blind to the fundamentals entirely.
- **Extractive news summaries can occasionally read a little oddly out of
  context**, since a sentence pulled from the middle of an article was
  written to sit next to sentences you're not seeing.
- **The trend-line strategy is a mathematical approximation of a manual,
  visual technique.** A human drawing lines on a chart uses judgment this
  dashboard doesn't have — it follows a strict, repeatable rule (the
  tightest line that touches the most swing points without price crossing
  it) every time, which is what makes it automatable, but it will
  occasionally draw a line a discretionary trader wouldn't have.
- **The volume-profile "confirming candle" is a simplification.** The
  original idea (from the trading educators this was learned from) looks
  for a specific reversal candlestick pattern at the level; this dashboard
  checks a simpler stand-in — whether the latest full day's candle closed
  in the expected direction — rather than pattern-matching candle shapes.
- **The $75-risk trade plan is pure arithmetic, not judgment.** It assumes
  the stop-loss placement is correct and that you'll actually place and
  respect that stop. It says nothing about whether the signal itself is a
  good idea, your account size, or diversification across other positions.

None of this makes the tool useless — it makes it exactly what it's meant to
be: a fast, honest, mechanical first pass over a lot of data, so a human
(you) can decide what's actually worth digging into further.
