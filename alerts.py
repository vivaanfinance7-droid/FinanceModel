"""
Sends alerts through one or more channels (config.ALERT_METHODS). Now that
the dashboard holds the full detail (charts, per-indicator breakdowns, news),
alerts are short teasers pointing you there -- not the full analysis.
"""

import logging

import requests

import config

log = logging.getLogger("sp500_scanner")


# ---------------------------------------------------------------------------
# MESSAGE BUILDERS
# ---------------------------------------------------------------------------

def _format_buy_line(r, seen_today):
    tp = r["trade_plan"]
    line = (f"{r['ticker']}: qty {tp['qty']} @ entry {tp['entry']:.2f} "
            f"/ stop {tp['stop']:.2f} / target {tp['target']:.2f}")

    # Prefer the real intraday crossing time+price (precise, e.g.
    # "10:30 AM @ 103.20, +1.8% since") over the coarser "which check first
    # saw it" flag -- only fall back to the latter when the crossing time
    # couldn't be determined (e.g. intraday data fetch failed). This is
    # also correct for an OLD (already-seen) ticker: crossed_at/crossed_price
    # are recomputed fresh from today's full intraday history every scan,
    # so they still point at the true original cross, not just "since your
    # last check."
    crossed_at = r["trend_line_check"].get("crossed_at")
    crossed_price = r["trend_line_check"].get("crossed_price")
    if crossed_at and crossed_price:
        pct_moved = (tp["entry"] - crossed_price) / crossed_price * 100
        line += f" (crossed {crossed_at} @ {crossed_price:.2f}, {pct_moved:+.1f}% since)"
    else:
        prior = seen_today.get(r["ticker"])
        if prior:
            pct_moved = (tp["entry"] - prior["first_price"]) / prior["first_price"] * 100
            line += f" [seen {prior['first_slot']} @ {prior['first_price']:.2f}, {pct_moved:+.1f}% since]"
    return line


def build_market_check_message(results, slot_label=None, seen_today=None):
    """
    Sent unconditionally on each of the day's scheduled "market analysis"
    scans (see scanner.py / config.STRATEGY_SCAN_TIMES_ET) -- does NOT
    dedupe against previously alerted tickers, since the point is a fresh
    read at every checkpoint, not a one-time ping the first time a setup
    appears.

    results: list of strategy_engine.analyze_ticker()-shaped dicts (the
    full scan's results, not pre-filtered).

    seen_today: {ticker: {"first_price":..., "first_slot":...}} from
    state_manager.get_seen_today(), captured BEFORE this scan's results were
    recorded. Splits BUY signals into a NEW section (not in seen_today --
    up to 5, alphabetical) and, below a separator, an OLD section (already
    flagged at an earlier check today -- also up to 5). At the very first
    check of the day seen_today is always empty, so this naturally
    collapses to just the NEW section with no separator -- no need to
    special-case the 09:35 slot. "No validated ranking, so alphabetical"
    is still the rule within each section.
    """
    seen_today = seen_today or {}
    buys = [r for r in results if r.get("recommendation") == "BUY" and r.get("trade_plan")]
    buys.sort(key=lambda r: r["ticker"])

    new_buys = [r for r in buys if r["ticker"] not in seen_today][:5]
    old_buys = [r for r in buys if r["ticker"] in seen_today][:5]

    header = f"{slot_label} scan" if slot_label else "Scan"
    regime = results[0]["trend_line_check"].get("market_bias", "unknown") if results else "unknown"

    if not new_buys and not old_buys:
        return f"{header} (regime: {regime}): 0 BUY signals right now.\n{config.DASHBOARD_URL}"

    lines = [f"{header} (regime: {regime}): {len(new_buys) + len(old_buys)} BUY signal(s):"]
    if new_buys:
        lines.extend(_format_buy_line(r, seen_today) for r in new_buys)
    else:
        lines.append("(no new signals since your last check)")

    if old_buys:
        lines.append("______________")
        lines.append("OLD companies:")
        lines.extend(_format_buy_line(r, seen_today) for r in old_buys)

    lines.append(config.DASHBOARD_URL)
    return "\n".join(lines)


