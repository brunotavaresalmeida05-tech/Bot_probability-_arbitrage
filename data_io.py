from __future__ import annotations

import json
from pathlib import Path
import yaml
import pandas as pd


def load_yaml(path: str, default):
    p = Path(path)
    if not p.exists():
        return default
    with p.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or default


def load_presets(path: str = "presets.yaml") -> dict:
    data = load_yaml(path, {})
    return data if isinstance(data, dict) else {}


def load_history(path: str = "data/historical_rankings.csv") -> pd.DataFrame:
    p = Path(path)
    if not p.exists():
        return pd.DataFrame()
    df = pd.read_csv(path)
    if "ts_run" in df.columns:
        df["ts_run"] = pd.to_datetime(df["ts_run"], errors="coerce")
    return df


def load_runs(path: str = "data/session_runs.csv") -> pd.DataFrame:
    df = pd.read_csv(path)
    for col in ["start_ts", "end_ts"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")
    return df


def load_curves(path: str = "data/session_curves.csv") -> pd.DataFrame:
    df = pd.read_csv(path)
    if "ts" in df.columns:
        df["ts"] = pd.to_datetime(df["ts"], errors="coerce")
    return df


def load_live_kpi(summary: pd.DataFrame) -> dict:
    kpi = {"balance": "—", "equity": "—", "profit": "—", "positions": "—", "health": "—"}
    try:
        with open("data/live_state.json") as f:
            data = json.load(f)
            acc = data.get("account", {})
            kpi["balance"] = f"€{acc.get('balance', 0):,.2f}"
            kpi["equity"] = f"€{acc.get('equity', 0):,.2f}"
            kpi["profit"] = f"{'€'}{acc.get('profit', 0):+,.2f}"
            kpi["positions"] = str(len(data.get("positions", [])))
    except Exception:
        if not summary.empty:
            eq = summary["equity_final"].iloc[0]
            kpi["equity"] = f"€{eq:,.2f}"
            kpi["balance"] = kpi["equity"]
    try:
        with open("data/v8_live_state.json") as f:
            data = json.load(f)
            h = data.get("health", {})
            kpi["health"] = h.get("status", "—")
    except Exception:
        pass
    return kpi
