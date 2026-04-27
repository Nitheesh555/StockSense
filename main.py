"""
main.py - Main orchestrator for the Stock Signal Analyzer.

Usage:
    python main.py                  # Run scheduled scans (9:20 AM + 11:30 AM IST)
    python main.py --scan-now       # Run a single scan immediately and exit
    python main.py --symbol RELIANCE --type INTRADAY   # Analyze one stock

Architecture:
    1. Load watchlist
    2. For each stock: fetch OHLCV + fundamentals + option chain
    3. Compute technical indicators and detect patterns
    4. Send to Gemini for synthesis
    5. Save signals to SQLite and send Telegram alerts
    6. View results in Streamlit dashboard
"""

import sys
import time
import argparse
from datetime import datetime

from config import (
    PREMARKET_SCAN_HOUR, PREMARKET_SCAN_MINUTE,
    SCAN_HOUR, SCAN_MINUTE, MIDDAY_SCAN_HOUR, MIDDAY_SCAN_MINUTE,
    EOD_SCAN_HOUR, EOD_SCAN_MINUTE, NEXT_SESSION_SCAN_HOUR, NEXT_SESSION_SCAN_MINUTE,
    load_watchlist, get_settings, logger, GEMINI_API_KEY
)
from data.cache import init_db, save_signal
from data.fetcher import fetch_multi_timeframe, fetch_option_chain
from data.fundamentals import fetch_fundamentals
from analysis.analyzer import compute_indicators, get_ohlcv_summary, analyze_timeframes, summarize_timeframe_alignment
from analysis.signals import calculate_trade_levels, enrich_signal_with_risk
from analysis.patterns import detect_patterns
from analysis.setup_engine import build_setup_context
from ai.ai_engine import analyze_stock, generate_market_summary
from context.market_context import build_market_context
from output.alerts import (
    send_signal_alert, send_market_summary, send_intelligence_report,
    send_scan_start_notification, send_error_notification
)
from output.report_generator import build_intelligence_report, persist_intelligence_report, select_top_setups


def check_api_key():
    if not GEMINI_API_KEY:
        logger.error(
            "\n" + "="*60 +
            "\nGEMINI_API_KEY is not set!" +
            "\nSteps to fix:" +
            "\n  1. Copy .env.example to .env" +
            "\n  2. Add your API key from https://ai.google.dev/" +
            "\n  3. Run again" +
            "\n" + "="*60
        )
        sys.exit(1)


def _normalize_signal_fields(signal: dict, indicators: dict, trade_type: str,
                             setup_context: dict, pre_levels: dict) -> dict:
    """Fill new intelligence fields from local rules when Gemini omits or nulls them."""
    if not signal:
        return signal

    direction = signal.get("signal")
    level_key = "buy" if direction == "BUY" else "sell" if direction == "SELL" else None
    levels = pre_levels.get(level_key, {}) if level_key else {}
    next_session = setup_context.get("next_session", {})

    def fill(key, value):
        if signal.get(key) in (None, "", "N/A"):
            signal[key] = value

    fill("setup_type", setup_context.get("setup_type"))
    fill("conviction_label", setup_context.get("label"))
    fill("entry_zone", str(levels.get("entry") or signal.get("entry_price") or "N/A"))
    fill("entry_price", levels.get("entry"))
    fill("target_price", levels.get("target_1"))
    fill("target_2_price", levels.get("target_2"))
    fill("stop_loss", levels.get("stop_loss"))
    fill("risk_reward_ratio", levels.get("risk_reward"))
    fill("pattern_detected", setup_context.get("setup_type") or "N/A")
    fill("best_entry_time", "Wait for setup confirmation")
    fill("risk_factors", "Invalid if price fails setup level or broader market reverses.")
    fill("next_session_bias", next_session.get("bias"))
    fill("next_session_confidence", next_session.get("confidence"))
    fill("gap_probability", next_session.get("gap_probability"))
    fill("market_context_reasoning", "Best-effort market context included where available.")

    key_levels = signal.setdefault("key_levels", {})
    if key_levels.get("support") in (None, "", "N/A"):
        key_levels["support"] = next_session.get("support") or indicators.get("s1")
    if key_levels.get("resistance") in (None, "", "N/A"):
        key_levels["resistance"] = next_session.get("resistance") or indicators.get("r1")

    return enrich_signal_with_risk(signal, indicators, trade_type, get_settings())


