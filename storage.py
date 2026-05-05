"""
storage.py — Reusable GCS helpers for AlphaSystem.
Bot (main.py) uses gcsfs.
Dashboard (Streamlit) uses st_files_connection directly.
"""
import json
import os

GCS_BUCKET = os.getenv("GCS_BUCKET", "your-bucket-name")
GCS_PREFIX = os.getenv("GCS_PREFIX", "alphasystem")


# ── Bot helpers (gcsfs) ──────────────────────────────

def get_gcs_fs():
    import gcsfs
    return gcsfs.GCSFileSystem(token="cloud")


def save_json(name: str, obj, fs=None, prefix: str = GCS_PREFIX):
    if fs is None:
        fs = get_gcs_fs()
    full_path = f"{GCS_BUCKET}/{prefix}/{name}"
    with fs.open(full_path, "w") as f:
        json.dump(obj, f, indent=2, default=str)


def load_json(name: str, fs=None, prefix: str = GCS_PREFIX):
    if fs is None:
        fs = get_gcs_fs()
    full_path = f"{GCS_BUCKET}/{prefix}/{name}"
    try:
        with fs.open(full_path, "r") as f:
            return json.load(f)
    except:
        return {}


def save_csv(name: str, df, fs=None, prefix: str = GCS_PREFIX):
    import io
    if fs is None:
        fs = get_gcs_fs()
    output = io.StringIO()
    df.to_csv(output, index=False)
    full_path = f"{GCS_BUCKET}/{prefix}/{name}"
    with fs.open(full_path, "w") as f:
        f.write(output.getvalue())


def load_csv(name: str, fs=None, prefix: str = GCS_PREFIX):
    import pandas as pd
    if fs is None:
        fs = get_gcs_fs()
    full_path = f"{GCS_BUCKET}/{prefix}/{name}"
    try:
        with fs.open(full_path, "r") as f:
            return pd.read_csv(f)
    except:
        return pd.DataFrame()
