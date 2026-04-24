"""
analysis/setup_engine.py - Rule-based setup classification and next-session outlook.
These rules give GPT structured context and provide safe fallback fields.
"""

from analysis.signals import conviction_label


def _score_from_conditions(conditions):
    score = sum(points for ok, points, _ in conditions if ok)
    reasons = [reason for ok, _, reason in conditions if ok]
    return min(10, max(1, score)), reasons


def detect_intraday_setup(frames: dict, indicators: dict, alignment: dict, patterns: list) -> dict:
    df_5m = frames.get("5m")
    close = indicators.get("close")
    vwap = indicators.get("vwap")
    rsi = indicators.get("rsi")
    volume_ratio = indicators.get("volume_ratio") or 0
    macd_hist = indicators.get("macd_histogram") or 0

    setup_type = "Momentum Scalp"
    direction = "BUY" if alignment.get("alignment") == "bullish" else "SELL" if alignment.get("alignment") == "bearish" else "AVOID"

    if close and vwap:
        if close > vwap and indicators.get("vwap_position") == "above_vwap":
            setup_type = "VWAP Reclaim"
            direction = "BUY"
        elif close < vwap and indicators.get("vwap_position") == "below_vwap":
            setup_type = "VWAP Rejection"
            direction = "SELL"

    if df_5m is not None and len(df_5m) >= 4:
        day = df_5m.tail(80)
        opening = day.head(3)
        if len(opening) == 3:
            orb_high = float(opening["High"].max())
            orb_low = float(opening["Low"].min())
            if close and close > orb_high:
                setup_type = "Opening Range Breakout"
                direction = "BUY"
            elif close and close < orb_low:
                setup_type = "Opening Range Breakdown"
                direction = "SELL"

    conditions = [
        (direction == "BUY" and alignment.get("alignment") == "bullish", 2, "multi-timeframe bullish alignment"),
        (direction == "SELL" and alignment.get("alignment") == "bearish", 2, "multi-timeframe bearish alignment"),
        (volume_ratio >= 1.5, 2, "volume confirmation above 1.5x average"),
        (rsi is not None and 35 <= rsi <= 68, 1, "RSI in tradable momentum zone"),
        (direction == "BUY" and macd_hist > 0, 1, "positive MACD histogram"),
        (direction == "SELL" and macd_hist < 0, 1, "negative MACD histogram"),
        (any("engulfing" in p or "breakout" in p or "breakdown" in p for p in patterns), 1, "supporting pattern detected"),
    ]
    score, reasons = _score_from_conditions(conditions)
    return {
        "setup_type": setup_type,
        "direction": direction,
        "score_hint": score,
        "label": conviction_label(score),
        "reasons": reasons,
    }


def detect_swing_setup(indicators: dict, alignment: dict, patterns: list) -> dict:
    close = indicators.get("close")
    ema21 = indicators.get("ema_slow")
    adx = indicators.get("adx") or 0
    adx_direction = indicators.get("adx_direction")
    volume_ratio = indicators.get("volume_ratio") or 0
    setup_type = "Trend Continuation"
    direction = "BUY" if alignment.get("alignment") == "bullish" else "SELL" if alignment.get("alignment") == "bearish" else "AVOID"

    if close and ema21:
        distance = abs(close - ema21) / ema21
        if distance <= 0.02 and alignment.get("alignment") == "bullish":
            setup_type = "Pullback to 21 EMA"
            direction = "BUY"
    if any("breakout" in p for p in patterns) and volume_ratio >= 1.5:
        setup_type = "Breakout with Volume Surge"
        direction = "BUY"
    if any("breakdown" in p for p in patterns) and volume_ratio >= 1.5:
        setup_type = "Breakdown with Volume Surge"
        direction = "SELL"

    conditions = [
        (alignment.get("alignment") in ("bullish", "bearish"), 2, "multi-timeframe trend alignment"),
        (adx >= 20, 2, f"ADX trend strength {adx}"),
        (direction == "BUY" and adx_direction == "bullish", 1, "ADX direction bullish"),
        (direction == "SELL" and adx_direction == "bearish", 1, "ADX direction bearish"),
        (volume_ratio >= 1.5, 2, "volume surge above 1.5x average"),
        (any("breakout" in p or "pullback" in p or "EMA" in p for p in patterns), 1, "supporting swing pattern"),
    ]
    score, reasons = _score_from_conditions(conditions)
    return {
        "setup_type": setup_type,
        "direction": direction,
        "score_hint": score,
        "label": conviction_label(score),
        "reasons": reasons,
    }


def build_next_session_outlook(indicators: dict, alignment: dict) -> dict:
    close = indicators.get("close")
    vwap = indicators.get("vwap")
    rsi = indicators.get("rsi") or 50
    macd_hist = indicators.get("macd_histogram") or 0
    ema21 = indicators.get("ema_slow")
    ema50 = indicators.get("ema_trend")

    score = 50
    reasons = []
    if close and vwap:
        if close > vwap:
            score += 10
            reasons.append("closing above VWAP")
        else:
            score -= 10
            reasons.append("closing below VWAP")
    if macd_hist > 0:
        score += 10
        reasons.append("MACD histogram positive")
    elif macd_hist < 0:
        score -= 10
        reasons.append("MACD histogram negative")
    if close and ema21 and ema50:
        if close > ema21 > ema50:
            score += 15
            reasons.append("price above 21/50 EMA")
        elif close < ema21 < ema50:
            score -= 15
            reasons.append("price below 21/50 EMA")
    if rsi >= 60:
        score += 5
        reasons.append("RSI momentum supportive")
    elif rsi <= 40:
        score -= 5
        reasons.append("RSI momentum weak")
    if alignment.get("alignment") == "bullish":
        score += 10
    elif alignment.get("alignment") == "bearish":
        score -= 10

    score = max(1, min(99, int(score)))
    if score >= 60:
        bias = "Bullish"
        gap_probability = "High" if score >= 75 else "Moderate"
    elif score <= 40:
        bias = "Bearish"
        gap_probability = "High" if score <= 25 else "Moderate"
    else:
        bias = "Neutral"
        gap_probability = "Low"

    return {
        "bias": bias,
        "confidence": score if bias != "Bearish" else 100 - score,
        "gap_probability": gap_probability,
        "watch_level": indicators.get("r1") if bias == "Bullish" else indicators.get("s1"),
        "support": indicators.get("s1"),
        "resistance": indicators.get("r1"),
        "reasons": reasons[:4],
        "pre_market_checklist": "Check index futures, opening volume, VWAP hold/reject, and first 15-minute range.",
    }


def build_setup_context(trade_type: str, frames: dict, indicators: dict, alignment: dict, patterns: list) -> dict:
    if trade_type == "SWING":
        setup = detect_swing_setup(indicators, alignment, patterns)
    else:
        setup = detect_intraday_setup(frames, indicators, alignment, patterns)
    setup["next_session"] = build_next_session_outlook(indicators, alignment)
    return setup
