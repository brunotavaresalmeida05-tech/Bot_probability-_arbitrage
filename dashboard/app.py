"""
dashboard/app.py — Streamlit Dashboard (minimal).
Reads state.json from GCS via storage.py.
"""
from __future__ import annotations

import os, sys
from pathlib import Path
import streamlit as st
from dotenv import load_dotenv

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))
load_dotenv()

st.set_page_config(page_title="AlphaSystem Dashboard", page_icon="📈", layout="wide")
st.title("AlphaSystem V8 - Trading Dashboard")

# GCS connection
from storage import get_conn, dash_load_state
conn = get_conn()

# Load state (cached)
@st.cache_data
def load_state():
    try:
        return dash_load_state(conn)
    except Exception as e:
        st.error(f"Load state failed: {e}")
        return {"equity": 0, "balance": 0, "positions": [], "last_signal": "none", "updated_at": ""}

state = load_state()

# Display
st.subheader("Estado Atual")
c1, c2, c3, c4 = st.columns(4)
with c1:
    st.metric("Equity", f"{state.get('equity', 0):.2f}")
with c2:
    st.metric("Balance", f"{state.get('balance', 0):.2f}")
with c3:
    st.metric("Last Signal", state.get("last_signal", "none"))
with c4:
    st.metric("Updated At", state.get("updated_at", "")[:19])

st.subheader("JSON Completo")
st.json(state)

st.write("Refresh the page to reload state from GCS.")
