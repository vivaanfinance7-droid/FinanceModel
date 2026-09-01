"""
Generates the plain-English "what are the indicators telling me" summary
shown at the bottom of a company's page. Deliberately rule-based and
deterministic (not AI-generated prose) -- it mechanically describes what
the numbers show, which is a better fit for a tool that's explicitly not
meant to act as a financial advisor.
"""


def _bollinger_text(bb, close_price, period_label):
    if not bb["upper"] or bb["upper"][-1] is None or close_price is None:
        return f"Not enough {period_label} history to compute a {bb['window']}-day Bollinger Band."

    upper, lower = bb["upper"][-1], bb["lower"][-1]
    window = bb["window"]

    if close_price <= lower:
        return (f"Looking at the {window}-day Bollinger Bands over the {period_label} view, price "
                f"(${close_price:.2f}) is at or below the lower band (${lower:.2f}) -- historically "
                f"an oversold / potential-buy zone.")
    if close_price >= upper:
        return (f"Looking at the {window}-day Bollinger Bands over the {period_label} view, price "
                f"(${close_price:.2f}) is at or above the upper band (${upper:.2f}) -- historically "
                f"an overbought / potential-sell zone.")

    pct = (close_price - lower) / (upper - lower) * 100 if upper != lower else 50
    return (f"Looking at the {window}-day Bollinger Bands over the {period_label} view, price sits "
            f"inside the bands (about {pct:.0f}% of the way from lower to upper) -- no extreme "
            f"reading in either direction right now.")


def _rsi_text(rsi):
    val = rsi["values"][-1] if rsi["values"] else None
    if val is None:
        return f"Not enough history to compute the {rsi['period']}-day RSI."

    period = rsi["period"]
    if val <= rsi["oversold"]:
        return f"The {period}-day RSI is at {val:.0f}, in oversold territory (below {rsi['oversold']})."
    if val >= rsi["overbought"]:
        return f"The {period}-day RSI is at {val:.0f}, in overbought territory (above {rsi['overbought']})."
    return f"The {period}-day RSI is at {val:.0f}, a neutral reading (between {rsi['oversold']} and {rsi['overbought']})."


def _macd_text(macd):
    hist = macd["histogram"][-1] if macd["histogram"] else None
    if hist is None:
        return "Not enough history to compute MACD."

    if hist > 0:
        return f"MACD ({macd['preset']} settings) is positive at {hist:.2f}, suggesting bullish momentum."
    if hist < 0:
        return f"MACD ({macd['preset']} settings) is negative at {hist:.2f}, suggesting bearish momentum."
    return f"MACD ({macd['preset']} settings) is essentially flat, suggesting no clear momentum either way."


def _volume_text(volume, volume_avg):
    latest = volume[-1] if volume else None
    avg = volume_avg["values"][-1] if volume_avg["values"] else None
    window = volume_avg["window"]

    if not latest or not avg:
        return f"Not enough history to compute the {window}-day average volume."

    ratio = latest / avg
    if ratio >= 1.5:
        return f"Volume is running about {ratio:.1f}x the {window}-day average -- unusually high activity."
    if ratio <= 0.5:
        return f"Volume is running about {ratio:.1f}x the {window}-day average -- unusually quiet."
    return f"Volume is about {ratio:.1f}x the {window}-day average -- fairly normal activity."


def _trendline_text(trendline, period_label):
    values = (trendline or {}).get("values") or []
    valid = [v for v in values if v is not None]
    if len(valid) < 2:
        return f"Not enough {period_label} history to fit a trendline."

    start, end = valid[0], valid[-1]
    if start == 0:
        return f"Not enough price variation over the {period_label} view to describe a trendline direction."

    pct = (end - start) / abs(start) * 100
    if pct > 1:
        return (f"The trendline over the {period_label} view slopes upward, gaining about {pct:.1f}% "
                f"end-to-end -- an overall uptrend.")
    if pct < -1:
        return (f"The trendline over the {period_label} view slopes downward, losing about {abs(pct):.1f}% "
                f"end-to-end -- an overall downtrend.")
    return f"The trendline over the {period_label} view is essentially flat -- no clear up or down drift."


