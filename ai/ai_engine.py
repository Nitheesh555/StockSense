"""
ai/ai_engine.py - Gemini API integration.
Sends structured prompts and parses JSON trade signals.
"""

import json
import time

import requests

from config import GEMINI_API_KEY, GEMINI_MODEL, MAX_TOKENS, logger
from ai.prompt_builder import SYSTEM_PROMPT, build_analysis_prompt, build_watchlist_summary_prompt

_GEMINI_DISABLED_REASON = None
_GEMINI_DISABLED_LOGGED = False
_GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
_REQUEST_TIMEOUT_SECONDS = 90
_TRANSIENT_STATUS_CODES = {500, 502, 503, 504}
_RETRYABLE_FINISH_REASONS = {"MAX_TOKENS"}

_SIGNAL_SCHEMA = {
    "type": "object",
    "properties": {
        "symbol": {"type": "string"},
        "signal": {"type": "string", "enum": ["BUY", "SELL", "AVOID"]},
        "trade_type": {"type": "string", "enum": ["INTRADAY", "SWING", "NONE"]},
        "confidence": {"type": "integer", "minimum": 0, "maximum": 10},
        "setup_type": {"type": "string"},
        "entry_price": {"type": ["number", "null"]},
        "target_price": {"type": ["number", "null"]},
        "stop_loss": {"type": ["number", "null"]},
        "reasoning": {"type": "string"},
    },
    "required": [
        "symbol",
        "signal",
        "confidence",
        "reasoning",
    ],
    "additionalProperties": False,
}

_MARKET_SUMMARY_SCHEMA = {
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
}


def _gemini_available() -> bool:
    return _GEMINI_DISABLED_REASON is None


def _log_disabled_once():
    global _GEMINI_DISABLED_LOGGED
    if _GEMINI_DISABLED_REASON and not _GEMINI_DISABLED_LOGGED:
        logger.warning("Gemini analysis disabled for this run: %s", _GEMINI_DISABLED_REASON)
        _GEMINI_DISABLED_LOGGED = True


