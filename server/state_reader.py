from __future__ import annotations
import json
from pathlib import Path

STATE_PATH = Path("state/state.json")
HISTORY_PATH = Path("state/state_history.jsonl")


def _normalize(raw: dict) -> dict:
    """
    Translate either engine format into the unified dashboard format.

    New engine (trading_engine.py) writes:
      market.symbols.{SYM}, strategies[], account.open_pnl, health.mt5_connected

    Old engine (engine.py) / dashboard format:
      market.{SYM}, signals.{SYM}, indicators.{SYM}, executions.{SYM}

    Output is always the dashboard format.
    """
    if not raw:
        return {}

    # Detect format: new engine has "strategies" list, old has "signals" dict
    is_new = "strategies" in raw and isinstance(raw.get("strategies"), list)

    if not is_new:
        # Already in dashboard format — inject session if missing
        if "session" not in raw:
            try:
                from src.session_scheduler import SessionScheduler
                raw = dict(raw)
                raw["session"] = SessionScheduler().session_info()
            except Exception:
                pass
        return raw

    # ── New engine → dashboard format ──────────────────────────────────────

    # 1. Flatten market: {symbols: {SYM: bar}} → {SYM: bar}
    market_raw = raw.get("market", {})
    if isinstance(market_raw, dict) and "symbols" in market_raw:
        market = market_raw.get("symbols", {})
    else:
        market = market_raw

    # 2. signals, executions from strategies array
    strategies = raw.get("strategies", [])
    signals: dict = {}
    executions: dict = {}
    for s in strategies:
        sym = s.get("symbol", "")
        if not sym:
            continue
        sig = s.get("signal", "HOLD")
        signals[sym] = sig
        bar = market.get(sym, {})
        kill = raw.get("risk", {}).get("kill_switch", False)
        status = "blocked" if kill else ("dry_run" if raw.get("mode") != "live" else "pending")
        executions[sym] = {
            "side": sig,
            "quantity": 0.0,
            "status": status,
            "price": bar.get("close"),
            "ts": raw.get("ts", ""),
            "message": "blocked by kill_switch" if kill else f"score={s.get('score', 0.0):.2f}",
        }

    # 3. Summary counts
    buy  = sum(1 for v in signals.values() if v == "BUY")
    sell = sum(1 for v in signals.values() if v == "SELL")
    hold = sum(1 for v in signals.values() if v == "HOLD")

    # 4. Account
    acc = raw.get("account", {})
    account = {
        "balance":      round(float(acc.get("balance", 0)), 2),
        "equity":       round(float(acc.get("equity", 0)), 2),
        "margin":       round(float(acc.get("margin", 0)), 2),
        "free_margin":  round(float(acc.get("free_margin", 0)), 2),
        "margin_level": round(float(acc.get("margin_level", 0)), 2),
        "profit":       round(float(acc.get("open_pnl", 0)), 2),
        "daily_pnl":    round(float(acc.get("daily_pnl", 0)), 2),
        "currency":     str(acc.get("currency", "EUR")),
        "leverage":     int(acc.get("leverage", 1)),
    }

    # 5. Health
    h = raw.get("health", {})
    health = {"ok": bool(h.get("ok", True)), "message": str(h.get("message", "ok"))}

    # 6. Positions
    positions = [
        {
            "ticket": int(p.get("ticket", 0)),
            "symbol": str(p.get("symbol", "")),
            "type":   str(p.get("type", "BUY")),
            "volume": float(p.get("volume", 0)),
            "profit": round(float(p.get("profit", 0)), 2),
        }
        for p in raw.get("positions", [])
    ]

    # 7. Session info (live from scheduler)
    session: dict = {}
    try:
        from src.session_scheduler import SessionScheduler
        session = SessionScheduler().session_info()
    except Exception:
        pass

    return {
        "ts":       raw.get("ts", ""),
        "mode":     raw.get("mode", "paper"),
        "status":   raw.get("status", "running"),
        "paper":    raw.get("mode", "") != "live",
        "health":   health,
        "market":   market,
        "indicators": raw.get("indicators", {}),
        "signals":  signals,
        "executions": executions,
        "summary": {
            "counts": {"BUY": buy, "SELL": sell, "HOLD": hold},
            "strongest": {"symbol": None, "score": None},
            "weakest":   {"symbol": None, "score": None},
        },
        "session":   session,
        "account":   account,
        "positions": positions,
    }


def read_state() -> dict:
    if not STATE_PATH.exists():
        return {}
    try:
        raw = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        return _normalize(raw)
    except Exception:
        return {}


def read_equity_history(limit: int = 200) -> list[dict]:
    if not HISTORY_PATH.exists():
        return []
    try:
        lines = HISTORY_PATH.read_text(encoding="utf-8").strip().splitlines()
        result = []
        for line in lines:
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
                eq = entry.get("equity")
                if eq is None:
                    continue
                result.append({
                    "ts":      entry.get("ts", ""),
                    "equity":  float(eq),
                    "balance": float(entry.get("balance", eq)),
                })
            except Exception:
                continue
        return result[-limit:] if len(result) > limit else result
    except Exception:
        return []


def read_history(limit: int = 100) -> list[dict]:
    if not HISTORY_PATH.exists():
        return []
    try:
        lines = HISTORY_PATH.read_text(encoding="utf-8").strip().splitlines()
        tail = lines[-limit:] if len(lines) > limit else lines
        return [json.loads(line) for line in tail if line.strip()]
    except Exception:
        return []
