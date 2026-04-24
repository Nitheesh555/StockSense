"""
analysis/signals.py - Calculate entry price, target, and stop-loss levels.
Uses ATR-based stops and pivot-based targets. Works independently of AI.
"""

from config import get_settings, logger


def calculate_trade_levels(indicators: dict, trade_type: str = "INTRADAY") -> dict:
    """
    Calculate entry, target, and stop-loss based on indicators.
    Returns a dict with price levels and risk/reward ratio.

    This is used both as a sanity check on AI output and as a standalone
    fallback when the AI signal matches but needs refined levels.
    """
    close = indicators.get("close")
    atr = indicators.get("atr")
    s1 = indicators.get("s1")
    s2 = indicators.get("s2")
    r1 = indicators.get("r1")
    r2 = indicators.get("r2")
    vwap = indicators.get("vwap")
    trend = indicators.get("trend", "sideways")

    if not close or not atr:
        return {}

    settings = get_settings()
    atr_multiplier = settings.get("atr_sl_multiplier", 1.5)
    if trade_type == "SWING":
        atr_multiplier = max(atr_multiplier, 2.0)

    # ── BUY levels ─────────────────────────────────────────────────────────────
    buy_entry = close
    buy_sl = round(close - (atr * atr_multiplier), 2)
    # Target: next resistance, or 2× risk if no pivot available
    risk = close - buy_sl
    buy_target_1 = round(r1 if r1 and r1 > close else close + (risk * 2), 2)
    buy_target_2 = round(r2 if r2 and r2 > close else close + (risk * 3), 2)
    buy_rr = round((buy_target_1 - buy_entry) / (buy_entry - buy_sl), 2) if buy_entry != buy_sl else 0

    # ── SELL levels ────────────────────────────────────────────────────────────
    sell_entry = close
    sell_sl = round(close + (atr * atr_multiplier), 2)
    sell_risk = sell_sl - close
    sell_target_1 = round(s1 if s1 and s1 < close else close - (sell_risk * 2), 2)
    sell_target_2 = round(s2 if s2 and s2 < close else close - (sell_risk * 3), 2)
    sell_rr = round((sell_entry - sell_target_1) / (sell_sl - sell_entry), 2) if sell_entry != sell_sl else 0

    return {
        "buy": {
            "entry": buy_entry,
            "stop_loss": buy_sl,
            "target_1": buy_target_1,
            "target_2": buy_target_2,
            "risk_reward": buy_rr,
            "risk_points": round(risk, 2),
        },
        "sell": {
            "entry": sell_entry,
            "stop_loss": sell_sl,
            "target_1": sell_target_1,
            "target_2": sell_target_2,
            "risk_reward": sell_rr,
            "risk_points": round(sell_risk, 2),
        },
        "atr": round(atr, 2),
        "vwap": vwap,
        "trend": trend,
    }


def position_size(capital: float, risk_pct: float, entry: float, stop_loss: float) -> dict:
    """
    Calculate position size based on risk per trade.

    Args:
        capital: Total trading capital in INR
        risk_pct: Percent of capital to risk (e.g., 1.0 for 1%)
        entry: Entry price
        stop_loss: Stop-loss price

    Returns:
        Dict with quantity, max_loss, and capital_used
    """
    if entry <= 0 or stop_loss <= 0 or entry == stop_loss:
        return {}

    risk_amount = capital * (risk_pct / 100)
    risk_per_share = abs(entry - stop_loss)
    quantity = int(risk_amount / risk_per_share)
    capital_used = round(quantity * entry, 2)
    actual_risk = round(quantity * risk_per_share, 2)

    return {
        "quantity": quantity,
        "capital_used": capital_used,
        "max_loss": actual_risk,
        "max_loss_pct": round((actual_risk / capital) * 100, 2),
    }


def conviction_label(score: int) -> str:
    if score >= 8:
        return "High Conviction"
    if score >= 5:
        return "Moderate"
    return "Low / Skip"


