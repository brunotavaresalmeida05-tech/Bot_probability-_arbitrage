from __future__ import annotations
import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from server.auth import verify_token

router = APIRouter(tags=["v9"])

_STATE   = Path("state/state.json")
_HISTORY = Path("state/state_history.jsonl")


def _read_state() -> dict:
    if not _STATE.exists():
        return {}
    try:
        return json.loads(_STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _read_history(limit: int = 50) -> list[dict]:
    if not _HISTORY.exists():
        return []
    try:
        lines = [l for l in _HISTORY.read_text(encoding="utf-8").splitlines() if l.strip()]
        return [json.loads(l) for l in lines[-limit:]]
    except Exception:
        return []


@router.get("/v9/state")
def v9_state(_: str = Depends(verify_token)) -> dict:
    """Estado completo V9: macro, scenario, signals, risk, benchmark."""
    return _read_state()


@router.get("/v9/regime")
def v9_regime(_: str = Depends(verify_token)) -> dict:
    """Resumo do regime macro actual."""
    s = _read_state()
    return {
        "ts":           s.get("ts", ""),
        "cycle":        s.get("cycle_count", 0),
        "session":      s.get("session", ""),
        "tradeable":    s.get("tradeable", False),
        "scenario":     s.get("scenario", "indefinido"),
        "macro":        s.get("macro", {}),
        "benchmark":    s.get("benchmark", {}),
        "dry_run":      s.get("dry_run", True),
    }


@router.get("/v9/signals")
def v9_signals(_: str = Depends(verify_token)) -> dict:
    """Sinais activos + risco."""
    s = _read_state()
    return {
        "ts":      s.get("ts", ""),
        "cycle":   s.get("cycle_count", 0),
        "signals": s.get("signals", []),
        "risk":    s.get("risk", {}),
    }


@router.get("/v9/history")
def v9_history(limit: int = 50, _: str = Depends(verify_token)) -> list[dict]:
    """Ultimos N ciclos do state_history.jsonl."""
    return _read_history(limit)


@router.get("/v9/scanner")
def v9_scanner(_: str = Depends(verify_token)) -> dict:
    """Métricas do scanner: por classe, por TF, conversão, alertas."""
    s = _read_state()
    return s.get("scanner_metrics", {})


@router.get("/v9/watchlist")
def v9_watchlist(_: str = Depends(verify_token)) -> list:
    """Watchlist actual ordenada por OpportunityScore."""
    s = _read_state()
    return s.get("watchlist", [])