def _sma_crossover_text(sma):
    fast_window = sma.get("fast_window")
    slow_window = sma.get("slow_window")
    pairs = [(f, s) for f, s in zip(sma.get("fast") or [], sma.get("slow") or []) if f is not None and s is not None]

    if not pairs:
        return f"Not enough history to compute the {fast_window}/{slow_window}-day moving average crossover."

    recent = pairs[-10:] if len(pairs) >= 10 else pairs
    cur_fast, cur_slow = pairs[-1]
    cur_sign = cur_fast > cur_slow
    crossed = any((f > s) != cur_sign for f, s in recent[:-1])

    if crossed and cur_sign:
        return (f"A 'Golden Cross' recently occurred -- the {fast_window}-day average (${cur_fast:.2f}) crossed "
                f"above the {slow_window}-day average (${cur_slow:.2f}), a classic bullish trend-following signal.")
    if crossed and not cur_sign:
        return (f"A 'Death Cross' recently occurred -- the {fast_window}-day average (${cur_fast:.2f}) crossed "
                f"below the {slow_window}-day average (${cur_slow:.2f}), a classic bearish trend-following signal.")
    if cur_sign:
        return (f"The {fast_window}-day average (${cur_fast:.2f}) is above the {slow_window}-day average "
                f"(${cur_slow:.2f}), consistent with an established uptrend.")
    return (f"The {fast_window}-day average (${cur_fast:.2f}) is below the {slow_window}-day average "
            f"(${cur_slow:.2f}), consistent with an established downtrend.")


def _atr_text(atr, close_price):
    values = (atr or {}).get("values") or []
    val = values[-1] if values else None
    period = (atr or {}).get("period")

    if val is None or not close_price:
        return f"Not enough history to compute the {period}-day ATR." if period else "Not enough history to compute ATR."

    pct_of_price = val / close_price * 100
    return (f"The {period}-day ATR (Average True Range) is ${val:.2f} (about {pct_of_price:.1f}% of the current "
            f"price) -- a rough measure of typical daily price movement, useful for sizing stop-losses or price "
            f"targets rather than predicting direction.")


def _tally_lean(chart_payload, close_price):
    """
    Directional lean per indicator, for the bottom-line tally. Volume is
    deliberately excluded from the vote -- it has no direction of its own,
    it just says whether a move is unusually active or quiet, so it's used
    as a confidence note instead (see _bottom_line_text).
    """
    votes = []
    bb = chart_payload["bollinger"]
    rsi = chart_payload["rsi"]
    macd = chart_payload["macd"]

    if close_price is not None and bb["upper"] and bb["upper"][-1] is not None:
        if close_price <= bb["lower"][-1]:
            votes.append(("Bollinger", "bullish"))
        elif close_price >= bb["upper"][-1]:
            votes.append(("Bollinger", "bearish"))
        else:
            votes.append(("Bollinger", "neutral"))

    if rsi["values"] and rsi["values"][-1] is not None:
        val = rsi["values"][-1]
        if val <= rsi["oversold"]:
            votes.append(("RSI", "bullish"))
        elif val >= rsi["overbought"]:
            votes.append(("RSI", "bearish"))
        else:
            votes.append(("RSI", "neutral"))

    if macd["histogram"] and macd["histogram"][-1] is not None:
        hist = macd["histogram"][-1]
        if hist > 0:
            votes.append(("MACD", "bullish"))
        elif hist < 0:
            votes.append(("MACD", "bearish"))
        else:
            votes.append(("MACD", "neutral"))

    sma = chart_payload.get("sma_crossover")
    if sma:
        pairs = [(f, s) for f, s in zip(sma.get("fast") or [], sma.get("slow") or []) if f is not None and s is not None]
        if pairs:
            cur_fast, cur_slow = pairs[-1]
            if cur_fast > cur_slow:
                votes.append(("SMA 50/200", "bullish"))
            elif cur_fast < cur_slow:
                votes.append(("SMA 50/200", "bearish"))
            else:
                votes.append(("SMA 50/200", "neutral"))

    return votes


