"""
dashboard/app.py - Streamlit Dashboard reading from Google Cloud Storage.
Consumes data saved by main.py via Google Cloud Storage.
Displays: Account, Regime, Signal, Risk, Execution per symbol.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path
import pandas as pd
import streamlit as st
from streamlit_autorefresh import st_autorefresh
from dotenv import load_dotenv
from st_files_connection import FilesConnection

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv()

st.set_page_config(
    page_title="AlphaSystem Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.title("AlphaSystem V8 - Trading Dashboard")

# ── Sidebar config ──────────────────────────────────
sidebar = st.sidebar
sidebar.header("Configuration")

REFRESH_SECONDS = sidebar.slider("Refresh (s)", 1, 30, int(os.getenv("DASHBOARD_REFRESH_SECONDS", "3")))

# ── Auto-refresh ──────────────────────────────────
refresh_count = st_autorefresh(interval=REFRESH_SECONDS * 1000, limit=None, key="datarefresh")
st.write(f"Refreshes: {refresh_count}")

# ── GCS Connection ──────────────────────────────────
conn = st.connection("gcs", type=FilesConnection)
BUCKET = st.secrets.get("GCS_BUCKET", os.getenv("GCS_BUCKET", "your-bucket-name"))
PREFIX = st.secrets.get("GCS_PREFIX", os.getenv("GCS_PREFIX", "alphasystem"))

# ── Helper functions ──────────────────────────────────

@st.cache_data
def load_state():
    """Load bot state from GCS (cached)."""
    try:
        state = conn.read(f"{BUCKET}/{PREFIX}/state.json", input_format="json", ttl=30)
        return state
    except Exception as e:
        st.error(f"Load state failed: {e}")
        return {"equity": 0, "positions": [], "last_signal": "none"}

@st.cache_data
def load_history():
    """Load history from GCS (cached)."""
    try:
        df = conn.read(f"{BUCKET}/{PREFIX}/history.json", input_format="json", ttl=60)
        if "time" in df.columns:
            df["time"] = pd.to_datetime(df["time"])
        return df
    except Exception as e:
        st.error(f"Load history failed: {e}")
        return pd.DataFrame()

@st.cache_data
def load_events():
    """Load events from GCS (cached)."""
    try:
        df = conn.read(f"{BUCKET}/{PREFIX}/events.csv", ttl=60)
        if "time" in df.columns:
            df["time"] = pd.to_datetime(df["time"])
        return df
    except Exception as e:
        st.error(f"Load events failed: {e}")
        return pd.DataFrame()

@st.cache_data
def load_snapshots():
    """Load all snapshot JSON files from GCS."""
    snapshots = {}
    try:
        prefix = f"{BUCKET}/{PREFIX}/snapshots/"
        blobs = conn.list_files(prefix=prefix)
        for blob_name in blobs:
            if blob_name.endswith(".json"):
                symbol = blob_name.replace(f"{prefix}snapshot_", "").replace(".json", "")
                df = conn.read(blob_name, input_format="json", ttl=60)
                snapshots[symbol] = {"data": df}
    except Exception as e:
        st.error(f"Error loading snapshots: {e}")
    return snapshots

# ── Load data ──────────────────────────────────
state = load_state()
history_df = load_history()
events_df = load_events()
snapshots = load_snapshots()

# ── Render functions ──────────────────────────────────

def render_overview(snapshots):
    """Render overview with KPI cards and account summary."""
    st.subheader("System Overview")

    if not snapshots:
        st.warning("No snapshots found. Run main.py to generate snapshots.")
        return

    # Aggregate account state from first snapshot
    first = next(iter(snapshots.values()))
    data = first.get("data", {})
    account = data.get("account", {})

    # ── KPI Cards ──
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Equity", f"{account.get('equity', 0):.2f} {account.get('currency', 'EUR')}")
    with c2:
        st.metric("Balance", f"{account.get('balance', 0):.2f}")
    with c3:
        total_pos = sum(d.get("open_positions_count", 0) for d in (s.get("data", {}) for s in snapshots.values()))
        st.metric("Open Positions", total_pos)
    with c4:
        last_retcode = "n/a"
        for s in snapshots.values():
            result = s.get("data", {}).get("result", {})
            if "execution" in result:
                last_retcode = result["execution"].get("retcode", "n/a")
                break
        st.metric("Last Retcode", last_retcode)

    # ── Account State ──
    with st.expander("Estado da Conta", expanded=False):
        st.json(account)

    # ── All Symbols Summary ──
    st.subheader("Symbols Summary")
    for symbol, snap in sorted(snapshots.items()):
        data = snap.get("data", {})
        result = data.get("result", {})
        regime = result.get("regime", {})
        signal = result.get("signal", {})
        risk = result.get("risk", {})

        col1, col2, col3, col4, col5 = st.columns([1, 2, 2, 2, 3])
        with col1:
            st.write(f"**{symbol}**")
        with col2:
            regime_type = regime.get("regime", "unknown") if regime else "n/a"
            st.write(f"Regime: `{regime_type}`")
        with col3:
            signal_side = signal.get("side", "none") if signal else "none"
            st.write(f"Signal: `{signal_side}`")
        with col4:
            risk_action = risk.get("action", "n/a") if risk else "n/a"
            st.write(f"Risk: `{risk_action}`")
        with col5:
            status = result.get("status", "n/a")
            st.write(f"Status: `{status}`")

    # ── Equity History Chart ──
    st.subheader("Equity History")
    if not history_df.empty and "equity" in history_df.columns:
        chart_df = history_df.dropna(subset=["equity"])
        if not chart_df.empty:
            chart_df = chart_df.set_index("time")[["equity"]]
            st.line_chart(chart_df)
        else:
            st.info("No valid equity data available for chart.")
    else:
        st.info("No equity history found. Run main.py to generate data/history.json.")

    # ── Recent Events Table ──
    st.subheader("Recent Events")
    if not events_df.empty:
        cols = ["time", "symbol", "equity", "status", "regime", "signal"]
        available = [c for c in cols if c in events_df.columns]
        if available:
            recent = events_df[available].tail(10).iloc[::-1]  # most recent first
            st.dataframe(recent, use_container_width=True)
        else:
            st.info("No event details available.")
    else:
        st.info("No events logged yet. Run main.py to generate data/events.csv.")


def render_symbol_detail(symbol, snapshot_data):
    """Render detailed view for a single symbol with organized panels."""
    data = snapshot_data.get("data", {})
    result = data.get("result", {})

    st.subheader(f"Symbol: {symbol}")

    # ── KPI Cards ──
    regime = result.get("regime", {})
    signal = result.get("signal", {})
    risk = result.get("risk", {})
    execution = result.get("execution", {})
    mgmt = result.get("management", {})

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        regime_type = regime.get("regime", "unknown") if regime else "n/a"
        st.metric("Regime", regime_type)
    with c2:
        signal_side = signal.get("side", "none") if signal else "none"
        st.metric("Signal", signal_side)
    with c3:
        risk_action = risk.get("action", "n/a") if risk else "n/a"
        st.metric("Risk Action", risk_action)
    with c4:
        exec_success = execution.get("success", mgmt.get("success", "n/a")) if execution or mgmt else "n/a"
        st.metric("Execution", "OK" if exec_success is True else exec_success)

    # ── Sections ──
    col1, col2 = st.columns(2)

    with col1:
        with st.expander("Estado da Conta", expanded=False):
            st.json(data.get("account", {}))

        with st.expander("Regime e Sinal", expanded=True):
            if regime:
                st.write(f"**Type:** `{regime.get('regime', 'unknown')}`")
                st.write(f"**Confidence:** `{regime.get('confidence', 0):.2f}`")
                st.json(regime)
            if signal and signal.get("side"):
                st.write(f"**Side:** `{signal.get('side')}`")
                st.write(f"**Confidence:** `{signal.get('confidence', 0):.2f}`")
                st.json(signal)

    with col2:
        with st.expander("Risco e Execução", expanded=True):
            if risk:
                st.write(f"**Action:** `{risk.get('action', 'unknown')}`")
                st.write(f"**Reason:** `{risk.get('reason', '')}`")
                st.json(risk)
            if execution:
                st.json(execution)
            if mgmt:
                st.write("**Position Management:**")
                st.json(mgmt)

    # ── Raw JSON ──
    with st.expander("JSON Bruto (Snapshot Completo)", expanded=False):
        st.json(snapshot_data)


# ── Main render ──────────────────────────────────

tab1, tab2 = st.tabs(["📈 Overview", "🔍 Symbol Detail"])

with tab1:
    render_overview(snapshots)

with tab2:
    if not snapshots:
        st.warning("No snapshots available.")
    else:
        symbol = st.selectbox("Select Symbol", sorted(snapshots.keys()))
        if symbol:
            render_symbol_detail(symbol, snapshots[symbol])
