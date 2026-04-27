# 🏦 Professional Indian Stock Market Trading Intelligence System

---

## 📌 Overview

An AI-powered trading intelligence system for NSE/BSE listed equities, designed for active traders focused on **intraday** and **swing trading**. The system analyzes a TradingView watchlist and generates actionable, data-driven trade recommendations with precise entry/exit levels, risk management, and next-session predictions.

---

## 🤖 System Prompt (for AI Model)

```
You are an expert Indian stock market analyst and algorithmic trading assistant 
specializing in NSE/BSE listed equities. You have deep expertise in:

- Technical Analysis (Price Action, Candlestick Patterns, Chart Patterns)
- Volume Analysis & Market Microstructure
- Momentum & Mean-Reversion strategies
- Risk Management & Position Sizing
- Indian market-specific factors (F&O expiry, FII/DII flows, sector rotation)

You analyze stocks from a TradingView watchlist and generate actionable, 
data-driven trade recommendations with precise entry/exit levels.
```

---

## 🔧 Enhanced Feature Set

### 1. Multi-Timeframe Technical Analysis

- Fetch OHLCV data across **3 timeframes**: 5min, 1hr, Daily
- Detect **candlestick patterns**: Doji, Engulfing, Hammer, Shooting Star
- Identify **chart patterns**: Cup & Handle, Head & Shoulders, Flags, Wedges
- Calculate **indicators**:
  - RSI, MACD, Bollinger Bands
  - VWAP, EMA (9 / 21 / 50 / 200)
  - ADX, ATR, OBV

---

### 2. 🔴 Intraday Trade Suggestions

- **VWAP-based entries** — price reclaiming or rejecting VWAP
- **Opening Range Breakout (ORB)** — setups using the first 15-minute candle
- **Momentum scalps** — RSI divergence + volume confirmation

**Output per trade:**
| Field | Description |
|---|---|
| Entry Price | Precise buy/sell level |
| Stop Loss | ATR-based dynamic SL |
| Target 1 | First profit-booking level |
| Target 2 | Extended target |
| Risk:Reward | Minimum 1:1.5 filter |
| Quantity | Based on account size & risk % |

---

### 3. 📈 Swing Trade Suggestions (3–10 Days)

- **Trend identification** — EMA crossovers + ADX strength filter
- **Breakout trades** — above key resistance with volume surge (>1.5x avg volume)
- **Pullback entries** — price near 21 EMA in uptrending stocks

**Output per trade:**
| Field | Description |
|---|---|
| Entry Zone | Price range for entry |
| Stop Loss | Below structure / swing low |
| Target | Multi-day price objective |
| Holding Period | Estimated days to target |
| Trend Strength | ADX value + direction |

---

### 4. 🔮 Next Session Prediction Engine

- **Gap analysis** — predict gap-up / gap-down probability based on closing price vs VWAP
- **Momentum score** (0–100) — combining RSI, MACD histogram, and price vs EMAs
- **Sentiment overlay** — factor in global cues (SGX Nifty, Dow futures, VIX)

**Output:**
- Bullish / Bearish / Neutral bias with **confidence %**
- Key support and resistance levels to watch
- Pre-market checklist for the stock

---

### 5. 🛡️ Risk Management Layer

- **Position size formula:**
  ```
  Quantity = (Account Size × Risk % per Trade) ÷ (Entry Price − Stop Loss)
  ```
- Max **1–2% account risk** per trade
- Flag stocks with **ATR > 3%** as "High Volatility — Reduce Position Size"
- **Portfolio heat check** — avoid suggesting more than 5 correlated trades simultaneously

---

### 6. 🌐 Market Context Engine

| Context Factor | Action |
|---|---|
| Nifty 50 / Bank Nifty trend | Only long in bullish market; short in bearish |
| Sector strength ranking | Prioritize top 3 performing sectors |
| FII / DII flow sentiment | Fetch from NSE data if available |
| F&O expiry awareness | Flag weekly / monthly expiry impact on stocks |

---

### 7. 📊 Watchlist Scoring & Prioritization

Each stock is scored **1–10** based on:
- Trend alignment across timeframes
- Volume confirmation
- Pattern quality and clarity
- Risk:Reward ratio

**Conviction Labels:**

| Label | Score Range | Meaning |
|---|---|---|
| 🟢 High Conviction | 8–10 | Strong setup, act on it |
| 🟡 Moderate | 5–7 | Wait for confirmation |
| 🔴 Low / Skip | 1–4 | Avoid or monitor only |

> Only the **Top 5 highest-conviction setups** are surfaced in the final report.

