"""dashboard/state.py — Bot state, health KPIs and alert feed."""
import requests
import pandas as pd
from datetime import datetime, timezone


def get_health():
    """Return dict with bot health from /health endpoint."""
    try:
        r = requests.get("http://localhost:8080/health", timeout=2)
        if r.status_code == 200:
            return r.json()
    except:
        pass
    return {"ok": False, "running": False, "last_loop_age_sec": 999, "drawdown": 0}


def get_alerts(limit=10):
    """Return recent alerts (placeholder — reads from log or state)."""
    # In production, read from a log file or Redis/DB
    return [
        {"ts": "2026-05-06 17:18", "level": "info", "msg": "Bot started"},
        {"ts": "2026-05-06 17:19", "level": "success", "msg": "Trade #5 closed: +$9.55"},
    ][:limit]


def format_kpi_delta(value, prefix="", suffix=""):
    """Helper for Streamlit metric deltas."""
    if value > 0:
        return f"+{prefix}{value:.2f}{suffix}"
    elif value < 0:
        return f"-{prefix}{abs(value):.2f}{suffix}"
    return None
