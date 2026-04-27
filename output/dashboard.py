"""
output/dashboard.py - Streamlit dashboard for viewing stock signals.
Run with: streamlit run output/dashboard.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from compat import disable_blocked_pyarrow

disable_blocked_pyarrow()

import streamlit as st
import pandas as pd
from datetime import datetime

from data.cache import init_db, get_today_signals, get_signal_history, get_latest_intelligence_report
from config import load_watchlist

try:
    import pyarrow  # noqa: F401
    HAS_PYARROW = not getattr(pyarrow, "__codex_stub__", False) and hasattr(pyarrow, "Table")
except Exception:
    HAS_PYARROW = False

st.set_page_config(
    page_title="Stock Signal Analyzer",
    page_icon="📈",
    layout="wide",
)

# ── Styling ────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
.metric-card {
    background: #f8f9fa;
    border-radius: 10px;
    padding: 16px;
    text-align: center;
    border: 1px solid #e0e0e0;
}
.buy-signal { background: #e8f5e9; border-left: 4px solid #4caf50; padding: 10px; border-radius: 6px; margin: 4px 0; }
.sell-signal { background: #ffebee; border-left: 4px solid #f44336; padding: 10px; border-radius: 6px; margin: 4px 0; }
.avoid-signal { background: #f5f5f5; border-left: 4px solid #9e9e9e; padding: 10px; border-radius: 6px; margin: 4px 0; }
.signal-header { font-size: 20px; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# ── Init ───────────────────────────────────────────────────────────────────────
init_db()


def render_dataframe(df: pd.DataFrame):
    """Render a dataframe without hard-failing when pyarrow is blocked."""
    if HAS_PYARROW:
        st.dataframe(df, width="stretch")
        return

    st.caption("Interactive table disabled because pyarrow is blocked on this machine.")
    st.markdown(df.to_html(index=False), unsafe_allow_html=True)


def confidence_bar(score: int) -> str:
    filled = "█" * score
    empty = "░" * (10 - score)
    return f"{filled}{empty}"


def signal_color(sig: str) -> str:
    return {"BUY": "🟢", "SELL": "🔴", "AVOID": "⚪"}.get(sig, "⚪")


# ── Sidebar ────────────────────────────────────────────────────────────────────
st.sidebar.title("📈 Stock Analyzer")
st.sidebar.caption(f"Last refreshed: {datetime.now().strftime('%H:%M:%S')}")

if st.sidebar.button("🔄 Refresh Signals", width="stretch"):
    st.rerun()

# Run scan button
st.sidebar.markdown("---")
st.sidebar.subheader("Run a Scan")
st.sidebar.caption("This will fetch data and call Gemini for your watchlist.")
if st.sidebar.button("▶ Run Full Scan Now", width="stretch", type="primary"):
    with st.spinner("Running scan... this may take a few minutes"):
        import subprocess
        result = subprocess.run(
            [sys.executable, os.path.join(os.path.dirname(os.path.dirname(__file__)), "main.py"), "--scan-now"],
            capture_output=True, text=True, timeout=600
        )
        if result.returncode == 0:
            st.sidebar.success("Scan complete!")
            st.rerun()
        else:
            st.sidebar.error(f"Scan failed:\n{result.stderr[-500:]}")

st.sidebar.markdown("---")
min_confidence = st.sidebar.slider("Min confidence filter", 1, 10, 6)
trade_type_filter = st.sidebar.selectbox("Trade type", ["ALL", "INTRADAY", "SWING"])
signal_filter = st.sidebar.multiselect("Signal type", ["BUY", "SELL", "AVOID"], default=["BUY", "SELL"])

# ── Main content ───────────────────────────────────────────────────────────────
st.title("📊 Stock Signal Dashboard")
st.caption(f"NSE Market Analysis | {datetime.now().strftime('%A, %d %B %Y')}")

# Load signals
all_signals = get_today_signals()

# Filter
filtered = [
    s for s in all_signals
    if s.get("confidence", 0) >= min_confidence
    and s.get("signal") in signal_filter
    and (trade_type_filter == "ALL" or s.get("trade_type") == trade_type_filter)
]
filtered = sorted(
    filtered,
    key=lambda s: (s.get("confidence", 0), s.get("risk_reward_ratio") or 0),
    reverse=True,
)[:5]

# ── Summary metrics ────────────────────────────────────────────────────────────
col1, col2, col3, col4, col5 = st.columns(5)
total = len(all_signals)
buys = sum(1 for s in all_signals if s.get("signal") == "BUY")
sells = sum(1 for s in all_signals if s.get("signal") == "SELL")
avoids = sum(1 for s in all_signals if s.get("signal") == "AVOID")
avg_conf = round(sum(s.get("confidence", 0) for s in all_signals) / total, 1) if total else 0

col1.metric("Total Scanned", total)
col2.metric("Buy Signals 🟢", buys)
col3.metric("Sell Signals 🔴", sells)
col4.metric("Avoided ⚪", avoids)
col5.metric("Avg Confidence", f"{avg_conf}/10")

st.markdown("---")

latest_report = get_latest_intelligence_report()
if latest_report:
    with st.expander("Latest Trade Intelligence Report", expanded=False):
        st.markdown(latest_report.get("markdown", ""))

st.markdown("---")

if not filtered:
    st.info("No signals match your filters. Try lowering the confidence threshold or running a new scan.")
else:
    st.subheader(f"Top {len(filtered)} Setups")

    # ── Signal cards ───────────────────────────────────────────────────────────
    for signal in filtered:
        sym = signal.get("symbol", "?")
        sig = signal.get("signal", "AVOID")
        conf = signal.get("confidence", 0)
        trade_type = signal.get("trade_type", "")
        entry = signal.get("entry_price")
        target = signal.get("target_price")
        sl = signal.get("stop_loss")
        rr = signal.get("risk_reward_ratio")
        target2 = signal.get("target_2_price")
        qty = signal.get("quantity")
        setup_type = signal.get("setup_type") or signal.get("pattern_detected", "")
        conviction = signal.get("conviction_label", "")
        next_bias = signal.get("next_session_bias")
        next_conf = signal.get("next_session_confidence")
        volatility = signal.get("volatility_flag")
        pattern = signal.get("pattern_detected", "")
        reason = signal.get("reasoning", "")
        risk = signal.get("risk_factors", "")
        entry_time = signal.get("best_entry_time", "")
        support = signal.get("support")
        resistance = signal.get("resistance")

        css_class = {"BUY": "buy-signal", "SELL": "sell-signal"}.get(sig, "avoid-signal")
        emoji = signal_color(sig)

        with st.container():
            st.markdown(f"""
