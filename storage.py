"""
storage.py — Reusable GCS helpers for AlphaSystem.
Bot (main.py) uses gcsfs | Dashboard (Streamlit) uses st_files_connection.
Pattern: JSON for state, CSV for history/events.
"""
import json
import os

GCS_BUCKET = os.getenv("GCS_BUCKET", "your-bucket-name")
GCS_PREFIX = os.getenv("GCS_PREFIX", "alphasystem")


# ── BOT HELPERS (gcsfs — for main.py) ──────────

def get_fs():
    """Return gcsfs filesystem for bot."""
    import gcsfs
    return gcsfs.GCSFileSystem(token="cloud")


def save_json(name: str, obj, fs=None, prefix: str = GCS_PREFIX):
    """Save dict/list as JSON to GCS (bot)."""
    if fs is None:
        fs = get_fs()
    path = f"{GCS_BUCKET}/{prefix}/{name}"
    with fs.open(path, "w") as f:
        json.dump(obj, f, indent=2, default=str)


def load_json(name: str, fs=None, prefix: str = GCS_PREFIX):
    """Load JSON from GCS (bot). Returns {} on error."""
    if fs is None:
        fs = get_fs()
    path = f"{GCS_BUCKET}/{prefix}/{name}"
    try:
        with fs.open(path, "r") as f:
            return json.load(f)
    except:
        return {}


def save_csv(name: str, df, fs=None, prefix: str = GCS_PREFIX):
    """Save DataFrame as CSV to GCS (bot)."""
    import io
    if fs is None:
        fs = get_fs()
    output = io.StringIO()
    df.to_csv(output, index=False)
    path = f"{GCS_BUCKET}/{prefix}/{name}"
    with fs.open(path, "w") as f:
        f.write(output.getvalue())


def load_csv(name: str, fs=None, prefix: str = GCS_PREFIX):
    """Load CSV from GCS (bot). Returns empty DataFrame on error."""
    import pandas as pd
    if fs is None:
        fs = get_fs()
    path = f"{GCS_BUCKET}/{prefix}/{name}"
    try:
        with fs.open(path, "r") as f:
            return pd.read_csv(f)
    except:
        return pd.DataFrame()


# ── DASHBOARD HELPERS (st_files_connection — for Streamlit) ──

def get_conn():
    """Return Streamlit FilesConnection (call only inside Streamlit)."""
    from st_files_connection import FilesConnection
    import streamlit as st
    return st.connection("gcs", type=FilesConnection)


def dash_load_json(conn, name: str, ttl: int = 30, prefix: str = GCS_PREFIX):
    """Load JSON in Streamlit (cached via @st.cache_data)."""
    path = f"{GCS_BUCKET}/{prefix}/{name}"
    return conn.read(path, input_format="json", ttl=ttl)


def dash_load_csv(conn, name: str, ttl: int = 30, prefix: str = GCS_PREFIX):
    """Load CSV in Streamlit (cached via @st.cache_data)."""
    path = f"{GCS_BUCKET}/{prefix}/{name}"
    return conn.read(path, ttl=ttl)
