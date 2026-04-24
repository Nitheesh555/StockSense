"""
ai/prompt_builder.py - Build structured prompts for GPT analysis.
Combines OHLCV summary, indicators, patterns, and fundamentals.
"""

from data.fundamentals import format_fundamentals_for_prompt


SYSTEM_PROMPT = """You are an expert Indian stock market analyst specializing in NSE-listed stocks.
You analyze charts and fundamentals to generate precise intraday and swing trade signals.
You always respond with valid JSON only — no preamble, no markdown, no explanation outside the JSON.
Your signals are actionable with specific entry, target, and stop-loss levels.
You are conservative and only give high-confidence signals. When in doubt, signal AVOID."""

def _format_timeframes(timeframes: dict = None) -> str:
    if not timeframes:
        return "Multi-timeframe data unavailable."
    lines = []
    for tf, data in timeframes.items():
        ind = data.get("indicators", {})
        lines.append(
            f"{tf}: close={ind.get('close')}, trend={ind.get('trend')}, "
            f"EMA9/21/50/200={ind.get('ema_fast')}/{ind.get('ema_slow')}/{ind.get('ema_trend')}/{ind.get('ema_200')}, "
            f"RSI={ind.get('rsi')}, MACD hist={ind.get('macd_histogram')}, "
            f"ADX={ind.get('adx')} {ind.get('adx_direction')}, ATR%={ind.get('atr_pct')}, "
            f"VWAP={ind.get('vwap')}, volume ratio={ind.get('volume_ratio')}"
        )
    return "\n".join(lines)


def _format_market_context(market_context: dict = None) -> str:
    if not market_context:
        return "Market context unavailable."
    indexes = market_context.get("indexes", {})
    lines = [f"Market bias: {market_context.get('market_bias', 'UNKNOWN')}"]
    for name, item in indexes.items():
        lines.append(
            f"{name}: status={item.get('status')}, close={item.get('close')}, "
            f"change={item.get('change_pct')}%, trend={item.get('trend')}, rsi={item.get('rsi')}"
        )
    lines.append(f"Sector strength: {', '.join(market_context.get('sector_strength', []))}")
    lines.append(f"FII/DII: {market_context.get('fii_dii', {}).get('status', 'unavailable')}")
    lines.append(f"Expiry: {market_context.get('expiry_awareness', 'Check manually')}")
    return "\n".join(lines)


def _format_setup_context(setup_context: dict = None) -> str:
    if not setup_context:
        return "Setup context unavailable."
    next_session = setup_context.get("next_session", {})
    return f"""Rule-based setup hint:
  Setup type: {setup_context.get('setup_type')}
  Direction hint: {setup_context.get('direction')}
  Score hint: {setup_context.get('score_hint')}/10 ({setup_context.get('label')})
  Reasons: {', '.join(setup_context.get('reasons', [])) or 'N/A'}
  Next session: {next_session.get('bias')} ({next_session.get('confidence')}%) | Gap probability: {next_session.get('gap_probability')}
  Watch level: {next_session.get('watch_level')} | Checklist: {next_session.get('pre_market_checklist')}"""


