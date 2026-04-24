"""
data/fetcher.py - Fetch OHLCV price data for NSE stocks.
Primary source: yfinance (free, no API key needed).
Falls back to cached data if fetch fails during market hours.
"""

import time
import requests
from compat import disable_blocked_pyarrow

disable_blocked_pyarrow()

import pandas as pd
import yfinance as yf
from datetime import datetime
from config import (
    NSE_SUFFIX, INTRADAY_INTERVAL, INTRADAY_PERIOD,
    SWING_INTERVAL, SWING_PERIOD, MULTI_TIMEFRAME_CONFIG, logger
)
from data.cache import get_ohlcv_cache, set_ohlcv_cache


# NSE headers needed to scrape their unofficial API
NSE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com",
}


def _nse_ticker(symbol: str) -> str:
    if symbol.startswith("^") or symbol.endswith(".NS") or symbol.endswith(".BO"):
        return symbol
    return f"{symbol}{NSE_SUFFIX}"


def _serialize_ohlcv_for_cache(df: pd.DataFrame) -> dict:
    """Convert a DataFrame to a JSON-safe dict for SQLite caching."""
    cached_df = df.copy()
    cached_df.index = cached_df.index.astype(str)
    return cached_df.to_dict()


def fetch_ohlcv(symbol: str, interval: str = INTRADAY_INTERVAL,
                period: str = INTRADAY_PERIOD, use_cache: bool = True) -> pd.DataFrame:
    """
    Fetch OHLCV candles for a symbol.
    Returns a DataFrame with columns: Open, High, Low, Close, Volume.
    """
    if use_cache:
        cached = get_ohlcv_cache(symbol, interval, period)
        if cached:
            logger.debug("Cache hit for %s %s/%s", symbol, interval, period)
            df = pd.DataFrame(cached)
            df.index = pd.to_datetime(df.index)
            return df

    ticker = _nse_ticker(symbol)
    try:
        logger.info("Fetching %s [%s/%s] from yfinance", symbol, interval, period)
        df = yf.download(
            ticker,
            period=period,
            interval=interval,
            progress=False,
            auto_adjust=True,
        )
        if df.empty:
            logger.warning("No data returned for %s", symbol)
            return pd.DataFrame()

        # Flatten MultiIndex columns if present
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        df.dropna(inplace=True)

        if use_cache:
            set_ohlcv_cache(symbol, interval, period, _serialize_ohlcv_for_cache(df))

        time.sleep(0.3)  # polite rate limiting
        return df

    except Exception as e:
        logger.error("Failed to fetch %s: %s", symbol, e)
        return pd.DataFrame()


def fetch_intraday(symbol: str) -> pd.DataFrame:
    return fetch_ohlcv(symbol, INTRADAY_INTERVAL, INTRADAY_PERIOD)


def fetch_swing(symbol: str) -> pd.DataFrame:
    return fetch_ohlcv(symbol, SWING_INTERVAL, SWING_PERIOD)


def fetch_multi_timeframe(symbol: str) -> dict:
    """
    Fetch 5m, 1h, and 1d OHLCV frames for a symbol.
    Returns {timeframe: DataFrame}; empty frames are kept out of the result.
    """
    frames = {}
    for timeframe, cfg in MULTI_TIMEFRAME_CONFIG.items():
        df = fetch_ohlcv(symbol, cfg["interval"], cfg["period"])
        if not df.empty:
            frames[timeframe] = df
    return frames


def fetch_market_index(symbol: str, interval: str = "1d", period: str = "3mo") -> pd.DataFrame:
    """Fetch index data such as ^NSEI, ^NSEBANK, or ^INDIAVIX without NSE suffixing."""
    return fetch_ohlcv(symbol, interval=interval, period=period)


def fetch_option_chain(symbol: str) -> dict:
    """
    Fetch NSE option chain data.
    Returns dict with PCR, max pain, and key OI levels.
    """
    session = requests.Session()
    try:
        # Warm up NSE session (required for cookies)
        session.get("https://www.nseindia.com", headers=NSE_HEADERS, timeout=10)
        time.sleep(1)

        url = f"https://www.nseindia.com/api/option-chain-equities?symbol={symbol}"
        resp = session.get(url, headers=NSE_HEADERS, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        records = data.get("records", {})
        ce_oi = {}
        pe_oi = {}

        for item in records.get("data", []):
            strike = item.get("strikePrice", 0)
            if "CE" in item:
                ce_oi[strike] = item["CE"].get("openInterest", 0)
            if "PE" in item:
                pe_oi[strike] = item["PE"].get("openInterest", 0)

        total_ce = sum(ce_oi.values())
        total_pe = sum(pe_oi.values())
        pcr = round(total_pe / total_ce, 2) if total_ce else 0

        # Max pain = strike where total OI (CE+PE) is maximum
        max_pain_strike = None
        if ce_oi and pe_oi:
            all_strikes = set(ce_oi) | set(pe_oi)
            max_pain_strike = max(
                all_strikes,
                key=lambda s: ce_oi.get(s, 0) + pe_oi.get(s, 0)
            )

        # Top CE/PE strikes by OI (resistance/support via options)
        top_ce = sorted(ce_oi, key=ce_oi.get, reverse=True)[:3]
        top_pe = sorted(pe_oi, key=pe_oi.get, reverse=True)[:3]

        return {
            "pcr": pcr,
            "max_pain": max_pain_strike,
            "top_ce_resistance": top_ce,
            "top_pe_support": top_pe,
            "sentiment": "bullish" if pcr > 1.2 else ("bearish" if pcr < 0.8 else "neutral"),
        }

    except Exception as e:
        logger.warning("Option chain fetch failed for %s: %s", symbol, e)
        return {"pcr": None, "max_pain": None, "sentiment": "unknown"}


def get_current_price(symbol: str) -> float:
    """Get latest traded price quickly."""
    try:
        ticker = yf.Ticker(_nse_ticker(symbol))
        info = ticker.fast_info
        return round(float(info.last_price), 2)
    except Exception:
        return 0.0


def fetch_batch(symbols: list, interval: str = INTRADAY_INTERVAL,
                period: str = INTRADAY_PERIOD) -> dict:
    """Fetch OHLCV for multiple symbols. Returns {symbol: DataFrame}."""
    result = {}
    for sym in symbols:
        df = fetch_ohlcv(sym, interval, period)
        if not df.empty:
            result[sym] = df
        time.sleep(0.2)
    return result
