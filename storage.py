"""
storage.py — GCS helpers for AlphaSystem.
Single entry point for state.json (JSON) and events.csv (CSV).
Bot uses gcsfs | Dashboard uses st_files_connection.
"""
import json
import os

GCS_BUCKET = os.getenv("GCS_BUCKET", "your-bucket-name")
GCS_PREFIX = os.getenv("GCS_PREFIX", "alphasystem")

# Schema definitions
STATE_KEYS = {"equity", "balance", "positions", "last_signal", "updated_at"}
EVENTS_COLS = ["ts", "event", "detail", "asset", "side", "price", "quantity"]


# ── BOT HELPERS (gcsfs) ──────────────────────────

def get_fs():
    import gcsfs
    return gcsfs.GCSFileSystem(token="cloud")


def save_state(obj, fs=None):
    """Save state dict as JSON to GCS."""
    if fs is None:
        fs = get_fs()
    path = f"{GCS_BUCKET}/{GCS_PREFIX}/state.json"
    with fs.open(path, "w") as f:
        json.dump(obj, f, indent=2, default=str)


def load_state(fs=None):
    """Load state.json from GCS. Raises ValueError on invalid schema."""
    if fs is None:
        fs = get_fs()
    path = f"{GCS_BUCKET}/{GCS_PREFIX}/state.json"
    try:
        with fs.open(path, "r") as f:
            data = json.load(f)
    except Exception:
        raise ValueError("state.json not found or unreadable")

    if not isinstance(data, dict):
        raise ValueError(f"state.json invalid: expected dict, got {type(data).__name__}")

    missing = STATE_KEYS - set(data.keys())
    if missing:
        raise ValueError(f"state.json invalid: missing keys {sorted(missing)}")

    return data


def save_events(df, fs=None):
    """Save DataFrame as CSV to GCS (events.csv)."""
    if fs is None:
        fs = get_fs()
    import io
    output = io.StringIO()
    df.to_csv(output, index=False)
    path = f"{GCS_BUCKET}/{GCS_PREFIX}/events.csv"
    with fs.open(path, "w") as f:
        f.write(output.getvalue())


def load_events(fs=None):
    """Load events.csv from GCS. Raises ValueError on invalid schema."""
    if fs is None:
        fs = get_fs()
    import pandas as pd
    path = f"{GCS_BUCKET}/{GCS_PREFIX}/events.csv"
    try:
        with fs.open(path, "r") as f:
            df = pd.read_csv(f)
    except Exception:
        raise ValueError("events.csv not found or unreadable")

    missing = [c for c in EVENTS_COLS if c not in df.columns]
    if missing:
        raise ValueError(f"events.csv invalid: missing columns {missing}")

    return df[EVENTS_COLS]


# ── DASHBOARD HELPERS (st_files_connection) ──────────

def get_conn():
    """Return Streamlit FilesConnection (call only inside Streamlit)."""
    from st_files_connection import FilesConnection
    import streamlit as st
    return st.connection("gcs", type=FilesConnection)


def dash_load_state(conn):
    """Load state.json in Streamlit (cached)."""
    path = f"{GCS_BUCKET}/{GCS_PREFIX}/state.json"
    try:
        data = conn.read(path, input_format="json", ttl=30)
    except Exception as e:
        raise ValueError(f"state.json read failed: {e}")

    if not isinstance(data, dict):
        raise ValueError(f"state.json invalid: expected dict, got {type(data).__name__}")

    missing = STATE_KEYS - set(data.keys())
    if missing:
        raise ValueError(f"state.json invalid: missing keys {sorted(missing)}")

    return data


def dash_load_events(conn):
    """Load events.csv in Streamlit (cached)."""
    path = f"{GCS_BUCKET}/{GCS_PREFIX}/events.csv"
    try:
        df = conn.read(path, ttl=30)
    except Exception as e:
        raise ValueError(f"events.csv read failed: {e}")

    missing = [c for c in EVENTS_COLS if c not in df.columns]
    if missing:
        raise ValueError(f"events.csv invalid: missing columns {missing}")

    return df[EVENTS_COLS]
