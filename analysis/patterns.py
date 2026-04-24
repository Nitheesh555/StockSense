"""
analysis/patterns.py - Detect common chart patterns and setups.
All pattern detection is rule-based (no ML), runs locally for free.
"""

from compat import disable_blocked_pyarrow

disable_blocked_pyarrow()

import pandas as pd
import numpy as np
from config import logger


def detect_patterns(df: pd.DataFrame, indicators: dict) -> list:
    """
    Detect chart patterns in the OHLCV data.
    Returns a list of detected pattern names (strings).
    """
    if df.empty or len(df) < 10:
        return []

    patterns = []
    close = df["Close"]
    high = df["High"]
    low = df["Low"]
    volume = df.get("Volume", pd.Series(dtype=float))

    last = df.iloc[-1]
    prev = df.iloc[-2]
    prev2 = df.iloc[-3] if len(df) >= 3 else prev

    # ── Candlestick patterns ──────────────────────────────────────────────────
    body = abs(last["Close"] - last["Open"])
    total_range = last["High"] - last["Low"]
    upper_wick = last["High"] - max(last["Close"], last["Open"])
    lower_wick = min(last["Close"], last["Open"]) - last["Low"]

    if total_range > 0:
        body_ratio = body / total_range

        # Doji
        if body_ratio < 0.1:
            patterns.append("doji (indecision)")

        # Hammer (bullish reversal)
        if (lower_wick > 2 * body and upper_wick < body * 0.5
                and last["Close"] > last["Open"]):
            patterns.append("hammer (bullish reversal)")

        # Shooting star (bearish reversal)
        if (upper_wick > 2 * body and lower_wick < body * 0.5
                and last["Close"] < last["Open"]):
            patterns.append("shooting star (bearish reversal)")

        # Marubozu (strong momentum)
        if body_ratio > 0.85:
            if last["Close"] > last["Open"]:
                patterns.append("bullish marubozu (strong buying)")
            else:
                patterns.append("bearish marubozu (strong selling)")

    # Engulfing patterns (2-candle)
    prev_body = prev["Close"] - prev["Open"]
    last_body = last["Close"] - last["Open"]

    if prev_body < 0 and last_body > 0 and abs(last_body) > abs(prev_body):
        patterns.append("bullish engulfing")
    if prev_body > 0 and last_body < 0 and abs(last_body) > abs(prev_body):
        patterns.append("bearish engulfing")

    # ── Trend patterns ────────────────────────────────────────────────────────
    ema9 = indicators.get("ema_fast")
    ema21 = indicators.get("ema_slow")
    ema50 = indicators.get("ema_trend")
    current_close = indicators.get("close")

    # EMA crossover (fresh)
    if ema9 and ema21:
        prev_ema9 = df.iloc[-2].get(f"EMA_9", None) if hasattr(df.iloc[-2], 'get') else None
        if prev_ema9 is None:
            # Use a rough proxy
            prev_ema9 = prev["Close"]
        if ema9 > ema21:
            patterns.append("EMA 9 above 21 (bullish)")
        else:
            patterns.append("EMA 9 below 21 (bearish)")

    # Price vs VWAP breakout
    vwap = indicators.get("vwap")
    if vwap and current_close:
        pct_diff = ((current_close - vwap) / vwap) * 100
        if pct_diff > 0.5:
            patterns.append("breakout above VWAP")
        elif pct_diff < -0.5:
            patterns.append("breakdown below VWAP")

    # ── Breakout / Breakdown from recent highs/lows ───────────────────────────
    window = 10
    if len(df) >= window + 1:
        recent_high = df["High"].iloc[-window-1:-1].max()
        recent_low = df["Low"].iloc[-window-1:-1].min()
        last_close = df["Close"].iloc[-1]

        if last_close > recent_high:
            patterns.append(f"{window}-candle breakout (resistance cleared)")
        elif last_close < recent_low:
            patterns.append(f"{window}-candle breakdown (support broken)")

    # ── Volume breakout ───────────────────────────────────────────────────────
    vol_ratio = indicators.get("volume_ratio")
    if vol_ratio and vol_ratio > 2.0:
        patterns.append("volume spike (2x+ average)")

    # ── Inside bar ────────────────────────────────────────────────────────────
    if (last["High"] < prev["High"] and last["Low"] > prev["Low"]):
        patterns.append("inside bar (compression before move)")

    # ── Double top / bottom (simplified) ─────────────────────────────────────
    if len(df) >= 20:
        highs = df["High"].iloc[-20:]
        lows = df["Low"].iloc[-20:]
        max_high = highs.max()
        min_low = lows.min()
        high_idx = highs.idxmax()
        low_idx = lows.idxmin()

        # If two similar highs exist within 0.5% range
        highs_near_max = highs[abs(highs - max_high) / max_high < 0.005]
        if len(highs_near_max) >= 2 and current_close and current_close < max_high * 0.99:
            patterns.append("potential double top")

        lows_near_min = lows[abs(lows - min_low) / min_low < 0.005]
        if len(lows_near_min) >= 2 and current_close and current_close > min_low * 1.01:
            patterns.append("potential double bottom")

    return patterns
