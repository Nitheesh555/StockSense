"""
context/market_context.py - Best-effort market pulse for Indian equities.
All context is optional; failures are represented as unavailable fields.
"""

from collections import Counter

from analysis.analyzer import compute_indicators
from data.fetcher import fetch_market_index
from config import logger

INDEXES = {
    "nifty": "^NSEI",
    "bank_nifty": "^NSEBANK",
    "india_vix": "^INDIAVIX",
}


def _index_context(label: str, ticker: str) -> dict:
    try:
        df = fetch_market_index(ticker, interval="1d", period="3mo")
        if df.empty:
            return {"label": label, "symbol": ticker, "status": "unavailable"}
        ind = compute_indicators(df)
        close = ind.get("close")
        previous_close = float(df["Close"].iloc[-2]) if len(df) > 1 else None
        change_pct = None
        if close and previous_close:
            change_pct = round(((close - previous_close) / previous_close) * 100, 2)
        return {
            "label": label,
            "symbol": ticker,
            "status": "available",
            "close": close,
            "change_pct": change_pct,
            "trend": ind.get("trend", "unknown"),
            "rsi": ind.get("rsi"),
            "adx": ind.get("adx"),
        }
    except Exception as exc:
        logger.warning("Market context fetch failed for %s: %s", ticker, exc)
        return {"label": label, "symbol": ticker, "status": "unavailable", "error": str(exc)}


def infer_sector_strength(fundamentals_by_symbol: dict) -> list:
    """Infer rough sector focus from available Screener sectors."""
    counter = Counter()
    for fundamentals in fundamentals_by_symbol.values():
        sector = fundamentals.get("sector") if isinstance(fundamentals, dict) else None
        if sector and sector != "Unknown":
            counter[sector] += 1
    return [sector for sector, _ in counter.most_common(3)]


def build_market_context(fundamentals_by_symbol: dict = None) -> dict:
    fundamentals_by_symbol = fundamentals_by_symbol or {}
    indexes = {name: _index_context(name, ticker) for name, ticker in INDEXES.items()}
    nifty = indexes.get("nifty", {})
    bank = indexes.get("bank_nifty", {})

    bullish = sum(1 for item in (nifty, bank) if item.get("trend") == "uptrend")
    bearish = sum(1 for item in (nifty, bank) if item.get("trend") == "downtrend")
    if bullish > bearish:
        bias = "BULLISH"
    elif bearish > bullish:
        bias = "BEARISH"
    else:
        bias = "MIXED"

    return {
        "market_bias": bias,
        "indexes": indexes,
        "sector_strength": infer_sector_strength(fundamentals_by_symbol) or ["Unavailable"],
        "fii_dii": {
            "status": "unavailable",
            "note": "FII/DII flow is not available from the configured free sources in this run.",
        },
        "expiry_awareness": "Check weekly/monthly expiry manually before taking F&O-heavy trades.",
    }