<div class="{css_class}">
<span class="signal-header">{emoji} {sym}</span> &nbsp;
<span style="font-size:14px; color:#666;">{sig} | {trade_type} | {conviction} | Confidence: {confidence_bar(conf)} {conf}/10</span>
</div>
""", unsafe_allow_html=True)

        col_a, col_b, col_c, col_d, col_e = st.columns(5)
        col_a.metric("Entry Price", f"₹{entry}" if entry else "N/A")
        col_b.metric("Target", f"₹{target}" if target else "N/A")
        col_c.metric("Stop Loss", f"₹{sl}" if sl else "N/A")
        col_d.metric("R:R Ratio", f"{rr}:1" if rr else "N/A")
        col_e.metric("Quantity", qty if qty else "N/A")

        with st.expander(f"Details — {sym}"):
            col_x, col_y = st.columns(2)
            with col_x:
                st.markdown(f"**Setup:** {setup_type}")
                st.markdown(f"**Target 2:** â‚¹{target2 or 'N/A'}")
                st.markdown(f"**Best entry time:** {entry_time}")
                st.markdown(f"**Reasoning:** {reason}")
            with col_y:
                st.markdown(f"**Support:** ₹{support or 'N/A'}")
                st.markdown(f"**Resistance:** ₹{resistance or 'N/A'}")
                st.markdown(f"**Next session:** {next_bias or 'N/A'} ({next_conf if next_conf is not None else 'N/A'}%)")
                st.markdown(f"**Volatility:** {volatility or 'N/A'}")
                st.markdown(f"**Risk factors:** {risk}")

        st.markdown("")

# ── Signal History Table ───────────────────────────────────────────────────────
st.markdown("---")
st.subheader("Signal History (all time)")

wl = load_watchlist()
all_symbols = wl.get("intraday", []) + wl.get("swing", [])

selected_sym = st.selectbox("Select stock", ["ALL"] + sorted(set(all_symbols)))
history = []
if selected_sym == "ALL":
    for s in all_signals:
        history.append(s)
else:
    history = get_signal_history(selected_sym, days=90)

if history:
    df_hist = pd.DataFrame(history)
    cols_to_show = ["created_at", "symbol", "signal", "trade_type", "confidence",
                    "conviction_label", "setup_type", "entry_price", "target_price",
                    "target_2_price", "stop_loss", "risk_reward_ratio", "quantity",
                    "next_session_bias", "next_session_confidence", "pattern_detected"]
    cols_to_show = [c for c in cols_to_show if c in df_hist.columns]
    df_show = df_hist[cols_to_show].rename(columns={
        "created_at": "Time", "symbol": "Symbol", "signal": "Signal",
        "trade_type": "Type", "confidence": "Conf",
        "entry_price": "Entry", "target_price": "Target", "target_2_price": "Target 2",
        "stop_loss": "SL", "risk_reward_ratio": "R:R", "quantity": "Qty",
        "conviction_label": "Conviction", "setup_type": "Setup",
        "next_session_bias": "Next Bias", "next_session_confidence": "Next %",
        "pattern_detected": "Pattern"
    })
    render_dataframe(df_show)
else:
    st.info("No history found. Run a scan first.")

# ── Footer ─────────────────────────────────────────────────────────────────────
st.markdown("---")
st.caption("⚠️ This tool is for educational and informational purposes only. "
           "Always do your own research before trading. Past signals do not guarantee future results.")
