"""
dashboard/app.py — Streamlit Dashboard (minimal).
Reads state.json and events.csv from GCS via storage.py.
"""
import streamlit as st
from storage import get_conn, dash_load_state, dash_load_events

conn = get_conn()

st.set_page_config(page_title="AlphaSystem Dashboard", page_icon="📈")
st.title("AlphaSystem V8 - Trading Dashboard")

st.subheader("Estado Atual")
state = dash_load_state(conn)
st.json(state)

st.subheader("Eventos")
events = dash_load_events(conn)
st.dataframe(events)

st.write("Refresh the page to reload data from GCS.")
