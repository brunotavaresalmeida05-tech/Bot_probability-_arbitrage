from __future__ import annotations
from datetime import datetime, timezone
from typing import Any


JSON = dict[str, Any]


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_snapshot(
    ts: str = "",
    mode: str = "paper",
    status: str = "starting",
    account: dict | None = None,
    positions: list | None = None,
    market: dict | None = None,
    strategies: list | None = None,
    risk: dict | None = None,
    health: dict | None = None,
    portfolio: dict | None = None,
    alerts: list | None = None,
) -> dict:
    return {
        "ts": ts or utcnow(),
        "mode": mode,
        "status": status,
        "session_id": datetime.now().strftime("%Y%m%d_%H%M%S"),
        "build": "round_2",
        "account": account or {
            "balance": 0.0, "equity": 0.0, "margin": 0.0,
            "free_margin": 0.0, "margin_level": 0.0, "open_pnl": 0.0,
            "daily_pnl": 0.0, "daily_return_pct": 0.0, "currency": "USD",
            "drawdown_pct": 0.0, "max_drawdown_pct": 0.0,
            "win_rate": 0.0, "profit_factor": 0.0,
            "trades_today": 0, "trades_total": 0,
        },
        "market": market or {
            "symbols": {},
            "indices": [],
            "commodities": [],
            "fx_strength": [],
            "correlations": [],
        },
        "positions": positions or [],
        "strategies": strategies or [],
        "portfolio": portfolio or {
            "exposure_pct": 0.0,
            "net_exposure_pct": 0.0,
            "gross_exposure_pct": 0.0,
            "concentration_pct": 0.0,
            "correlation_risk": 0.0,
            "open_positions": 0,
            "symbols_exposed": 0
        },
        "risk": risk or {
            "kill_switch": False,
            "daily_loss_limit_hit": False,
            "weekly_loss_limit_hit": False,
            "max_positions": 5,
            "max_risk_per_trade_pct": 0.5,
            "current_risk_pct": 0.0,
            "spread_filter_blocked": False,
            "news_filter_blocked": False,
            "session_blocked": False
        },
        "health": health or {
            "ok": True,
            "mt5_connected": False,
            "backend_alive": True,
            "ws_clients": 0,
            "latency_ms": 0,
            "last_cycle_ms": 0,
            "cycles_ok": 0,
            "cycles_fail": 0,
            "message": "running"
        },
        "alerts": alerts or []
    }