def _bottom_line_text(chart_payload):
    close_price = chart_payload["close"][-1] if chart_payload.get("close") else None
    votes = _tally_lean(chart_payload, close_price)

    bullish = [name for name, lean in votes if lean == "bullish"]
    bearish = [name for name, lean in votes if lean == "bearish"]
    neutral_count = len(votes) - len(bullish) - len(bearish)

    vol = chart_payload.get("volume") or []
    vol_avg = (chart_payload.get("volume_avg") or {}).get("values") or []
    vol_note = ""
    if vol and vol_avg and vol[-1] is not None and vol_avg[-1]:
        ratio = vol[-1] / vol_avg[-1]
        if ratio >= 1.5:
            vol_note = " Volume is running unusually high, which adds some weight to this reading."
        elif ratio <= 0.5:
            vol_note = " Volume is unusually light, though, which is a reason for some caution here."

    threshold_note = ""
    bb = chart_payload["bollinger"]
    if close_price and bb["upper"] and bb["upper"][-1] and bb["lower"][-1]:
        upper, lower = bb["upper"][-1], bb["lower"][-1]
        if close_price < lower:
            pct = (lower - close_price) / close_price * 100
            threshold_note = (f" Price is already about {pct:.1f}% below the lower band (${lower:.2f}) -- "
                               f"it would need to rise back above that level for the Bollinger reading to "
                               f"stop registering as oversold.")
        elif close_price > upper:
            pct = (close_price - upper) / close_price * 100
            threshold_note = (f" Price is already about {pct:.1f}% above the upper band (${upper:.2f}) -- "
                               f"it would need to fall back below that level for the Bollinger reading to "
                               f"stop registering as overbought.")
        else:
            up_pct = (upper - close_price) / close_price * 100
            down_pct = (close_price - lower) / close_price * 100
            threshold_note = (f" For reference: price would need to rise about {up_pct:.1f}% to "
                               f"${upper:.2f} to flip the Bollinger reading to overbought, or fall about "
                               f"{down_pct:.1f}% to ${lower:.2f} to flip it to oversold.")

    if not votes or len(bullish) == len(bearish):
        return (f"Mechanical bottom line: tallying just the directional indicators above, "
                f"{len(bullish)} lean bullish, {len(bearish)} lean bearish, {neutral_count} neutral -- "
                f"no majority either way, so this simple rule would currently sit at HOLD, not BUY or SELL."
                f"{vol_note}{threshold_note} This is a tally of the numbers already shown, not independent "
                f"judgment -- these indicators frequently disagree with each other and with what actually "
                f"happens next, and this isn't financial advice.")

    lean = "BUY" if len(bullish) > len(bearish) else "SELL"
    reasons = bullish if lean == "BUY" else bearish

    return (f"Mechanical bottom line: if this were reduced to one simple rule -- majority vote across "
            f"the indicators above -- {len(reasons)} of {len(votes)} currently lean "
            f"{'bullish' if lean == 'BUY' else 'bearish'} ({', '.join(reasons)}), so the rule would "
            f"currently point to {lean}.{vol_note}{threshold_note} This is a tally of the numbers already "
            f"shown, not independent judgment or a forecast -- these indicators frequently disagree with "
            f"each other and with what actually happens next, and this isn't financial advice.")


def build_interpretation(chart_payload, news_items=None):
    period_label = chart_payload.get("period", "selected")
    close_price = chart_payload["close"][-1] if chart_payload.get("close") else None

    lines = [
        _bollinger_text(chart_payload["bollinger"], close_price, period_label),
        _rsi_text(chart_payload["rsi"]),
        _macd_text(chart_payload["macd"]),
        _volume_text(chart_payload["volume"], chart_payload["volume_avg"]),
    ]

    if chart_payload.get("trendline"):
        lines.append(_trendline_text(chart_payload["trendline"], period_label))
    if chart_payload.get("sma_crossover"):
        lines.append(_sma_crossover_text(chart_payload["sma_crossover"]))
    if chart_payload.get("atr"):
        lines.append(_atr_text(chart_payload["atr"], close_price))

    if news_items:
        top = news_items[0]
        lines.append(f'Recent news: "{top["headline"]}" ({top["source"]}) -- worth reading before acting on the above.')

    lines.append(_bottom_line_text(chart_payload))

    lines.append("This is a mechanical summary of the indicators above, not financial advice -- "
                 "treat it as a starting point for your own research.")

    return lines


def build_outlook(chart_payload, news_items=None, upcoming_earnings_date=None):
    """
    Rule-based BUY/HOLD/SELL lean for the detail page's "Outlook" section --
    the same directional tally used in _bottom_line_text, plus context
    (upcoming earnings, recent news) that doesn't change the lean itself
    but flags reasons the mechanical reading might not tell the whole
    story. Deliberately NOT a price or percent prediction -- no rule-based
    system can honestly compute "you'll see +X%" from news and indicators,
    so this stays qualitative, same as every other interpretation in this
    module.
    """
    close_price = chart_payload["close"][-1] if chart_payload.get("close") else None
    votes = _tally_lean(chart_payload, close_price)

    bullish = [name for name, lean in votes if lean == "bullish"]
    bearish = [name for name, lean in votes if lean == "bearish"]

    if not votes or len(bullish) == len(bearish):
        lean = "HOLD"
        detail = f"{len(bullish)} of {len(votes)} signals lean bullish, {len(bearish)} lean bearish -- no majority"
    elif len(bullish) > len(bearish):
        lean = "BUY"
        detail = f"{len(bullish)} of {len(votes)} signals lean bullish ({', '.join(bullish)})"
    else:
        lean = "SELL"
        detail = f"{len(bearish)} of {len(votes)} signals lean bearish ({', '.join(bearish)})"

    parts = [f"Mechanical outlook: leans {lean} -- {detail}."]

    if upcoming_earnings_date:
        parts.append(f"Earnings are due around {upcoming_earnings_date}, which can add volatility beyond "
                      f"what these indicators capture.")

    if news_items:
        parts.append("There's recent news on this company -- worth reading before acting on this.")

    parts.append("This is a rule-based tally of the indicators above, not a forecast, price target, or "
                  "financial advice.")

    return {"lean": lean, "text": " ".join(parts)}
