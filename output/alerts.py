"""
output/alerts.py - Send trade signal alerts via Telegram and console.
Telegram is optional — the system works without it.
"""

import requests
from datetime import datetime
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, logger


def _is_placeholder(value: str) -> bool:
    if not value:
        return True
    normalized = value.strip().lower()
    return normalized.startswith("your_") or "here" in normalized


def _telegram_send(message: str):
    """Send a message to Telegram if credentials are configured."""
    if _is_placeholder(TELEGRAM_BOT_TOKEN) or _is_placeholder(TELEGRAM_CHAT_ID):
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        resp = requests.post(url, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "HTML",
        }, timeout=10)
        resp.raise_for_status()
    except Exception as e:
        logger.warning("Telegram send failed: %s", e)


def _signal_emoji(signal: str) -> str:
    return {"BUY": "🟢", "SELL": "🔴", "AVOID": "⚪"}.get(signal, "⚪")


def _confidence_bar(score: int) -> str:
    filled = "█" * score
    empty = "░" * (10 - score)
    return f"{filled}{empty} {score}/10"


def format_signal_message(signal: dict) -> str:
    """Format a trade signal into a readable message string."""
    sym = signal.get("symbol", "?")
    sig = signal.get("signal", "AVOID")
    trade_type = signal.get("trade_type", "")
    conf = signal.get("confidence", 0)
    entry = signal.get("entry_price")
    target = signal.get("target_price")
    target2 = signal.get("target_2_price")
    sl = signal.get("stop_loss")
    rr = signal.get("risk_reward_ratio")
    qty = signal.get("quantity")
    setup_type = signal.get("setup_type") or signal.get("pattern_detected", "")
    conviction = signal.get("conviction_label", "")
    next_bias = signal.get("next_session_bias")
    next_conf = signal.get("next_session_confidence")
    reason = signal.get("reasoning", "")
    pattern = signal.get("pattern_detected", "")
    risk_factors = signal.get("risk_factors", "")
    entry_time = signal.get("best_entry_time", "")
    key_levels = signal.get("key_levels", {})

    emoji = _signal_emoji(sig)
    time_str = datetime.now().strftime("%d-%b-%Y %H:%M IST")

    msg = f"""
{emoji} <b>{sym}</b> — {sig} [{trade_type}]
━━━━━━━━━━━━━━━━━━━━
Confidence: {_confidence_bar(conf)}
Conviction: {conviction}
Time: {time_str}

<b>Trade Levels:</b>
  Entry:    ₹{entry}
  Target 1: ₹{target}
  Target 2: ₹{target2 or 'N/A'}
  Stop Loss: ₹{sl}
  R:R Ratio: {rr}
  Quantity: {qty or 'N/A'}

<b>Key Levels:</b>
  Support:    ₹{key_levels.get('support', 'N/A')}
  Resistance: ₹{key_levels.get('resistance', 'N/A')}

<b>Setup:</b> {setup_type}
<b>Entry timing:</b> {entry_time}
<b>Next session:</b> {next_bias or 'N/A'} ({next_conf if next_conf is not None else 'N/A'}%)

<b>Reasoning:</b>
{reason}

<b>Risk factors:</b> {risk_factors}
━━━━━━━━━━━━━━━━━━━━
""".strip()
    return msg


def send_signal_alert(signal: dict):
    """Send a formatted alert for a single trade signal."""
    if signal.get("signal") == "AVOID" or signal.get("confidence", 0) < 1:
        return

    message = format_signal_message(signal)
    logger.info("\n%s", message.replace("<b>", "").replace("</b>", ""))
    _telegram_send(message)


def send_market_summary(summary: dict, signal_count: int):
    """Send the overall market summary."""
    bias = summary.get("market_bias", "UNKNOWN")
    top_picks = ", ".join(summary.get("top_picks", [])) or "None"
    sectors = ", ".join(summary.get("sectors_to_watch", [])) or "None"
    overall = summary.get("overall_summary", "")
    caution = summary.get("caution_notes", "")

    bias_emoji = {"BULLISH": "📈", "BEARISH": "📉", "MIXED": "↔️", "SIDEWAYS": "➡️"}.get(bias, "📊")

    message = f"""
{bias_emoji} <b>Market Summary — {datetime.now().strftime("%d-%b-%Y")}</b>
━━━━━━━━━━━━━━━━━━━━
Stocks scanned: {signal_count}
Market bias: <b>{bias}</b>

<b>Top picks today:</b> {top_picks}
<b>Sectors to watch:</b> {sectors}

<b>Outlook:</b>
{overall}

<b>Watch out for:</b> {caution}
━━━━━━━━━━━━━━━━━━━━
""".strip()

    logger.info("\n%s", message.replace("<b>", "").replace("</b>", ""))
    _telegram_send(message)


def send_intelligence_report(markdown: str):
    """Send the final Top 5 intelligence report to console and Telegram."""
    if not markdown:
        return
    logger.info("\n%s", markdown)
    _telegram_send(markdown[:3900])


def send_scan_start_notification(symbol_count: int):
    _telegram_send(
        f"🔍 <b>Stock Analyzer starting scan</b>\n"
        f"Scanning {symbol_count} stocks at {datetime.now().strftime('%H:%M IST')}"
    )


def send_error_notification(error: str):
    logger.error("SCAN ERROR: %s", error)
    _telegram_send(f"⚠️ <b>Scan Error</b>\n{error}")
