"""
config.py - Central configuration for Stock Analyzer
All constants, paths, and settings live here.
"""

import os
import json
import logging
from pathlib import Path
from dotenv import load_dotenv

# ── Paths ──────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
WATCHLIST_PATH = BASE_DIR / "watchlist.json"
DB_PATH = BASE_DIR / "db" / "signals.db"
LOG_PATH = BASE_DIR / "logs" / "analyzer.log"
REPORTS_DIR = BASE_DIR / "output" / "reports"

# ── Load env ───────────────────────────────────────────────────────────────────
load_dotenv(BASE_DIR / ".env")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# ── Market settings ────────────────────────────────────────────────────────────
NSE_SUFFIX = ".NS"
INTRADAY_INTERVAL = "5m"
INTRADAY_PERIOD = "5d"
HOURLY_INTERVAL = "1h"
HOURLY_PERIOD = "60d"
SWING_INTERVAL = "1d"
SWING_PERIOD = "1y"
MULTI_TIMEFRAME_CONFIG = {
    "5m": {"interval": INTRADAY_INTERVAL, "period": INTRADAY_PERIOD},
    "1h": {"interval": HOURLY_INTERVAL, "period": HOURLY_PERIOD},
    "1d": {"interval": SWING_INTERVAL, "period": SWING_PERIOD},
}

# ── AI Model ───────────────────────────────────────────────────────────────────
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
MAX_TOKENS = 800

# ── Scheduler (IST) ───────────────────────────────────────────────────────────
PREMARKET_SCAN_HOUR = int(os.getenv("PREMARKET_SCAN_HOUR", 8))
PREMARKET_SCAN_MINUTE = int(os.getenv("PREMARKET_SCAN_MINUTE", 45))
SCAN_HOUR = int(os.getenv("SCAN_HOUR", 9))
SCAN_MINUTE = int(os.getenv("SCAN_MINUTE", 15))
MIDDAY_SCAN_HOUR = int(os.getenv("MIDDAY_SCAN_HOUR", 12))
MIDDAY_SCAN_MINUTE = int(os.getenv("MIDDAY_SCAN_MINUTE", 0))
EOD_SCAN_HOUR = int(os.getenv("EOD_SCAN_HOUR", 15))
EOD_SCAN_MINUTE = int(os.getenv("EOD_SCAN_MINUTE", 30))
NEXT_SESSION_SCAN_HOUR = int(os.getenv("NEXT_SESSION_SCAN_HOUR", 16))
NEXT_SESSION_SCAN_MINUTE = int(os.getenv("NEXT_SESSION_SCAN_MINUTE", 0))

# ── Technical indicator parameters ────────────────────────────────────────────
EMA_FAST = 9
EMA_SLOW = 21
EMA_TREND = 50
RSI_PERIOD = 14
RSI_OVERBOUGHT = 70
RSI_OVERSOLD = 30
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9
BB_PERIOD = 20
BB_STD = 2
ATR_PERIOD = 14
STOCH_K = 14
STOCH_D = 3
VOLUME_MA_PERIOD = 20
ADX_PERIOD = 14

# ── Signal thresholds ─────────────────────────────────────────────────────────
def load_watchlist():
    with open(WATCHLIST_PATH) as f:
        return json.load(f)

DEFAULT_SETTINGS = {
    "min_confidence": 7,
    "min_volume_ratio": 1.2,
    "account_size": 500000,
    "intraday_risk_per_trade_pct": 1.0,
    "swing_risk_per_trade_pct": 2.0,
    "atr_sl_multiplier": 1.5,
    "rr_ratio_min": 1.5,
    "top_n_setups": 5,
}

def get_settings():
    settings = DEFAULT_SETTINGS.copy()
    settings.update(load_watchlist().get("settings", {}))
    return settings

# ── Logging ───────────────────────────────────────────────────────────────────
def setup_logging():
    LOG_PATH.parent.mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(LOG_PATH),
            logging.StreamHandler(),
        ],
    )
    return logging.getLogger("stock_analyzer")

logger = setup_logging()
