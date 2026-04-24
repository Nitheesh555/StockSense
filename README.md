# NSE Trading Intelligence System

AI-assisted trading intelligence for NSE-listed Indian stocks. The system scans a TradingView-style watchlist, fetches multi-timeframe market data, computes technical setups, asks OpenAI GPT for structured analysis, and produces a Top 5 trade intelligence report for intraday, swing, and next-session planning.

This tool is for educational and research use only. It is not financial advice.

## What It Does

- Fetches OHLCV data across `5m`, `1h`, and `1d` timeframes with yfinance.
- Computes RSI, MACD, Bollinger Bands, VWAP, EMA 9/21/50/200, ADX, ATR, OBV, volume ratio, and support/resistance.
- Detects candlestick and chart patterns such as Doji, Engulfing, Hammer, Shooting Star, VWAP moves, breakouts, breakdowns, and compression.
- Classifies setups for:
  - Intraday: VWAP reclaim/rejection, Opening Range Breakout, momentum scalps.
  - Swing: EMA/ADX trend continuation, volume breakout, 21 EMA pullback.
  - Next session: bullish/bearish/neutral bias, confidence %, gap probability, and levels to watch.
- Adds best-effort market context for Nifty 50, Bank Nifty, India VIX, sector strength, FII/DII availability, and expiry awareness.
- Applies risk management with configurable account size, 1-2% risk, ATR stops, quantity sizing, R:R filtering, and high-volatility flags.
- Uses the existing OpenAI GPT integration only. There is no Claude/Anthropic API dependency.
- Saves signals and final intelligence reports to SQLite and `output/reports/`.
- Shows Top 5 setups in Streamlit and optionally sends Telegram alerts.

## Quick Start

### 1. Prerequisites

- Python 3.10 or higher
- An OpenAI API key from https://platform.openai.com/api-keys

### 2. Setup

```bash
cd stock_analyzer
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate

pip install -r requirements.txt
```

### 3. Configure Environment

```bash
cp .env.example .env
```

Add your OpenAI key:

```env
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
```

Telegram is optional:

```env
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
TELEGRAM_CHAT_ID=your_telegram_chat_id_here
```

## Watchlist Settings

Edit `watchlist.json`:

```json
{
  "intraday": ["RELIANCE", "TCS", "HDFCBANK"],
  "swing": ["ADANIENT", "TITAN"],
  "settings": {
    "min_confidence": 7,
    "min_volume_ratio": 1.2,
    "account_size": 500000,
    "intraday_risk_per_trade_pct": 1.0,
    "swing_risk_per_trade_pct": 2.0,
    "atr_sl_multiplier": 1.5,
    "rr_ratio_min": 1.5,
    "top_n_setups": 5
  }
}
```

Quantity is calculated as:

```text
Quantity = (account_size * risk_percent / 100) / abs(entry_price - stop_loss)
```

If ATR is greater than 3% of price, the setup is flagged as high volatility and position size is reduced.

## Commands

Run a complete intraday + swing intelligence scan:

```bash
python main.py --scan-now
```

Analyze a single stock:

```bash
python main.py --symbol RELIANCE --type INTRADAY
python main.py --symbol TITAN --type SWING
```

Open the dashboard:

```bash
streamlit run output/dashboard.py
```

Run the scheduler:

```bash
python scheduler.py
```

## Schedule

The scheduler runs in IST:

| Time | Job | Purpose |
|---|---|---|
| 8:45 AM | Pre-market scan | Market context and next-session readiness |
| 9:15 AM | Intraday scan | VWAP, ORB, and momentum setups |
| 12:00 PM | Midday review | Refresh intraday opportunities |
| 3:30 PM | EOD swing scan | Daily-candle swing setups |
| 4:00 PM | Next-session scan | Tomorrow's bias and watch levels |

Override schedule values in `.env` using `PREMARKET_SCAN_HOUR`, `SCAN_HOUR`, `MIDDAY_SCAN_HOUR`, `EOD_SCAN_HOUR`, and `NEXT_SESSION_SCAN_HOUR` plus matching minute keys.

## Output

Each scan stores:

- Individual structured signals in `db/signals.db`.
- Final intelligence reports in the `intelligence_reports` table.
- Timestamped Markdown reports in `output/reports/`.

The final report includes:

- Market Pulse: Nifty trend, VIX, FII/DII availability.
- Top 5 Intraday Setups.
- Top 5 Swing Setups.
- Next Session Outlook with bias, confidence, gap probability, support, and resistance.

## Project Structure

```text
stock_analyzer/
├── main.py                  # Entry point and scan orchestration
├── scheduler.py             # APScheduler jobs
├── config.py                # Settings, paths, schedule, defaults
├── watchlist.json           # Your symbols and risk settings
├── data/
│   ├── fetcher.py           # yfinance/NSE data fetchers
│   ├── fundamentals.py      # Screener.in fundamentals
│   └── cache.py             # SQLite cache, signals, reports
├── analysis/
│   ├── analyzer.py          # Indicators and timeframe alignment
│   ├── patterns.py          # Pattern detection
│   ├── setup_engine.py      # Setup classification and next-session outlook
│   └── signals.py           # Trade levels, risk, position sizing
├── context/
│   └── market_context.py    # Best-effort index/VIX/sector context
├── ai/
│   ├── ai_engine.py         # OpenAI GPT structured output
│   └── prompt_builder.py    # Trading intelligence prompts
└── output/
    ├── dashboard.py         # Streamlit Top 5 dashboard
    ├── alerts.py            # Telegram and console alerts
    ├── report_generator.py  # Final report builder
    └── reports/             # Generated Markdown reports
```

## Troubleshooting

**`OPENAI_API_KEY not set`**  
Copy `.env.example` to `.env` and add your OpenAI API key.

**No data returned for a symbol**  
Use base NSE symbols such as `RELIANCE`, not `RELIANCE.NS`. The app appends `.NS` automatically for equities.

**Market context unavailable**  
The app uses free best-effort sources. If Nifty, Bank Nifty, VIX, FII/DII, or sector data is unavailable, the scan continues and marks the field unavailable.

**Dashboard shows no signals**  
Run `python main.py --scan-now` first, then open `streamlit run output/dashboard.py`.

## Disclaimer

This system assists research and decision-making. Always validate signals independently, manage risk, and trade only with capital you can afford to lose. Past performance of indicators or generated signals does not guarantee future results.
