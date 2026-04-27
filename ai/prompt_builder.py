"""
ai/prompt_builder.py - Build structured prompts for Gemini analysis.
Combines OHLCV summary, indicators, patterns, and fundamentals.
"""

from data.fundamentals import format_fundamentals_for_prompt


SYSTEM_PROMPT = """You are an expert Indian stock market analyst specializing in NSE-listed stocks.
You analyze charts and fundamentals to generate precise intraday and swing trade signals.
You always respond with valid JSON only: no preamble, no markdown, no code fences, and no explanation outside the JSON.
You must strictly follow the response schema supplied by the API.
Do not include placeholders, comments, or pseudo-JSON such as "or", "<float>", or "<integer>".
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
    Build the full prompt to send to Gemini for a single stock.
    Returns the user message string.
    """

    ind = indicators
    opt = option_data or {}
    levels = pre_computed_levels or {}

    pattern_str = ", ".join(patterns) if patterns else "No clear patterns detected"
    fundam_str = format_fundamentals_for_prompt(fundamentals)

    levels_str = ""
    if levels:
        buy = levels.get("buy", {})
        sell = levels.get("sell", {})
        levels_str = f"""
Pre-computed technical levels:
  BUY: Entry={buy.get('entry')}, SL={buy.get('stop_loss')}, T1={buy.get('target_1')}, T2={buy.get('target_2')}, R:R={buy.get('risk_reward')}
  SELL: Entry={sell.get('entry')}, SL={sell.get('stop_loss')}, T1={sell.get('target_1')}, T2={sell.get('target_2')}, R:R={sell.get('risk_reward')}
  ATR: {levels.get('atr')}"""

    prompt = f"""Analyze this NSE stock and return a structured trade signal.

STOCK: {symbol}
TRADE TYPE: {trade_type}

PRICE SUMMARY:
{ohlcv_summary}

LATEST TECHNICALS:
  Close={ind.get('close')} Open={ind.get('open')} High={ind.get('high')} Low={ind.get('low')}
  Volume={ind.get('volume')} VolumeRatio={ind.get('volume_ratio')}
  Trend={ind.get('trend')} VWAPPosition={ind.get('vwap_position')} VWAP={ind.get('vwap')}
  EMA9={ind.get('ema_fast')} EMA21={ind.get('ema_slow')} EMA50={ind.get('ema_trend')}
  RSI={ind.get('rsi')} RSISignal={ind.get('rsi_signal')}
  MACD={ind.get('macd')} MACDSignal={ind.get('macd_signal_line')} Histogram={ind.get('macd_histogram')}
  MACDCrossover={ind.get('macd_crossover') or 'none'}
  StochK={ind.get('stoch_k')} StochD={ind.get('stoch_d')} StochSignal={ind.get('stoch_signal')}
  ATR={ind.get('atr')}
  BBUpper={ind.get('bb_upper')} BBLower={ind.get('bb_lower')} BBSignal={ind.get('bb_signal')}
  Pivot={ind.get('pivot')} R1={ind.get('r1')} R2={ind.get('r2')} S1={ind.get('s1')} S2={ind.get('s2')}

PATTERNS:
  {pattern_str}

MULTI-TIMEFRAME CONTEXT:
{_format_timeframes(timeframes)}

RULE-BASED SETUP CONTEXT:
{_format_setup_context(setup_context)}

MARKET CONTEXT:
{_format_market_context(market_context)}

OPTION CHAIN:
  PCR={opt.get('pcr', 'N/A')} Sentiment={opt.get('sentiment', 'N/A')} MaxPain={opt.get('max_pain', 'N/A')}
  CEResistance={opt.get('top_ce_resistance', [])}
  PESupport={opt.get('top_pe_support', [])}

FUNDAMENTALS:
{fundam_str}
{levels_str}

RESPONSE RULES:
- Analyze the data holistically across indicators, patterns, timeframes, options, fundamentals, and market context.
- Use conservative trading judgment. If setup quality is weak, mixed, or unclear, return AVOID.
- Keep reasoning concise.
- Confidence must be an integer from 0 to 10.
- If provided, trade_type must be INTRADAY, SWING, or NONE.
- Return only valid JSON matching the supplied response schema."""

    return prompt


def build_watchlist_summary_prompt(signals: list) -> str:
    """Build a prompt to get an overall market summary from today's signals."""
    signal_lines = []
    for signal in signals:
        signal_lines.append(
            f"{signal['symbol']}: {signal['signal']} | Confidence={signal['confidence']}/10 | "
            f"Entry={signal.get('entry_price')} | Target={signal.get('target_price')} | "
            f"SL={signal.get('stop_loss')} | RR={signal.get('risk_reward_ratio')}"
        )

    prompt = f"""Based on today's scan of {len(signals)} stocks, summarize the market.

SIGNALS:
{chr(10).join(signal_lines)}

RESPONSE RULES:
- Return only valid JSON matching the supplied response schema.
- Keep the market summary concise."""

    return prompt
