"""
ai/ai_engine.py - OpenAI GPT integration.
Sends structured prompts and parses JSON trade signals.
"""

import json
import time
from openai import OpenAI, APIError, AuthenticationError, BadRequestError, RateLimitError

from config import OPENAI_API_KEY, OPENAI_MODEL, MAX_TOKENS, logger
from ai.prompt_builder import SYSTEM_PROMPT, build_analysis_prompt, build_watchlist_summary_prompt

_OPENAI_DISABLED_REASON = None
_OPENAI_DISABLED_LOGGED = False

_SIGNAL_SCHEMA = {
    "name": "stock_signal",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "symbol": {"type": "string"},
            "signal": {"type": "string", "enum": ["BUY", "SELL", "AVOID"]},
            "trade_type": {"type": "string", "enum": ["INTRADAY", "SWING", "NONE"]},
            "confidence": {"type": "integer"},
            "setup_type": {"type": "string"},
            "conviction_label": {"type": "string"},
            "entry_zone": {"type": "string"},
            "entry_price": {"type": ["number", "null"]},
            "target_price": {"type": ["number", "null"]},
            "target_2_price": {"type": ["number", "null"]},
            "stop_loss": {"type": ["number", "null"]},
            "risk_reward_ratio": {"type": ["number", "null"]},
            "quantity": {"type": ["integer", "null"]},
            "volatility_flag": {"type": ["string", "null"]},
            "reasoning": {"type": "string"},
            "key_levels": {
                "type": "object",
                "properties": {
                    "support": {"type": ["number", "null"]},
                    "resistance": {"type": ["number", "null"]},
                },
                "required": ["support", "resistance"],
                "additionalProperties": False,
            },
            "pattern_detected": {"type": "string"},
            "risk_factors": {"type": "string"},
            "best_entry_time": {"type": "string"},
            "next_session_bias": {"type": "string"},
            "next_session_confidence": {"type": "integer"},
            "gap_probability": {"type": "string"},
            "market_context_reasoning": {"type": "string"},
        },
        "required": [
            "symbol",
            "signal",
            "trade_type",
            "confidence",
            "setup_type",
            "conviction_label",
            "entry_zone",
            "entry_price",
            "target_price",
            "target_2_price",
            "stop_loss",
            "risk_reward_ratio",
            "quantity",
            "volatility_flag",
            "reasoning",
            "key_levels",
            "pattern_detected",
            "risk_factors",
            "best_entry_time",
            "next_session_bias",
            "next_session_confidence",
            "gap_probability",
            "market_context_reasoning",
        ],
        "additionalProperties": False,
    },
}

_MARKET_SUMMARY_SCHEMA = {
    "name": "market_summary",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "market_bias": {
                "type": "string",
                "enum": ["BULLISH", "BEARISH", "MIXED", "SIDEWAYS", "UNKNOWN"],
            },
            "top_picks": {
                "type": "array",
                "items": {"type": "string"},
            },
            "sectors_to_watch": {
                "type": "array",
                "items": {"type": "string"},
            },
            "overall_summary": {"type": "string"},
            "caution_notes": {"type": "string"},
        },
        "required": [
            "market_bias",
            "top_picks",
            "sectors_to_watch",
            "overall_summary",
            "caution_notes",
        ],
        "additionalProperties": False,
    },
}


def _get_client():
    if not OPENAI_API_KEY:
        raise ValueError(
            "OPENAI_API_KEY not set. Copy .env.example to .env and add your key.\n"
            "Create a key at: https://platform.openai.com/api-keys"
        )
    return OpenAI(api_key=OPENAI_API_KEY, max_retries=0)


def _openai_available() -> bool:
    return _OPENAI_DISABLED_REASON is None


def _log_disabled_once():
    global _OPENAI_DISABLED_LOGGED
    if _OPENAI_DISABLED_REASON and not _OPENAI_DISABLED_LOGGED:
        logger.warning("GPT analysis disabled for this run: %s", _OPENAI_DISABLED_REASON)
        _OPENAI_DISABLED_LOGGED = True


def _call_gpt(
    user_prompt: str,
    response_schema: dict,
    max_tokens: int = MAX_TOKENS,
) -> str:
    """Call OpenAI Responses API with structured JSON output."""
    global _OPENAI_DISABLED_REASON

    if _OPENAI_DISABLED_REASON:
        raise RuntimeError(_OPENAI_DISABLED_REASON)

    client = _get_client()
    try:
        response = client.responses.create(
            model=OPENAI_MODEL,
            instructions=SYSTEM_PROMPT,
            input=[{"role": "user", "content": user_prompt}],
            max_output_tokens=max_tokens,
            text={"format": {"type": "json_schema", **response_schema}},
        )
        return response.output_text
    except RateLimitError as e:
        _OPENAI_DISABLED_REASON = "OpenAI rate limit reached for this run."
        logger.warning("OpenAI rate limit hit: %s", e)
        raise RuntimeError(_OPENAI_DISABLED_REASON) from e
    except AuthenticationError as e:
        _OPENAI_DISABLED_REASON = "OpenAI API authentication failed for this run."
        logger.error("OpenAI authentication error: %s", e)
        raise RuntimeError(_OPENAI_DISABLED_REASON) from e
    except BadRequestError as e:
        logger.error("OpenAI bad request error: %s", e)
        error_text = str(e).lower()
        if "insufficient" in error_text or "quota" in error_text or "billing" in error_text:
            _OPENAI_DISABLED_REASON = "OpenAI API credits or billing are unavailable for this run."
            raise RuntimeError(_OPENAI_DISABLED_REASON) from e
        raise
    except APIError as e:
        logger.error("OpenAI API error: %s", e)
        raise


