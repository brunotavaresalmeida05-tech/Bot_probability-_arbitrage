"""
storage.py — Reusable GCS helpers for AlphaSystem.
Uses gcsfs for bot (main.py) and st_files_connection for dashboard (Streamlit).
Pattern: JSON for small state, CSV for tabular history.
"""

import json
import os
from pathlib import Path

# ── Config ──────────────────────────────────────
GCS_BUCKET = os.getenv("GCS_BUCKET", "your-bucket-name")
GCS_PREFIX = os.getenv("GCS_PREFIX", "alphasystem")


# ── BOT HELPES (gcsfs — for main.py) ──────────

def get_gcs_fs():
    """Return gcsfs filesystem (for bot/script use)."""
    import gcsfs
    return gcsfs.GCSFileSystem(token="cloud")


def save_json(fs, name: str, obj, prefix: str = GCS_PREFIX):
    """Save object as JSON to GCS (dict or list)."""
    full_path = f"{GCS_BUCKET}/{prefix}/{name}"
    with fs.open(full_path, "w") as f:
        json.dump(obj, f, indent=2, default=str)


def load_json(fs, name: str, prefix: str = GCS_PREFIX) -> dict:
    """Load JSON from GCS. Returns {} on error."""
    full_path = f"{GCS_BUCKET}/{prefix}/{name}"
    try:
        with fs.open(full_path, "r") as f:
            return json.load(f)
    except:
        return {}


def save_csv(fs, name: str, df, prefix: str = GCS_PREFIX):
    """Save DataFrame as CSV to GCS."""
    import io
    output = io.StringIO()
    df.to_csv(output, index=False)
    full_path = f"{GCS_BUCKET}/{prefix}/{name}"
    with fs.open(full_path, "w") as f:
        f.write(output.getvalue())


def load_csv(fs, name: str, prefix: str = GCS_PREFIX):
    """Load CSV from GCS. Returns DataFrame."""
    import pandas as pd
    full_path = f"{GCS_BUCKET}/{prefix}/{name}"
    try:
        with fs.open(full_path, "r") as f:
            return pd.read_csv(f)
    except:
        return pd.DataFrame()


# ── DASHBOARD HELPES (st_files_connection — for Streamlit) ──

def get_conn():
    """Return Streamlit FilesConnection (call only inside Streamlit)."""
    from st_files_connection import FilesConnection
    import streamlit as st
    return st.connection("gcs", type=FilesConnection)


def dashboard_load_json(conn, name: str, ttl: int = 30, prefix: str = GCS_PREFIX):
    """Load JSON in Streamlit (cached)."""
    import streamlit as st
    path = f"{GCS_BUCKET}/{prefix}/{name}"
    return conn.read(path, input_format="json", ttl=ttl)


def dashboard_load_csv(conn, name: str, ttl: int = 30, prefix: str = GCS_PREFIX):
    """Load CSV in Streamlit (cached)."""
    import streamlit as st
    path = f"{GCS_BUCKET}/{prefix}/{name}"
    return conn.read(path, ttl=ttl)


def dashboard_save_json(conn, name: str, obj: dict, prefix: str = GCS_PREFIX):
    """Save JSON from Streamlit."""
    import io
    path = f"{GCS_BUCKET}/{prefix}/{name}"
    output = io.StringIO()
    output.write(json.dumps(obj, indent=2, default=str))
    with conn.open(path, "w") as f:
        f.write(output.getvalue())


def dashboard_save_csv(conn, name: str, df, prefix: str = GCS_PREFIX):
    """Save CSV from Streamlit."""
    import io
    path = f"{GCS_BUCKET}/{prefix}/{name}"
    output = io.StringIO()
    df.to_csv(output, index=False)
    with conn.open(path, "w") as f:
        f.write(output.getvalue())
