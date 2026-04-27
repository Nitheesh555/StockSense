# Agent Notes

This repository is an NSE stock signal analyzer. Treat `stock_analyzer/` as the app root.

## What This Project Does

- Pulls NSE price data, fundamentals, and option-chain data.
- Computes technical indicators and chart patterns.
- Sends the result to Gemini for a structured trade signal.
- Stores signals in SQLite and exposes them in a Streamlit dashboard.
- Optionally sends Telegram alerts.

## Main Entry Points

- `main.py` is the primary orchestrator.
- `scheduler.py` runs the time-based scan loop.
- `output/dashboard.py` is the Streamlit UI.
- `output/alerts.py` handles alert formatting and delivery.

## Common Commands

```bash
python main.py --scan-now
python main.py --symbol RELIANCE --type INTRADAY
python main.py --symbol TITAN --type SWING
streamlit run output/dashboard.py
python scheduler.py
```

## Working Guidelines

- Keep changes small and consistent with the existing Python style.
- Prefer updating existing functions and modules over adding new abstractions.
- Do not modify generated runtime files unless the task explicitly requires it:
  - `db/signals.db`
  - `logs/analyzer.log`
  - `__pycache__/`
- Treat `watchlist.json` and `.env` as local configuration, not source code.

## Useful Files

- `config.py` centralizes paths, env vars, and trading parameters.
- `data/fetcher.py` and `data/fundamentals.py` handle external data access.
- `analysis/` contains technical analysis and signal logic.
- `ai/` contains prompt construction and Gemini integration.

## Verification

- If you change analysis logic, run a single-symbol analysis first.
- If you change orchestration or scheduler behavior, confirm `python main.py --scan-now` still works.
- If you change the dashboard, launch Streamlit and verify it opens cleanly.