def build_analysis_prompt(
    symbol: str,
    ohlcv_summary: str,
    indicators: dict,
    patterns: list,
    fundamentals: dict,
    option_data: dict,
    trade_type: str = "INTRADAY",
    pre_computed_levels: dict = None,
    timeframes: dict = None,
    setup_context: dict = None,
    market_context: dict = None,
) -> str:
    """
    Build the full prompt to send to GPT for a single stock.
    Returns the user message string.
    """

    ind = indicators
    opt = option_data or {}
    levels = pre_computed_levels or {}

    pattern_str = ", ".join(patterns) if patterns else "No clear patterns detected"
    fundam_str = format_fundamentals_for_prompt(fundamentals)

    # Pre-computed levels for AI to validate/refine
    levels_str = ""
    if levels:
        buy = levels.get("buy", {})
        sell = levels.get("sell", {})
        levels_str = f"""
Pre-computed technical levels (for your reference, refine as needed):
  BUY: Entry={buy.get('entry')}, SL={buy.get('stop_loss')}, T1={buy.get('target_1')}, T2={buy.get('target_2')}, R:R={buy.get('risk_reward')}
  SELL: Entry={sell.get('entry')}, SL={sell.get('stop_loss')}, T1={sell.get('target_1')}, T2={sell.get('target_2')}, R:R={sell.get('risk_reward')}
  ATR: {levels.get('atr')}"""

    prompt = f"""Analyze the following NSE stock and generate a trade signal.

═══════════════════════════════════════
STOCK: {symbol} | TRADE TYPE: {trade_type}
═══════════════════════════════════════

{ohlcv_summary}

TECHNICAL INDICATORS (latest candle):
  Close: {ind.get('close')} | Open: {ind.get('open')} | High: {ind.get('high')} | Low: {ind.get('low')}
  Volume: {ind.get('volume')} | Volume Ratio vs 20d avg: {ind.get('volume_ratio')}
  
  Trend: {ind.get('trend')} | VWAP Position: {ind.get('vwap_position')} | VWAP: {ind.get('vwap')}
  EMA 9: {ind.get('ema_fast')} | EMA 21: {ind.get('ema_slow')} | EMA 50: {ind.get('ema_trend')}
  
  RSI({14}): {ind.get('rsi')} → {ind.get('rsi_signal')}
  MACD: {ind.get('macd')} | Signal: {ind.get('macd_signal_line')} | Histogram: {ind.get('macd_histogram')}
  MACD Crossover: {ind.get('macd_crossover') or 'none'}
  Stochastic K: {ind.get('stoch_k')} | D: {ind.get('stoch_d')} → {ind.get('stoch_signal')}
  ATR: {ind.get('atr')}
  BB Upper: {ind.get('bb_upper')} | BB Lower: {ind.get('bb_lower')} → {ind.get('bb_signal')}
  
  Pivot: {ind.get('pivot')} | R1: {ind.get('r1')} | R2: {ind.get('r2')}
  S1: {ind.get('s1')} | S2: {ind.get('s2')}

CHART PATTERNS DETECTED:
  {pattern_str}

MULTI-TIMEFRAME TECHNICAL CONTEXT:
{_format_timeframes(timeframes)}

RULE-BASED SETUP CONTEXT:
{_format_setup_context(setup_context)}

MARKET CONTEXT:
{_format_market_context(market_context)}

OPTION CHAIN DATA:
  PCR: {opt.get('pcr', 'N/A')} | Sentiment: {opt.get('sentiment', 'N/A')}
  Max Pain: {opt.get('max_pain', 'N/A')}
  Key CE (resistance) strikes: {opt.get('top_ce_resistance', [])}
  Key PE (support) strikes: {opt.get('top_pe_support', [])}

COMPANY FUNDAMENTALS:
{fundam_str}
{levels_str}

═══════════════════════════════════════
INSTRUCTIONS:
Analyze all the above data holistically. Consider:
1. Technical confluence (how many indicators agree?)
2. Volume confirmation (is the move backed by volume?)
3. Risk/reward ratio (minimum configured threshold is 1.5:1 unless risk clearly invalidates the setup)
4. Fundamentals (for swing trades, is the company fundamentally sound?)
5. Option chain PCR (confirms institutional sentiment)
6. Market context from Nifty, Bank Nifty, VIX, sector strength, and expiry awareness)
7. Next-session bias using close vs VWAP, RSI, MACD histogram, and price vs EMAs)

Respond ONLY with this exact JSON structure, nothing else:
{{
  "symbol": "{symbol}",
  "signal": "BUY" or "SELL" or "AVOID",
  "trade_type": "{trade_type}" or "NONE",
  "confidence": <integer 1-10>,
  "setup_type": "<VWAP Reclaim, VWAP Rejection, Opening Range Breakout, Pullback to 21 EMA, Breakout with Volume Surge, etc.>",
  "conviction_label": "High Conviction" or "Moderate" or "Low / Skip",
  "entry_zone": "<price range or exact level as text>",
  "entry_price": <float or null>,
  "target_price": <float, primary target or null>,
  "target_2_price": <float, secondary target or null>,
  "stop_loss": <float or null>,
  "risk_reward_ratio": <float or null>,
  "quantity": <integer or null>,
  "volatility_flag": "<Normal Volatility or High Volatility - Reduce Position Size or null>",
  "reasoning": "<2-3 sentence explanation of the signal>",
  "key_levels": {{
    "support": <float>,
    "resistance": <float>
  }},
  "pattern_detected": "<primary pattern driving the signal>",
  "risk_factors": "<what could invalidate this signal>",
  "best_entry_time": "<e.g. 'on pullback to VWAP' or 'after ORB confirmation' or 'wait for breakout confirmation'>",
  "next_session_bias": "Bullish" or "Bearish" or "Neutral",
  "next_session_confidence": <integer 0-100>,
  "gap_probability": "High" or "Moderate" or "Low",
  "market_context_reasoning": "<brief note on how market context affects the setup>"
}}
═══════════════════════════════════════"""

    return prompt


def build_watchlist_summary_prompt(signals: list) -> str:
    """Build a prompt to get an overall market summary from today's signals."""
    signal_lines = []
    for s in signals:
        signal_lines.append(
            f"  {s['symbol']}: {s['signal']} | Confidence: {s['confidence']}/10 | "
            f"Entry: {s.get('entry_price')} | Target: {s.get('target_price')} | "
            f"SL: {s.get('stop_loss')} | R:R: {s.get('risk_reward_ratio')}"
        )

    prompt = f"""Based on today's scan of {len(signals)} stocks, here are the signals generated:

{chr(10).join(signal_lines)}

Provide a brief market overview in this JSON format:
{{
  "market_bias": "BULLISH" or "BEARISH" or "MIXED" or "SIDEWAYS",
  "top_picks": ["<symbol1>", "<symbol2>", "<symbol3>"],
  "sectors_to_watch": ["<sector1>", "<sector2>"],
  "overall_summary": "<3-4 sentence market outlook>",
  "caution_notes": "<any risks or things to watch>"
}}"""
    return prompt