def build_digest_message(earnings_map, macro_news):
    """
    earnings_map: {ticker: "YYYY-MM-DD"} for tickers reporting soon
    macro_news: list of {"headline":..., "source":...} keyword-matched macro items
    """
    if not earnings_map and not macro_news:
        return None

    parts = []
    if earnings_map:
        tickers = ", ".join(sorted(earnings_map.keys()))
        parts.append(f"earnings soon: {tickers}")
    if macro_news:
        parts.append(f"{len(macro_news)} macro headline(s) worth a look")

    return f"Check the site -- {'; '.join(parts)}\n{config.DASHBOARD_URL}"


# ---------------------------------------------------------------------------
# CHANNELS
# ---------------------------------------------------------------------------

def _send_ntfy(message):
    if not config.NTFY_TOPIC:
        raise RuntimeError("NTFY_TOPIC not configured")

    url = f"{config.NTFY_SERVER.rstrip('/')}/{config.NTFY_TOPIC}"
    resp = requests.post(url, data=message.encode("utf-8"), timeout=10)
    resp.raise_for_status()


def _send_twilio(message):
    from twilio.rest import Client

    missing = [
        name for name, val in [
            ("TWILIO_ACCOUNT_SID", config.TWILIO_ACCOUNT_SID),
            ("TWILIO_AUTH_TOKEN", config.TWILIO_AUTH_TOKEN),
            ("TWILIO_FROM_NUMBER", config.TWILIO_FROM_NUMBER),
            ("ALERT_TO_NUMBER", config.ALERT_TO_NUMBER),
        ] if not val
    ]
    if missing:
        raise RuntimeError(f"Missing Twilio config/env vars: {', '.join(missing)}")

    client = Client(config.TWILIO_ACCOUNT_SID, config.TWILIO_AUTH_TOKEN)
    client.messages.create(body=message, from_=config.TWILIO_FROM_NUMBER, to=config.ALERT_TO_NUMBER)


def _send_email(message):
    import smtplib
    from email.mime.text import MIMEText

    missing = [
        name for name, val in [
            ("SMTP_USERNAME", config.SMTP_USERNAME),
            ("SMTP_PASSWORD", config.SMTP_PASSWORD),
            ("EMAIL_TO", config.EMAIL_TO),
        ] if not val
    ]
    if missing:
        raise RuntimeError(f"Missing email config/env vars: {', '.join(missing)}")

    msg = MIMEText(message)
    msg["From"] = config.SMTP_USERNAME
    msg["To"] = config.EMAIL_TO
    msg["Subject"] = "Check the site -- these might be hot"

    with smtplib.SMTP(config.SMTP_SERVER, config.SMTP_PORT) as server:
        server.starttls()
        server.login(config.SMTP_USERNAME, config.SMTP_PASSWORD)
        server.sendmail(config.SMTP_USERNAME, [config.EMAIL_TO], msg.as_string())


def _send_email_sms(message):
    """Legacy carrier email-to-SMS gateway. Most carriers discontinued this -- see README."""
    import smtplib
    from email.mime.text import MIMEText

    missing = [
        name for name, val in [
            ("SMTP_USERNAME", config.SMTP_USERNAME),
            ("SMTP_PASSWORD", config.SMTP_PASSWORD),
            ("SMS_GATEWAY_ADDRESS", config.SMS_GATEWAY_ADDRESS),
        ] if not val
    ]
    if missing:
        raise RuntimeError(f"Missing email-to-SMS config/env vars: {', '.join(missing)}")

    msg = MIMEText(message)
    msg["From"] = config.SMTP_USERNAME
    msg["To"] = config.SMS_GATEWAY_ADDRESS
    msg["Subject"] = ""

    with smtplib.SMTP(config.SMTP_SERVER, config.SMTP_PORT) as server:
        server.starttls()
        server.login(config.SMTP_USERNAME, config.SMTP_PASSWORD)
        server.sendmail(config.SMTP_USERNAME, [config.SMS_GATEWAY_ADDRESS], msg.as_string())


_SENDERS = {
    "ntfy": _send_ntfy,
    "twilio": _send_twilio,
    "email": _send_email,
    "email_sms": _send_email_sms,
}


def send(message):
    if not message:
        return

    if not config.ALERT_METHODS:
        log.warning("No ALERT_METHODS configured -- message not sent")
        return

    for method in config.ALERT_METHODS:
        sender = _SENDERS.get(method)
        if not sender:
            log.error(f"Unknown alert method: {method}")
            continue
        try:
            sender(message)
            log.info(f"Alert sent via {method}")
        except Exception as e:
            log.error(f"Failed to send alert via {method}: {e}")