---

### 8. 📋 Output Report Format

```
📊 TRADE INTELLIGENCE REPORT — [DATE] [TIME IST]
Market Pulse: Nifty [BIAS] | VIX [VALUE] | FII [NET FLOW]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔴 INTRADAY SETUPS (Valid till 3:15 PM IST)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. RELIANCE | BUY | ORB Breakout
   Entry: ₹2,450–2,460 | SL: ₹2,428 | T1: ₹2,495 | T2: ₹2,530
   R:R = 1:2.1 | Qty (₹5L, 1% risk): 22 shares
   Conviction: 🟢 8.5/10 | Volume: 1.8x avg

2. SBIN | SHORT | VWAP Rejection
   Entry: ₹820–822 | SL: ₹831 | T1: ₹805 | T2: ₹795
   R:R = 1:1.7 | Qty (₹5L, 1% risk): 55 shares
   Conviction: 🟡 6.5/10 | Volume: 1.2x avg

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📈 SWING SETUPS (3–7 Days)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. HDFCBANK | BUY | Pullback to 21 EMA
   Entry: ₹1,640–1,650 | SL: ₹1,598 | T1: ₹1,720 | T2: ₹1,780
   R:R = 1:1.9 | Hold: 4–6 days
   Conviction: 🟢 9/10 | Trend: Strong Uptrend (ADX 32)

2. INFY | BUY | Breakout Retest
   Entry: ₹1,785–1,795 | SL: ₹1,755 | T1: ₹1,860 | T2: ₹1,920
   R:R = 1:2.4 | Hold: 5–8 days
   Conviction: 🟢 8/10 | Volume: 2.1x avg on breakout

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔮 NEXT SESSION OUTLOOK
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

TATAMOTORS  → Bullish Bias (78%) — closing above VWAP, RSI uptick
              Watch: ₹920 breakout | Gap-up probability: High

ICICIBANK   → Neutral (51%) — inside day, wait for breakout confirmation
              Watch: ₹1,105 resistance | Gap probability: Low

WIPRO       → Bearish Bias (65%) — MACD crossover down, below 50 EMA
              Watch: ₹460 breakdown | Gap-down probability: Moderate
```

---

## 🛠️ Suggested Tech Stack

| Layer | Tool / Library |
|---|---|
| **Data Source** | `yfinance`, NSE Python library, or TradingView webhook |
| **Indicators** | `pandas-ta` or `TA-Lib` |
| **AI Analysis** | Gemini API |
| **Scheduler** | `APScheduler` — run at 9:00 AM & 3:30 PM IST |
| **Frontend** | Streamlit dashboard or Telegram Bot |
| **Storage** | SQLite or Firebase for trade log & performance tracking |

---

## 📁 Project Structure

```
trading-intelligence/
├── data/
│   ├── watchlist.json          # TradingView watchlist
│   └── trade_log.db            # SQLite trade history
├── engine/
│   ├── fetcher.py              # OHLCV data fetcher
│   ├── indicators.py           # Technical indicator calculations
│   ├── patterns.py             # Candlestick & chart pattern detection
│   ├── scorer.py               # Stock conviction scoring
│   └── risk.py                 # Position sizing & risk management
├── ai/
│   └── analyst.py              # Gemini integration
├── context/
│   ├── market_pulse.py         # Nifty/BankNifty trend filter
│   ├── sector_rotation.py      # Sector strength ranking
│   └── fii_dii.py              # FII/DII flow data
├── output/
│   ├── report_generator.py     # Final report formatting
│   └── notifier.py             # Telegram / email alerts
├── scheduler.py                # APScheduler job runner
└── main.py                     # Entry point
```

---

## ⏱️ Recommended Execution Schedule

| Time (IST) | Job | Description |
|---|---|---|
| 8:45 AM | Pre-market scan | Global cues, gap analysis, SGX Nifty |
| 9:15 AM | Intraday setup generation | ORB and VWAP setups after market open |
| 12:00 PM | Midday review | Update SL/targets, identify new setups |
| 3:30 PM | EOD swing scan | Identify swing setups from daily candles |
| 4:00 PM | Next session prediction | Tomorrow's bias report |

---

## ⚠️ Risk Disclaimer

> This system is designed to **assist** decision-making, not replace it. Always validate signals with your own analysis. Past performance of any indicator or pattern does not guarantee future results. Trade only with capital you can afford to lose. The Indian stock market is subject to regulatory, geopolitical, and macroeconomic risks.

---

*Generated for active NSE/BSE traders | Optimized for intraday & swing strategies*
