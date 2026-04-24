"""
output/report_generator.py - Build and persist the final trade intelligence report.
"""

from datetime import datetime

from config import REPORTS_DIR, get_settings, logger
from data.cache import save_intelligence_report


def _fmt_price(value):
    return f"Rs {value:.2f}" if isinstance(value, (int, float)) else "N/A"


def _signal_sort_key(signal):
    return (
        int(signal.get("confidence") or 0),
        float(signal.get("risk_reward_ratio") or 0),
    )


def select_top_setups(signals: list, top_n: int = None) -> list:
    settings = get_settings()
    top_n = top_n or int(settings.get("top_n_setups", 5))
    actionable = [
        s for s in signals
        if s.get("signal") in ("BUY", "SELL")
        and int(s.get("confidence") or 0) >= int(settings.get("min_confidence", 7))
        and (s.get("risk_reward_ratio") is None or float(s.get("risk_reward_ratio") or 0) >= float(settings.get("rr_ratio_min", 1.5)))
    ]
    return sorted(actionable, key=_signal_sort_key, reverse=True)[:top_n]


def _market_pulse_line(market_context: dict) -> str:
    indexes = market_context.get("indexes", {})
    nifty = indexes.get("nifty", {})
    vix = indexes.get("india_vix", {})
    fii = market_context.get("fii_dii", {}).get("status", "unavailable")
    nifty_text = f"{nifty.get('trend', 'unknown')} {nifty.get('change_pct', 'N/A')}%"
    vix_text = vix.get("close", "N/A")
    return f"Market Pulse: Nifty {nifty_text} | VIX {vix_text} | FII/DII {fii}"


def _trade_lines(signals: list, title: str) -> list:
    lines = [f"## {title}"]
    if not signals:
        lines.append("No qualifying setups.")
        return lines
    for index, signal in enumerate(signals, 1):
        rr = signal.get("risk_reward_ratio")
        qty = signal.get("quantity") or "N/A"
        label = signal.get("conviction_label") or "N/A"
        lines.extend([
            f"{index}. {signal.get('symbol')} | {signal.get('signal')} | {signal.get('setup_type') or signal.get('pattern_detected')}",
            f"   Entry: {_fmt_price(signal.get('entry_price'))} | SL: {_fmt_price(signal.get('stop_loss'))} | T1: {_fmt_price(signal.get('target_price'))} | T2: {_fmt_price(signal.get('target_2_price'))}",
            f"   R:R = {rr if rr is not None else 'N/A'} | Qty: {qty} | Conviction: {label} {signal.get('confidence', 0)}/10",
            f"   Risk: {signal.get('volatility_flag') or signal.get('risk_factors') or 'Review manually'}",
        ])
    return lines


def _next_session_lines(signals: list) -> list:
    lines = ["## Next Session Outlook"]
    outlooks = [
        s for s in sorted(signals, key=_signal_sort_key, reverse=True)
        if s.get("next_session_bias")
    ][:5]
    if not outlooks:
        lines.append("No next-session outlook available.")
        return lines
    for signal in outlooks:
        lines.append(
            f"{signal.get('symbol')}: {signal.get('next_session_bias')} "
            f"({signal.get('next_session_confidence', 'N/A')}%) - "
            f"Watch support {_fmt_price(signal.get('key_levels', {}).get('support'))}, "
            f"resistance {_fmt_price(signal.get('key_levels', {}).get('resistance'))}"
        )
    return lines


def build_intelligence_report(intraday_signals: list, swing_signals: list, market_context: dict) -> dict:
    now = datetime.now()
    top_intraday = select_top_setups(intraday_signals)
    top_swing = select_top_setups(swing_signals)
    combined = top_intraday + top_swing
    lines = [
        f"# Trade Intelligence Report - {now.strftime('%d-%b-%Y %H:%M IST')}",
        _market_pulse_line(market_context),
        "",
        *_trade_lines(top_intraday, "Intraday Setups (Valid till 3:15 PM IST)"),
        "",
        *_trade_lines(top_swing, "Swing Setups (3-10 Days)"),
        "",
        *_next_session_lines(combined or intraday_signals + swing_signals),
        "",
        "Disclaimer: Educational and research use only. Validate every setup before trading.",
    ]
    markdown = "\n".join(lines)
    return {
        "markdown": markdown,
        "top_intraday": top_intraday,
        "top_swing": top_swing,
        "market_context": market_context,
    }


def persist_intelligence_report(report: dict, report_type: str = "combined") -> str:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = REPORTS_DIR / f"trade_intelligence_{stamp}.md"
    path.write_text(report["markdown"], encoding="utf-8")
    save_intelligence_report(report_type, report["markdown"], report)
    logger.info("Saved intelligence report to %s", path)
    return str(path)
