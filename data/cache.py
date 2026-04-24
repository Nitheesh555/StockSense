"""
data/cache.py - SQLite-based local cache for OHLCV data and signal history.
Avoids re-fetching data on multiple runs and stores all past signals.
"""

import sqlite3
import json
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from config import DB_PATH, logger


def _conn():
    DB_PATH.parent.mkdir(exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def init_db():
    """Create tables if they don't exist."""
    with _conn() as con:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS ohlcv_cache (
                key TEXT PRIMARY KEY,
                data TEXT NOT NULL,
                fetched_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS fundamentals_cache (
                symbol TEXT PRIMARY KEY,
                data TEXT NOT NULL,
                fetched_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                signal TEXT NOT NULL,
                trade_type TEXT NOT NULL,
                confidence INTEGER NOT NULL,
                entry_price REAL,
                target_price REAL,
                target_2_price REAL,
                stop_loss REAL,
                risk_reward_ratio REAL,
                reasoning TEXT,
                pattern_detected TEXT,
                risk_factors TEXT,
                best_entry_time TEXT,
                setup_type TEXT,
                conviction_label TEXT,
                quantity INTEGER,
                volatility_flag TEXT,
                next_session_bias TEXT,
                next_session_confidence INTEGER,
                support REAL,
                resistance REAL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS intelligence_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_type TEXT NOT NULL,
                markdown TEXT NOT NULL,
                data TEXT,
                created_at TEXT NOT NULL
            );
        """)
        _ensure_signal_columns(con)
    logger.info("Database initialized at %s", DB_PATH)


def _ensure_signal_columns(con):
    """Add nullable columns for older local databases."""
    existing = {row["name"] for row in con.execute("PRAGMA table_info(signals)").fetchall()}
    columns = {
        "target_2_price": "REAL",
        "risk_factors": "TEXT",
        "best_entry_time": "TEXT",
        "setup_type": "TEXT",
        "conviction_label": "TEXT",
        "quantity": "INTEGER",
        "volatility_flag": "TEXT",
        "next_session_bias": "TEXT",
        "next_session_confidence": "INTEGER",
    }
    for name, col_type in columns.items():
        if name not in existing:
            con.execute(f"ALTER TABLE signals ADD COLUMN {name} {col_type}")


def cache_key(symbol: str, interval: str, period: str) -> str:
    raw = f"{symbol}_{interval}_{period}"
    return hashlib.md5(raw.encode()).hexdigest()


def get_ohlcv_cache(symbol: str, interval: str, period: str, max_age_minutes: int = 30):
    key = cache_key(symbol, interval, period)
    with _conn() as con:
        row = con.execute(
            "SELECT data, fetched_at FROM ohlcv_cache WHERE key = ?", (key,)
        ).fetchone()
    if not row:
        return None
    fetched_at = datetime.fromisoformat(row["fetched_at"])
    if datetime.now() - fetched_at > timedelta(minutes=max_age_minutes):
        return None
    return json.loads(row["data"])


def set_ohlcv_cache(symbol: str, interval: str, period: str, data: dict):
    key = cache_key(symbol, interval, period)
    with _conn() as con:
        con.execute(
            "INSERT OR REPLACE INTO ohlcv_cache (key, data, fetched_at) VALUES (?, ?, ?)",
            (key, json.dumps(data), datetime.now().isoformat()),
        )


def get_fundamentals_cache(symbol: str, max_age_hours: int = 24):
    with _conn() as con:
        row = con.execute(
            "SELECT data, fetched_at FROM fundamentals_cache WHERE symbol = ?", (symbol,)
        ).fetchone()
    if not row:
        return None
    fetched_at = datetime.fromisoformat(row["fetched_at"])
    if datetime.now() - fetched_at > timedelta(hours=max_age_hours):
        return None
    return json.loads(row["data"])


def set_fundamentals_cache(symbol: str, data: dict):
    with _conn() as con:
        con.execute(
            "INSERT OR REPLACE INTO fundamentals_cache (symbol, data, fetched_at) VALUES (?, ?, ?)",
            (symbol, json.dumps(data), datetime.now().isoformat()),
        )


def save_signal(signal: dict):
    with _conn() as con:
        con.execute(
            """INSERT INTO signals
               (symbol, signal, trade_type, confidence, entry_price, target_price,
                target_2_price, stop_loss, risk_reward_ratio, reasoning, pattern_detected,
                risk_factors, best_entry_time, setup_type, conviction_label, quantity,
                volatility_flag, next_session_bias, next_session_confidence,
                support, resistance, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                signal.get("symbol"),
                signal.get("signal"),
                signal.get("trade_type"),
                signal.get("confidence", 0),
                signal.get("entry_price"),
                signal.get("target_price"),
                signal.get("target_2_price"),
                signal.get("stop_loss"),
                signal.get("risk_reward_ratio"),
                signal.get("reasoning"),
                signal.get("pattern_detected"),
                signal.get("risk_factors"),
                signal.get("best_entry_time"),
                signal.get("setup_type"),
                signal.get("conviction_label"),
                signal.get("quantity"),
                signal.get("volatility_flag"),
                signal.get("next_session_bias"),
                signal.get("next_session_confidence"),
                signal.get("key_levels", {}).get("support"),
                signal.get("key_levels", {}).get("resistance"),
                datetime.now().isoformat(),
            ),
        )


def save_intelligence_report(report_type: str, markdown: str, data: dict = None):
    with _conn() as con:
        con.execute(
            """INSERT INTO intelligence_reports (report_type, markdown, data, created_at)
               VALUES (?, ?, ?, ?)""",
            (
                report_type,
                markdown,
                json.dumps(data or {}),
                datetime.now().isoformat(),
            ),
        )


def get_latest_intelligence_report(report_type: str = None):
    query = "SELECT * FROM intelligence_reports"
    params = []
    if report_type:
        query += " WHERE report_type = ?"
        params.append(report_type)
    query += " ORDER BY created_at DESC LIMIT 1"
    with _conn() as con:
        row = con.execute(query, params).fetchone()
    return dict(row) if row else None


def get_today_signals():
    today = datetime.now().date().isoformat()
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM signals WHERE created_at LIKE ? ORDER BY confidence DESC",
            (f"{today}%",),
        ).fetchall()
    return [dict(r) for r in rows]


def get_signal_history(symbol: str, days: int = 30):
    since = (datetime.now() - timedelta(days=days)).isoformat()
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM signals WHERE symbol = ? AND created_at >= ? ORDER BY created_at DESC",
            (symbol, since),
        ).fetchall()
    return [dict(r) for r in rows]
