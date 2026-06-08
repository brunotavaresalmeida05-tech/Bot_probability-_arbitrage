import time
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Tuple, Dict, Any, List

DEFAULT_ALLOWED_AGE_S = 120

def _now_iso():
    return datetime.now(timezone.utc).isoformat()

def _p95(lst: List[float]) -> float:
    if not lst:
        return 0.0
    s = sorted(lst)
    idx = max(0, int(len(s) * 95 / 100) - 1)
    return float(s[idx])

def preflight_check(cfg: Dict[str, Any], state: Dict[str, Any], logger=None) -> Tuple[bool, Dict[str, Any]]:
    report = {
        "timestamp": _now_iso(),
        "ok": True,
        "summary": {},
        "checks": {}
    }

    def mark_ok(key, severity="info", message="", value=None):
        report["checks"][key] = {"ok": True, "severity": severity, "message": message, "value": value}

    def mark_fail(key, severity="fatal", message="", value=None):
        report["checks"][key] = {"ok": False, "severity": severity, "message": message, "value": value}
        report["ok"] = False
        if logger:
            logger.warning(f"[preflight] FAIL {key}: {message} ({value})")

    state_path = Path(cfg.get("paths", {}).get("state_file", "state/state.json"))
    history_path = Path(cfg.get("paths", {}).get("history_file", "state/state_history.jsonl"))
    logs_path = Path(cfg.get("paths", {}).get("logs_dir", "logs"))
    symbols = cfg.get("market", {}).get("symbols", [])
    allowed_age_s = int(cfg.get("checks", {}).get("allowed_bar_age_s", DEFAULT_ALLOWED_AGE_S))

    # 1 — files
    if state_path.exists():
        mark_ok("state_file", "info", "exists", str(state_path))
    else:
        mark_fail("state_file", "fatal", "missing state file", str(state_path))

    if history_path.exists():
        try:
            age_s = (time.time() - history_path.stat().st_mtime)
            mark_ok("history_file", "info", f"mtime {age_s:.0f}s", {"path": str(history_path), "age_s": age_s})
        except Exception as e:
            mark_fail("history_file_stat", "warn", str(e))
    else:
        mark_fail("history_file", "warn", "missing history file", str(history_path))

    if logs_path.exists() and any(logs_path.iterdir()):
        mark_ok("logs", "info", "logs exist", str(logs_path))
    else:
        mark_fail("logs", "warn", "logs missing or empty", str(logs_path))

    # 2 — market data + latency proxy
    fetch_times = []
    market = state.get("market", {})
    bad_symbols = []
    now_ts = datetime.now(timezone.utc).timestamp()
    for s in symbols:
        item = market.get(s)
        if not item or item.get("status") == "no_data":
            bad_symbols.append(s)
            continue
        tval = item.get("time")
        try:
            t_parsed = datetime.fromisoformat(tval).timestamp() if isinstance(tval, str) else float(tval)
            age = abs(now_ts - t_parsed)
            if age > allowed_age_s:
                bad_symbols.append(s)
            fetch_times.append(age * 1000.0)
        except Exception:
            bad_symbols.append(s)

    if bad_symbols:
        mark_fail("market_data", "fatal", f"missing/old market data for {bad_symbols}", {"missing": bad_symbols})
    else:
        p50 = statistics.median(fetch_times) if fetch_times else None
        p95 = _p95(fetch_times) if fetch_times else None
        mark_ok("market_data", "info", "market data recent", {"p50_ms": p50, "p95_ms": p95, "count": len(fetch_times)})

    # 3 — indicators
    indicators = state.get("indicators", {})
    bad_inds = []
    for s in symbols:
        inds = indicators.get(s, {})
        if not inds or any(inds.get(k) is None for k in ("ma20", "rsi14", "zscore20")):
            bad_inds.append(s)
    if bad_inds:
        mark_fail("indicators", "fatal", f"missing/invalid indicators for {bad_inds}", {"bad": bad_inds})
    else:
        mark_ok("indicators", "info", "indicators OK", {"count": len(symbols)})

    # 4 — signals (aceita strings "BUY"/"SELL"/"HOLD" ou dicts com campo "signal")
    signals = state.get("signals", {})
    valid = {"BUY", "SELL", "HOLD"}
    def _sig_val(v):
        if isinstance(v, dict):
            return v.get("signal", "")
        return v
    bad_signals = [s for s, v in signals.items() if _sig_val(v) not in valid]
    if bad_signals:
        mark_fail("signals", "fatal", "invalid signals", {"bad": bad_signals})
    else:
        mark_ok("signals", "info", "signals OK", {"count": len(signals)})

    # 5 — executions
    executions = state.get("executions", {})
    if not executions:
        mark_fail("executions", "warn", "no executions recorded in state", None)
    else:
        allowed_status = {"dry_run", "filled", "blocked", "rejected", "failed", "skipped"}
        bad_exec = [s for s, e in executions.items() if e.get("status") not in allowed_status]
        if bad_exec:
            mark_fail("executions_status", "fatal", "unexpected exec statuses", {"bad": bad_exec})
        else:
            mark_ok("executions", "info", "executions OK", {"count": len(executions)})

    # 6 — health
    health = state.get("health", {})
    if not health.get("ok", False):
        mark_fail("health", "fatal", f"health not OK: {health.get('message')}", health)
    else:
        mark_ok("health", "info", "health OK", health.get("message"))

    # 7 — risk config plausibility
    risk = cfg.get("risk", {})
    r_issues = []
    if float(risk.get("max_spread", 0.0)) <= 0:
        r_issues.append("max_spread <= 0")
    if float(risk.get("max_daily_loss", 0.0)) <= 0:
        r_issues.append("max_daily_loss <= 0 (recommended)")
    if r_issues:
        mark_fail("risk_config", "warn", "risk config issues", {"issues": r_issues})
    else:
        mark_ok("risk_config", "info", "risk config OK", risk)

    # 8 — latency (real fetch timings if adapter available)
    latency_samples = []
    adapter = cfg.get("adapters", {}).get("mt5")
    if adapter and hasattr(adapter, "fetch_bars_timed"):
        for s in symbols:
            try:
                _, dur = adapter.fetch_bars_timed(
                    s,
                    cfg.get("market", {}).get("mt5_timeframe"),
                    int(cfg.get("market", {}).get("market_bars", 100))
                )
                latency_samples.append(dur)
            except Exception as e:
                mark_fail("latency_fetch_error", "warn", f"fetch timed failed for {s}: {e}")
        if latency_samples:
            p50 = float(statistics.median(latency_samples))
            p95 = float(sorted(latency_samples)[min(len(latency_samples)-1, max(0, int(len(latency_samples)*95/100)-1))])
            mark_ok("latency", "info", "latency measured", {"samples": len(latency_samples), "p50_ms": p50, "p95_ms": p95})
    else:
        mark_ok("latency", "info", "no adapter latency test (adapter missing)", None)

    # 9 — broker reconnection test (non-invasive)
    mt5_adapter = cfg.get("adapters", {}).get("mt5")
    if mt5_adapter and hasattr(mt5_adapter, "check_connection"):
        try:
            connected = mt5_adapter.check_connection()
            mark_ok("broker_connection", "info", "initial connection status", {"connected": bool(connected)})
            if not connected and hasattr(mt5_adapter, "reconnect"):
                try:
                    ok = mt5_adapter.reconnect(timeout=5)
                    if ok:
                        mark_ok("broker_reconnect", "info", "reconnected ok", None)
                    else:
                        mark_fail("broker_reconnect", "fatal", "reconnect failed", None)
                except Exception as e:
                    mark_fail("broker_reconnect", "fatal", f"reconnect exception: {e}")
        except Exception as e:
            mark_fail("broker_connection", "fatal", f"connection check failed: {e}")
    else:
        mark_ok("broker_connection", "info", "no broker adapter available", None)

    # summary
    report["summary"] = {
        "symbols": len(symbols),
        "checks_total": len(report["checks"]),
        "ok": report["ok"]
    }

    return report["ok"], report
