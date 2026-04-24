"""
analysis/analyzer.py - Technical indicators and timeframe summaries.
Indicators are implemented with pandas/numpy so scans do not depend on heavy TA runtimes.
"""

from compat import disable_blocked_pyarrow

disable_blocked_pyarrow()

import numpy as np
import pandas as pd

from config import (
    EMA_FAST, EMA_SLOW, EMA_TREND, RSI_PERIOD, RSI_OVERBOUGHT, RSI_OVERSOLD,
    MACD_FAST, MACD_SLOW, MACD_SIGNAL, BB_PERIOD, BB_STD, ATR_PERIOD,
    STOCH_K, STOCH_D, VOLUME_MA_PERIOD, ADX_PERIOD, logger
)


def _safe_float(value, default=None):
    try:
        if value is None or pd.isna(value):
            return default
        return round(float(value), 4)
    except Exception:
        return default


def _rsi(close: pd.Series, length: int) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / length, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / length, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _atr(high: pd.Series, low: pd.Series, close: pd.Series, length: int) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / length, adjust=False).mean()


def _adx(high: pd.Series, low: pd.Series, close: pd.Series, length: int):
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = pd.Series(np.where((up_move > down_move) & (up_move > 0), up_move, 0), index=high.index)
    minus_dm = pd.Series(np.where((down_move > up_move) & (down_move > 0), down_move, 0), index=high.index)
    atr = _atr(high, low, close, length).replace(0, np.nan)
    plus_di = 100 * plus_dm.ewm(alpha=1 / length, adjust=False).mean() / atr
    minus_di = 100 * minus_dm.ewm(alpha=1 / length, adjust=False).mean() / atr
    dx = ((plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)) * 100
    adx = dx.ewm(alpha=1 / length, adjust=False).mean()
    return adx, plus_di, minus_di


def _obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    direction = np.sign(close.diff()).fillna(0)
    return (direction * volume).cumsum()