def _extract_error_message(response: requests.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.text.strip() or f"HTTP {response.status_code}"
    return payload.get("error", {}).get("message") or response.text.strip() or f"HTTP {response.status_code}"


def _classify_http_failure(response: requests.Response) -> str:
    message = _extract_error_message(response)
    status_code = response.status_code
    lowered = message.lower()

    if status_code in (401, 403):
        return "Gemini API authentication failed for this run."
    if status_code == 429 and ("quota" in lowered or "billing" in lowered or "credit" in lowered):
        return "Gemini API credits or billing are unavailable for this run."
    if status_code == 429:
        return "Gemini API rate limit reached for this run."
    if status_code in (400, 402) and ("quota" in lowered or "billing" in lowered or "credit" in lowered):
        return "Gemini API credits or billing are unavailable for this run."
    if status_code in _TRANSIENT_STATUS_CODES:
        return f"Gemini API temporarily unavailable: {message}"
    return f"Gemini API request failed: {message}"


def _is_permanent_disable_reason(reason: str) -> bool:
    lowered = reason.lower()
    return "authentication failed" in lowered or "credits or billing" in lowered


def _extract_text_and_finish_reason(response_json: dict) -> tuple[str, str | None]:
    for candidate in response_json.get("candidates", []):
        content = candidate.get("content", {})
        collected = []
        for part in content.get("parts", []):
            text = part.get("text")
            if text:
                collected.append(text)
        if collected:
            return "".join(collected), candidate.get("finishReason")

    prompt_feedback = response_json.get("promptFeedback", {})
    if prompt_feedback:
        raise RuntimeError(f"Gemini blocked the prompt: {json.dumps(prompt_feedback)}")
    raise RuntimeError("Gemini returned no candidate text.")


def _call_gemini(
    user_prompt: str,
    response_schema: dict,
    max_tokens: int = MAX_TOKENS,
) -> str:
    """Call Gemini generateContent with JSON schema output."""
    global _GEMINI_DISABLED_REASON

    if _GEMINI_DISABLED_REASON:
        raise RuntimeError(_GEMINI_DISABLED_REASON)

    if not GEMINI_API_KEY:
        raise ValueError(
            "GEMINI_API_KEY not set. Copy .env.example to .env and add your key.\n"
            "Create a key at: https://ai.google.dev/"
        )

    token_attempts = [max_tokens, max(max_tokens * 4, 4096)]
    last_error = None

    for attempt_index, attempt_tokens in enumerate(token_attempts, start=1):
        payload = {
            "systemInstruction": {
                "parts": [{"text": SYSTEM_PROMPT}],
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": user_prompt}],
                }
            ],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseJsonSchema": response_schema,
                "maxOutputTokens": attempt_tokens,
                "temperature": 0.2,
                "thinkingConfig": {
                    "thinkingBudget": 0,
                },
            },
        }

        try:
            response = requests.post(
                _GEMINI_API_URL.format(model=GEMINI_MODEL),
                params={"key": GEMINI_API_KEY},
                headers={"Content-Type": "application/json"},
                json=payload,
                timeout=_REQUEST_TIMEOUT_SECONDS,
            )
        except requests.RequestException as e:
            logger.error("Gemini network error: %s", e)
            raise RuntimeError(f"Gemini network error: {e}") from e

        if response.status_code >= 400:
            reason = _classify_http_failure(response)
            if _is_permanent_disable_reason(reason):
                _GEMINI_DISABLED_REASON = reason
            if response.status_code in (400, 401, 402, 403, 429):
                logger.warning("Gemini API request failed: %s", _extract_error_message(response))
            else:
                logger.error("Gemini API error %s: %s", response.status_code, _extract_error_message(response))
            last_error = RuntimeError(reason)
            if response.status_code in _TRANSIENT_STATUS_CODES and attempt_index < len(token_attempts):
                time.sleep(2 * attempt_index)
                continue
            raise last_error

        try:
            response_json = response.json()
        except ValueError as e:
            logger.error("Gemini returned invalid JSON envelope: %s", e)
            raise RuntimeError("Gemini returned an invalid response payload.") from e

        raw_text, finish_reason = _extract_text_and_finish_reason(response_json)
        if finish_reason in _RETRYABLE_FINISH_REASONS and attempt_index < len(token_attempts):
            logger.warning(
                "Gemini output hit %s at %s tokens; retrying with a larger limit.",
                finish_reason,
                attempt_tokens,
            )
            time.sleep(1)
            continue

        return raw_text

    if last_error:
        raise last_error
    raise RuntimeError("Gemini request failed after retries.")


def _parse_json_response(raw: str, symbol: str) -> dict:
    """Safely parse JSON from Gemini's response."""
    if not raw:
        return _fallback_signal(symbol, "Empty API response")
    try:
        parsed = json.loads(raw.strip())
        confidence = parsed.get("confidence")
        if isinstance(confidence, (int, float)):
            parsed["confidence"] = max(0, min(10, int(confidence)))
        return parsed
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

    if not _gemini_available():
        _log_disabled_once()
        return _fallback_signal(symbol, _GEMINI_DISABLED_REASON)

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

    logger.info("Sending %s to Gemini (%s) for %s analysis...", symbol, GEMINI_MODEL, trade_type)
    try:
        raw = _call_gemini(prompt, _SIGNAL_SCHEMA)
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

    if not _gemini_available():
        _log_disabled_once()
        return {
            "market_bias": "UNKNOWN",
            "top_picks": [],
            "sectors_to_watch": [],
            "overall_summary": "AI market summary unavailable for this run.",
            "caution_notes": _GEMINI_DISABLED_REASON,
        }

    prompt = build_watchlist_summary_prompt(signals)
    try:
        raw = _call_gemini(prompt, _MARKET_SUMMARY_SCHEMA, max_tokens=500)
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