def analyze_single_stock(symbol: str, trade_type: str = "INTRADAY", market_context: dict = None) -> dict:
    """
    Full pipeline for a single stock.
    Returns the signal dict.
    """
    logger.info("--- Analyzing %s [%s] ---", symbol, trade_type)

    # 1. Fetch multi-timeframe price data
    frames = fetch_multi_timeframe(symbol)
    df = frames.get("1d") if trade_type == "SWING" else frames.get("5m")

    if df is None or df.empty:
        logger.warning("No price data for %s, skipping", symbol)
        return {}

    # 2. Fetch supporting data (non-blocking)
    try:
        fundamentals = fetch_fundamentals(symbol)
    except Exception as e:
        logger.warning("Fundamentals failed for %s: %s", symbol, e)
        fundamentals = {}

    try:
        option_data = fetch_option_chain(symbol)
    except Exception as e:
        logger.warning("Option chain failed for %s: %s", symbol, e)
        option_data = {}

    # 3. Technical analysis
    timeframe_analysis = analyze_timeframes(frames)
    alignment = summarize_timeframe_alignment(timeframe_analysis)
    indicators = compute_indicators(df)
    if not indicators:
        logger.warning("No indicators computed for %s", symbol)
        return {}

    patterns = detect_patterns(df, indicators)
    ohlcv_summary = get_ohlcv_summary(df, n_candles=8)
    setup_context = build_setup_context(
        trade_type=trade_type,
        frames=frames,
        indicators=indicators,
        alignment=alignment,
        patterns=patterns,
    )

    # 4. Pre-compute levels (AI will refine these)
    pre_levels = calculate_trade_levels(indicators, trade_type)

    # 5. AI analysis
    signal = analyze_stock(
        symbol=symbol,
        ohlcv_summary=ohlcv_summary,
        indicators=indicators,
        patterns=patterns,
        fundamentals=fundamentals,
        option_data=option_data,
        trade_type=trade_type,
        pre_computed_levels=pre_levels,
        timeframes=timeframe_analysis,
        setup_context=setup_context,
        market_context=market_context,
    )

    signal = _normalize_signal_fields(
        signal=signal,
        indicators=indicators,
        trade_type=trade_type,
        setup_context=setup_context,
        pre_levels=pre_levels,
    )

    return signal


def run_full_scan(trade_type: str = "INTRADAY", market_context: dict = None,
                  send_individual_alerts: bool = False, generate_report: bool = True):
    """
    Run a full scan of the watchlist.
    """
    wl = load_watchlist()
    settings = get_settings()
    min_confidence = settings.get("min_confidence", 7)
    market_context = market_context or build_market_context()

    symbols = wl.get(trade_type.lower(), wl.get("intraday", []))
    if not symbols:
        logger.warning("No symbols found for trade_type=%s", trade_type)
        return []

    logger.info("="*60)
    logger.info("Starting %s scan: %d stocks | Min confidence: %d",
                trade_type, len(symbols), min_confidence)
    logger.info("="*60)

    send_scan_start_notification(len(symbols))

    all_signals = []
    for i, symbol in enumerate(symbols, 1):
        try:
            logger.info("[%d/%d] Processing %s", i, len(symbols), symbol)
            signal = analyze_single_stock(symbol, trade_type, market_context=market_context)

            if signal:
                save_signal(signal)
                all_signals.append(signal)

                # Individual alerts are optional; combined Top 5 reports are the default surface.
                if (send_individual_alerts
                        and signal.get("confidence", 0) >= min_confidence
                        and signal.get("signal") in ("BUY", "SELL")):
                    send_signal_alert(signal)

        except Exception as e:
            logger.error("Error analyzing %s: %s", symbol, e)
            continue

        # Polite delay between stocks
        time.sleep(1)

    # Generate and send market summary
    actionable = [s for s in all_signals if s.get("signal") in ("BUY", "SELL")]
    if actionable:
        try:
            summary = generate_market_summary(select_top_setups(actionable))
            send_market_summary(summary, len(all_signals))
        except Exception as e:
            logger.error("Market summary failed: %s", e)

    logger.info("Scan complete. %d/%d stocks generated actionable signals.",
                len(actionable), len(all_signals))
    if generate_report:
        intraday = all_signals if trade_type == "INTRADAY" else []
        swing = all_signals if trade_type == "SWING" else []
        report = build_intelligence_report(intraday, swing, market_context)
        report_path = persist_intelligence_report(report, report_type=trade_type.lower())
        send_intelligence_report(report["markdown"])
        logger.info("%s intelligence report saved: %s", trade_type, report_path)
    return all_signals


def run_combined_scan():
    """Run both intraday and swing scans sequentially."""
    logger.info("Running combined intraday + swing scan")
    market_context = build_market_context()
    intraday_signals = run_full_scan("INTRADAY", market_context=market_context, generate_report=False)
    time.sleep(5)
    swing_signals = run_full_scan("SWING", market_context=market_context, generate_report=False)
    report = build_intelligence_report(intraday_signals, swing_signals, market_context)
    report_path = persist_intelligence_report(report)
    send_intelligence_report(report["markdown"])
    logger.info("Top intelligence report saved: %s", report_path)
    return intraday_signals + swing_signals


