"""
storage.py — Minimal GCS helper for AlphaSystem.
Single purpose: read/write state.json to GCS.
"""
import json
import os

GCS_BUCKET = os.getenv("GCS_BUCKET", "your-bucket-name")
GCS_PREFIX = os.getenv("GCS_PREFIX", "alphasystem")


# ── BOT (gcsfs) ──────────────────────────────────

def get_fs():
    import gcsfs
    return gcsfs.GCSFileSystem(token="cloud")


def save_state(obj: dict, fs=None):
    """Save state dict as JSON to GCS."""
    if fs is None:
        fs = get_fs()
    path = f"{GCS_BUCKET}/{GCS_PREFIX}/state.json"
    with fs.open(path, "w") as f:
        json.dump(obj, f, indent=2, default=str)


def load_state(fs=None) -> dict:
    """Load state.json from GCS. Returns minimal schema on error."""
    if fs is None:
        fs = get_fs()
    path = f"{GCS_BUCKET}/{GCS_PREFIX}/state.json"
    try:
        with fs.open(path, "r") as f:
            return json.load(f)
    except:
        return {"equity": 0, "positions": [], "last_signal": "none", "updated_at": ""}


# ── DASHBOARD (st_files_connection) ────────────────

def get_conn():
    """Return Streamlit FilesConnection (call only inside Streamlit)."""
    from st_files_connection import FilesConnection
    import streamlit as st
    return st.connection("gcs", type=FilesConnection)


def dash_load_state(conn):
    """Load state.json in Streamlit (cached)."""
    path = f"{GCS_BUCKET}/{GCS_PREFIX}/state.json"
    return conn.read(path, input_format="json", ttl=30)