def _parse_json_response(raw: str, symbol: str) -> dict:
    """Safely parse JSON from GPT's response."""
    if not raw:
        return _fallback_signal(symbol, "Empty API response")
    try:
        return json.loads(raw.strip())
    except json.JSONDecodeError as e:
        logger.error("JSON parse error for %s: %s | Raw: %s", symbol, e, raw[:200])
        return _fallback_signal(symbol, f"JSON parse error: {e}")


def _fallback_signal(symbol: str, reason: str) -> dict:
    return {
        "symbol": symbol,
        "signal": "AVOID",
        "trade_type": "NONE",
        "confidence": 0,
        "setup_type": "N/A",
        "conviction_label": "Low / Skip",
        "entry_zone": "N/A",
        "entry_price": None,
        "target_price": None,
        "target_2_price": None,
        "stop_loss": None,
        "risk_reward_ratio": None,
        "quantity": None,
        "volatility_flag": None,
        "reasoning": f"Analysis failed: {reason}",
        "key_levels": {"support": None, "resistance": None},
        "pattern_detected": "N/A",
        "risk_factors": "Analysis unavailable",
        "best_entry_time": "N/A",
        "next_session_bias": "Neutral",
        "next_session_confidence": 0,
        "gap_probability": "Low",
        "market_context_reasoning": "Analysis unavailable",
        "error": True,
    }


def analyze_stock(
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
) -> dict:
    """
    Full AI analysis for a single stock.
    Returns a structured signal dict.
    """
    if not indicators:
        return _fallback_signal(symbol, "No indicator data available")

    if not _openai_available():
        _log_disabled_once()
        return _fallback_signal(symbol, _OPENAI_DISABLED_REASON)

    prompt = build_analysis_prompt(
        symbol=symbol,
        ohlcv_summary=ohlcv_summary,
        indicators=indicators,
        patterns=patterns,
        fundamentals=fundamentals,
        option_data=option_data,
        trade_type=trade_type,
        pre_computed_levels=pre_computed_levels,
        timeframes=timeframes,
        setup_context=setup_context,
        market_context=market_context,
    )

    logger.info("Sending %s to GPT (%s) for %s analysis...", symbol, OPENAI_MODEL, trade_type)
    try:
        raw = _call_gpt(prompt, _SIGNAL_SCHEMA)
    except Exception as e:
        logger.warning("Using fallback analysis for %s: %s", symbol, e)
        return _fallback_signal(symbol, str(e))

    signal = _parse_json_response(raw, symbol)
    signal["symbol"] = symbol
    signal["trade_type"] = signal.get("trade_type", trade_type)
    if setup_context:
        signal.setdefault("setup_type", setup_context.get("setup_type"))
        signal.setdefault("conviction_label", setup_context.get("label"))
        next_session = setup_context.get("next_session", {})
        signal.setdefault("next_session_bias", next_session.get("bias"))
        signal.setdefault("next_session_confidence", next_session.get("confidence"))
        signal.setdefault("gap_probability", next_session.get("gap_probability"))

    logger.info(
        "%s -> %s | Confidence: %s/10 | Entry: %s | Target: %s | SL: %s",
        symbol,
        signal.get("signal"),
        signal.get("confidence"),
        signal.get("entry_price"),
        signal.get("target_price"),
        signal.get("stop_loss"),
    )

    time.sleep(1.5)
    return signal


def generate_market_summary(signals: list) -> dict:
    """
    Generate an overall market summary from today's signals.
    """
    if not signals:
        return {
            "market_bias": "UNKNOWN",
            "top_picks": [],
            "sectors_to_watch": [],
            "overall_summary": "No signals generated today.",
            "caution_notes": "Ensure market data was fetched correctly.",
        }

    if not _openai_available():
        _log_disabled_once()
        return {
            "market_bias": "UNKNOWN",
            "top_picks": [],
            "sectors_to_watch": [],
            "overall_summary": "AI market summary unavailable for this run.",
            "caution_notes": _OPENAI_DISABLED_REASON,
        }

    prompt = build_watchlist_summary_prompt(signals)
    try:
        raw = _call_gpt(prompt, _MARKET_SUMMARY_SCHEMA, max_tokens=500)
    except Exception as e:
        logger.warning("Using fallback market summary: %s", e)
        return {
            "market_bias": "UNKNOWN",
            "top_picks": [],
            "sectors_to_watch": [],
            "overall_summary": "AI market summary unavailable for this run.",
            "caution_notes": str(e),
        }
    return _parse_json_response(raw, "MARKET_SUMMARY")