def enrich_signal_with_risk(signal: dict, indicators: dict, trade_type: str, settings: dict = None) -> dict:
    """Attach configured position sizing, volatility, and conviction metadata."""
    settings = settings or get_settings()
    entry = signal.get("entry_price")
    stop_loss = signal.get("stop_loss")
    risk_pct_key = "swing_risk_per_trade_pct" if trade_type == "SWING" else "intraday_risk_per_trade_pct"
    sizing = {}
    if entry and stop_loss:
        sizing = position_size(
            capital=float(settings.get("account_size", 500000)),
            risk_pct=float(settings.get(risk_pct_key, 1.0)),
            entry=float(entry),
            stop_loss=float(stop_loss),
        )

    atr_pct = indicators.get("atr_pct")
    volatility_flag = None
    quantity = sizing.get("quantity")
    if atr_pct and atr_pct > 3:
        volatility_flag = "High Volatility - Reduce Position Size"
        if quantity:
            quantity = max(1, quantity // 2)
    elif atr_pct:
        volatility_flag = "Normal Volatility"

    confidence = int(signal.get("confidence") or 0)
    signal["quantity"] = quantity
    signal["position_size"] = sizing
    signal["volatility_flag"] = volatility_flag
    signal["conviction_label"] = signal.get("conviction_label") or conviction_label(confidence)
    return signal


def assess_signal_quality(indicators: dict, levels: dict, direction: str) -> dict:
    """
    Score a potential signal from 1-10 based on indicator confluence.
    More confirming indicators = higher score.
    """
    score = 0
    reasons = []

    rsi = indicators.get("rsi")
    trend = indicators.get("trend")
    vwap_pos = indicators.get("vwap_position")
    macd_cross = indicators.get("macd_crossover")
    bb_signal = indicators.get("bb_signal")
    vol_signal = indicators.get("volume_signal")
    stoch = indicators.get("stoch_signal")

    if direction == "BUY":
        if trend == "uptrend":
            score += 2; reasons.append("uptrend confirmed")
        if rsi and 40 < rsi < 65:
            score += 1; reasons.append("RSI in healthy zone")
        if rsi and rsi < RSI_OVERSOLD_THRESHOLD:
            score += 2; reasons.append("RSI oversold - bounce setup")
        if vwap_pos == "above_vwap":
            score += 1; reasons.append("price above VWAP")
        if macd_cross == "bullish_crossover":
            score += 2; reasons.append("MACD bullish crossover")
        if bb_signal == "below_lower_band":
            score += 1; reasons.append("BB lower band bounce")
        if stoch == "oversold":
            score += 1; reasons.append("stochastic oversold")
        if vol_signal == "high_volume":
            score += 1; reasons.append("above-average volume")

    elif direction == "SELL":
        if trend == "downtrend":
            score += 2; reasons.append("downtrend confirmed")
        if rsi and rsi > RSI_OVERBOUGHT_THRESHOLD:
            score += 2; reasons.append("RSI overbought")
        if vwap_pos == "below_vwap":
            score += 1; reasons.append("price below VWAP")
        if macd_cross == "bearish_crossover":
            score += 2; reasons.append("MACD bearish crossover")
        if bb_signal == "above_upper_band":
            score += 1; reasons.append("BB upper band rejection")
        if stoch == "overbought":
            score += 1; reasons.append("stochastic overbought")
        if vol_signal == "high_volume":
            score += 1; reasons.append("above-average volume")

    rr = levels.get(direction.lower(), {}).get("risk_reward", 0)
    if rr >= 3:
        score += 1; reasons.append(f"excellent R:R {rr}")
    elif rr >= 2:
        reasons.append(f"good R:R {rr}")

    return {
        "score": min(score, 10),
        "reasons": reasons,
    }


# Constants needed inside this module
RSI_OVERSOLD_THRESHOLD = 35
RSI_OVERBOUGHT_THRESHOLD = 65
