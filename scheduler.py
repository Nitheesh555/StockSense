"""
scheduler.py - APScheduler-based scheduler (alternative to built-in loop in main.py).
Use this if you want more control over scheduling.

Run with: python scheduler.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz

from config import (
    PREMARKET_SCAN_HOUR, PREMARKET_SCAN_MINUTE,
    SCAN_HOUR, SCAN_MINUTE,
    MIDDAY_SCAN_HOUR, MIDDAY_SCAN_MINUTE,
    EOD_SCAN_HOUR, EOD_SCAN_MINUTE,
    NEXT_SESSION_SCAN_HOUR, NEXT_SESSION_SCAN_MINUTE,
    logger,
)
from data.cache import init_db
from main import run_combined_scan, run_full_scan, run_next_session_scan, check_api_key

IST = pytz.timezone("Asia/Kolkata")


def morning_scan_job():
    logger.info("APScheduler: triggering intraday setup scan")
    run_full_scan("INTRADAY")


def premarket_scan_job():
    logger.info("APScheduler: triggering pre-market context scan")
    run_next_session_scan()


def midday_scan_job():
    logger.info("APScheduler: triggering midday intraday scan")
    run_full_scan("INTRADAY")


def eod_swing_scan_job():
    logger.info("APScheduler: triggering EOD swing scan")
    run_full_scan("SWING")


def next_session_scan_job():
    logger.info("APScheduler: triggering next-session scan")
    run_combined_scan()


if __name__ == "__main__":
    init_db()
    check_api_key()

    scheduler = BlockingScheduler(timezone=IST)

    scheduler.add_job(
        premarket_scan_job,
        CronTrigger(hour=PREMARKET_SCAN_HOUR, minute=PREMARKET_SCAN_MINUTE, timezone=IST),
        id="premarket_scan",
        name="Pre-market context and next-session scan",
    )

    scheduler.add_job(
        morning_scan_job,
        CronTrigger(hour=SCAN_HOUR, minute=SCAN_MINUTE, timezone=IST),
        id="intraday_scan",
        name="Intraday setup scan",
    )

    scheduler.add_job(
        midday_scan_job,
        CronTrigger(hour=MIDDAY_SCAN_HOUR, minute=MIDDAY_SCAN_MINUTE, timezone=IST),
        id="midday_scan",
        name="Midday intraday scan",
    )

    scheduler.add_job(
        eod_swing_scan_job,
        CronTrigger(hour=EOD_SCAN_HOUR, minute=EOD_SCAN_MINUTE, timezone=IST),
        id="eod_swing_scan",
        name="EOD swing scan",
    )

    scheduler.add_job(
        next_session_scan_job,
        CronTrigger(hour=NEXT_SESSION_SCAN_HOUR, minute=NEXT_SESSION_SCAN_MINUTE, timezone=IST),
        id="next_session_scan",
        name="Next-session prediction scan",
    )

    print(f"""
APScheduler running (IST timezone):
  Pre-market   : {PREMARKET_SCAN_HOUR:02d}:{PREMARKET_SCAN_MINUTE:02d}
  Intraday     : {SCAN_HOUR:02d}:{SCAN_MINUTE:02d}
  Midday       : {MIDDAY_SCAN_HOUR:02d}:{MIDDAY_SCAN_MINUTE:02d}
  EOD swing    : {EOD_SCAN_HOUR:02d}:{EOD_SCAN_MINUTE:02d}
  Next session : {NEXT_SESSION_SCAN_HOUR:02d}:{NEXT_SESSION_SCAN_MINUTE:02d}

Press Ctrl+C to stop.
""")

    try:
        scheduler.start()
    except KeyboardInterrupt:
        logger.info("Scheduler stopped.")