def run_next_session_scan():
    """Generate a best-effort next-session report from both watchlists."""
    logger.info("Running next-session intelligence scan")
    return run_combined_scan()


def run_scheduler():
    """
    Run the scheduler loop.
    Triggers scans at configured market-hour times (IST).
    Uses a simple time-check loop (no external dependencies for scheduling).
    """
    logger.info("Scheduler started. Watching for scan times...")
    logger.info(
        "Pre-market: %02d:%02d | Intraday: %02d:%02d | Midday: %02d:%02d | EOD: %02d:%02d | Next session: %02d:%02d IST",
        PREMARKET_SCAN_HOUR, PREMARKET_SCAN_MINUTE,
        SCAN_HOUR, SCAN_MINUTE,
        MIDDAY_SCAN_HOUR, MIDDAY_SCAN_MINUTE,
        EOD_SCAN_HOUR, EOD_SCAN_MINUTE,
        NEXT_SESSION_SCAN_HOUR, NEXT_SESSION_SCAN_MINUTE,
    )

    jobs = [
        ("pre_market", PREMARKET_SCAN_HOUR, PREMARKET_SCAN_MINUTE, run_next_session_scan),
        ("intraday", SCAN_HOUR, SCAN_MINUTE, lambda: run_full_scan("INTRADAY", market_context=build_market_context())),
        ("midday", MIDDAY_SCAN_HOUR, MIDDAY_SCAN_MINUTE, lambda: run_full_scan("INTRADAY", market_context=build_market_context())),
        ("eod_swing", EOD_SCAN_HOUR, EOD_SCAN_MINUTE, lambda: run_full_scan("SWING", market_context=build_market_context())),
        ("next_session", NEXT_SESSION_SCAN_HOUR, NEXT_SESSION_SCAN_MINUTE, run_next_session_scan),
    ]
    last_run = {}

    while True:
        now = datetime.now()
        today = now.date()

        for job_id, hour, minute, func in jobs:
            if now.hour == hour and now.minute >= minute and last_run.get(job_id) != today:
                logger.info("Triggering %s scan at %s", job_id, now.strftime("%H:%M"))
                try:
                    func()
                    last_run[job_id] = today
                except Exception as e:
                    send_error_notification(str(e))
                    logger.error("%s scan failed: %s", job_id, e)

        time.sleep(30)  # check every 30 seconds


# ── Entry point ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NSE Stock Signal Analyzer")
    parser.add_argument("--scan-now", action="store_true",
                        help="Run a full scan immediately and exit")
    parser.add_argument("--symbol", type=str,
                        help="Analyze a single stock symbol (e.g. RELIANCE)")
    parser.add_argument("--type", type=str, default="INTRADAY",
                        choices=["INTRADAY", "SWING"],
                        help="Trade type for single stock analysis")
    args = parser.parse_args()

    # Always initialize the database first
    init_db()
    check_api_key()

    if args.symbol:
        # Single stock mode
        signal = analyze_single_stock(args.symbol.upper(), args.type)
        if signal:
            from output.alerts import format_signal_message
            print("\n" + format_signal_message(signal).replace("<b>", "").replace("</b>", ""))
        else:
            print(f"No signal generated for {args.symbol}")

    elif args.scan_now:
        # One-shot scan
        run_combined_scan()
        print("\nScan complete. View results:")
        print("  streamlit run output/dashboard.py")

    else:
        # Continuous scheduler mode
        print("""
╔══════════════════════════════════════════╗
║      NSE Stock Signal Analyzer v1.0      ║
║  Run 'python main.py --help' for options ║
╚══════════════════════════════════════════╝

Scheduler running. Scans will trigger at:
  Pre-market:   {:02d}:{:02d} IST
  Intraday:     {:02d}:{:02d} IST
  Midday:       {:02d}:{:02d} IST
  EOD swing:    {:02d}:{:02d} IST
  Next session: {:02d}:{:02d} IST

Press Ctrl+C to stop.
To view signals:  streamlit run output/dashboard.py
""".format(
            PREMARKET_SCAN_HOUR, PREMARKET_SCAN_MINUTE,
            SCAN_HOUR, SCAN_MINUTE,
            MIDDAY_SCAN_HOUR, MIDDAY_SCAN_MINUTE,
            EOD_SCAN_HOUR, EOD_SCAN_MINUTE,
            NEXT_SESSION_SCAN_HOUR, NEXT_SESSION_SCAN_MINUTE,
        ))

        try:
            run_scheduler()
        except KeyboardInterrupt:
            logger.info("Scheduler stopped by user.")