def compute_indicators(df: pd.DataFrame) -> dict:
    """Compute the latest indicator values from OHLCV data."""
    if df.empty or len(df) < 30:
        return {}

    try:
        work = df.copy()
        open_ = work["Open"].astype(float)
        high = work["High"].astype(float)
        low = work["Low"].astype(float)
        close = work["Close"].astype(float)
        volume = work["Volume"].astype(float) if "Volume" in work else pd.Series(0, index=work.index)

        ema9 = close.ewm(span=EMA_FAST, adjust=False).mean()
        ema21 = close.ewm(span=EMA_SLOW, adjust=False).mean()
        ema50 = close.ewm(span=EMA_TREND, adjust=False).mean()
        ema200 = close.ewm(span=200, adjust=False).mean()

        typical_price = (high + low + close) / 3
        vwap = (typical_price * volume).cumsum() / volume.replace(0, np.nan).cumsum()

        rsi = _rsi(close, RSI_PERIOD)
        macd = close.ewm(span=MACD_FAST, adjust=False).mean() - close.ewm(span=MACD_SLOW, adjust=False).mean()
        macd_signal = macd.ewm(span=MACD_SIGNAL, adjust=False).mean()
        macd_hist = macd - macd_signal

        lowest_low = low.rolling(STOCH_K).min()
        highest_high = high.rolling(STOCH_K).max()
        stoch_k = 100 * (close - lowest_low) / (highest_high - lowest_low).replace(0, np.nan)
        stoch_d = stoch_k.rolling(STOCH_D).mean()

        atr = _atr(high, low, close, ATR_PERIOD)
        bb_mid = close.rolling(BB_PERIOD).mean()
        bb_std = close.rolling(BB_PERIOD).std()
        bb_upper = bb_mid + (bb_std * BB_STD)
        bb_lower = bb_mid - (bb_std * BB_STD)
        obv = _obv(close, volume)
        adx, dmp, dmn = _adx(high, low, close, ADX_PERIOD)

        volume_sma = volume.rolling(VOLUME_MA_PERIOD).mean()
        volume_ratio = volume / volume_sma.replace(0, np.nan)

        prev = work.iloc[-2]
        latest_close = _safe_float(close.iloc[-1])
        latest_open = _safe_float(open_.iloc[-1])
        latest_high = _safe_float(high.iloc[-1])
        latest_low = _safe_float(low.iloc[-1])
        latest_volume = _safe_float(volume.iloc[-1])
        latest_atr = _safe_float(atr.iloc[-1])

        ema9_val = _safe_float(ema9.iloc[-1])
        ema21_val = _safe_float(ema21.iloc[-1])
        ema50_val = _safe_float(ema50.iloc[-1])
        ema200_val = _safe_float(ema200.iloc[-1])
        trend = "uptrend" if (ema9_val and ema21_val and ema50_val and ema9_val > ema21_val > ema50_val) else \
                "downtrend" if (ema9_val and ema21_val and ema50_val and ema9_val < ema21_val < ema50_val) else "sideways"

        vwap_val = _safe_float(vwap.iloc[-1])
        vwap_position = None
        if vwap_val and latest_close:
            vwap_position = "above_vwap" if latest_close > vwap_val else "below_vwap"

        macd_val = _safe_float(macd.iloc[-1])
        macd_sig_val = _safe_float(macd_signal.iloc[-1])
        macd_hist_val = _safe_float(macd_hist.iloc[-1])
        macd_crossover = None
        if len(macd) >= 2 and macd_val is not None and macd_sig_val is not None:
            if macd.iloc[-2] < macd_signal.iloc[-2] and macd.iloc[-1] > macd_signal.iloc[-1]:
                macd_crossover = "bullish_crossover"
            elif macd.iloc[-2] > macd_signal.iloc[-2] and macd.iloc[-1] < macd_signal.iloc[-1]:
                macd_crossover = "bearish_crossover"

        rsi_val = _safe_float(rsi.iloc[-1])
        rsi_signal = "overbought" if (rsi_val and rsi_val > RSI_OVERBOUGHT) else \
                     "oversold" if (rsi_val and rsi_val < RSI_OVERSOLD) else "neutral"

        bb_upper_val = _safe_float(bb_upper.iloc[-1])
        bb_lower_val = _safe_float(bb_lower.iloc[-1])
        bb_mid_val = _safe_float(bb_mid.iloc[-1])
        bb_signal = "inside_bands"
        if latest_close and bb_upper_val and latest_close > bb_upper_val:
            bb_signal = "above_upper_band"
        elif latest_close and bb_lower_val and latest_close < bb_lower_val:
            bb_signal = "below_lower_band"

        vol_ratio_val = _safe_float(volume_ratio.iloc[-1])
        vol_signal = "high_volume" if (vol_ratio_val and vol_ratio_val > 1.5) else \
                     "low_volume" if (vol_ratio_val and vol_ratio_val < 0.7) else "normal_volume"

        prev_high = float(prev["High"])
        prev_low = float(prev["Low"])
        prev_close = float(prev["Close"])
        pivot = (prev_high + prev_low + prev_close) / 3
        r1 = (2 * pivot) - prev_low
        s1 = (2 * pivot) - prev_high
        r2 = pivot + (prev_high - prev_low)
        s2 = pivot - (prev_high - prev_low)

        stoch_k_val = _safe_float(stoch_k.iloc[-1])
        stoch_d_val = _safe_float(stoch_d.iloc[-1])
        stoch_signal = "overbought" if (stoch_k_val and stoch_k_val > 80) else \
                       "oversold" if (stoch_k_val and stoch_k_val < 20) else "neutral"

        adx_val = _safe_float(adx.iloc[-1])
        dmp_val = _safe_float(dmp.iloc[-1])
        dmn_val = _safe_float(dmn.iloc[-1])
        adx_direction = "bullish" if (dmp_val and dmn_val and dmp_val > dmn_val) else \
                        "bearish" if (dmp_val and dmn_val and dmn_val > dmp_val) else "neutral"
        atr_pct = round((latest_atr / latest_close) * 100, 2) if latest_atr and latest_close else None

        return {
            "close": latest_close,
            "open": latest_open,
            "high": latest_high,
            "low": latest_low,
            "volume": latest_volume,
            "volume_ratio": vol_ratio_val,
            "volume_signal": vol_signal,
            "ema_fast": ema9_val,
            "ema_slow": ema21_val,
            "ema_trend": ema50_val,
            "ema_200": ema200_val,
            "vwap": vwap_val,
            "vwap_position": vwap_position,
            "trend": trend,
            "rsi": rsi_val,
            "rsi_signal": rsi_signal,
            "macd": macd_val,
            "macd_signal_line": macd_sig_val,
            "macd_histogram": macd_hist_val,
            "macd_crossover": macd_crossover,
            "stoch_k": stoch_k_val,
            "stoch_d": stoch_d_val,
            "stoch_signal": stoch_signal,
            "atr": latest_atr,
            "atr_pct": atr_pct,
            "adx": adx_val,
            "adx_direction": adx_direction,
            "dmp": dmp_val,
            "dmn": dmn_val,
            "bb_upper": bb_upper_val,
            "bb_lower": bb_lower_val,
            "bb_mid": bb_mid_val,
            "bb_signal": bb_signal,
            "pivot": _safe_float(pivot),
            "r1": _safe_float(r1),
            "r2": _safe_float(r2),
            "s1": _safe_float(s1),
            "s2": _safe_float(s2),
            "obv": _safe_float(obv.iloc[-1]),
        }

    except Exception as e:
        logger.error("Indicator computation failed: %s", e)
        return {}


def get_ohlcv_summary(df: pd.DataFrame, n_candles: int = 10) -> str:
    """Return a human-readable summary of last N candles for the prompt."""
    if df.empty:
        return "No data"
    recent = df.tail(n_candles)[["Open", "High", "Low", "Close", "Volume"]]
    lines = [f"Last {n_candles} candles:"]
    for ts, row in recent.iterrows():
        lines.append(
            f"  {str(ts)[:16]}  O:{row['Open']:.2f}  H:{row['High']:.2f}"
            f"  L:{row['Low']:.2f}  C:{row['Close']:.2f}  V:{int(row['Volume']):,}"
        )
    return "\n".join(lines)


def analyze_timeframes(frames: dict) -> dict:
    """Compute indicators and compact OHLCV summaries for every available timeframe."""
    result = {}
    for timeframe, df in frames.items():
        indicators = compute_indicators(df)
        if not indicators:
            continue
        result[timeframe] = {
            "indicators": indicators,
            "summary": get_ohlcv_summary(df, n_candles=6),
            "rows": len(df),
        }
    return result


def summarize_timeframe_alignment(timeframes: dict) -> dict:
    """Score whether 5m, 1h, and 1d trends point in the same direction."""
    trends = {
        tf: data.get("indicators", {}).get("trend", "unknown")
        for tf, data in timeframes.items()
    }
    up = sum(1 for trend in trends.values() if trend == "uptrend")
    down = sum(1 for trend in trends.values() if trend == "downtrend")
    if up >= 2:
        alignment = "bullish"
    elif down >= 2:
        alignment = "bearish"
    else:
        alignment = "mixed"
    return {
        "alignment": alignment,
        "trend_by_timeframe": trends,
        "score": up - down,
    }
