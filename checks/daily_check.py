"""
checks/daily_check.py — Nightly quick-check (5 checks, ~30s)

Run every night:  python checks/daily_check.py

Prints OK / ALERT per check.
Exit code 0 = all clear, exit 1 = at least one ALERT.
Appends one JSON line to checks/daily_results.jsonl for audit trail.
"""
from __future__ import annotations

import json
import re
import shutil
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT       = Path(__file__).resolve().parent.parent
LOG_DIR    = ROOT / "logs"
STATE_DIR  = ROOT / "state"
BACKUP_DIR = ROOT / "backups"
CHECKS_DIR = ROOT / "checks"

BOT_LOG     = LOG_DIR / "bot.log"
WD_LOG      = LOG_DIR / "watchdog.log"
STATE_FILE  = STATE_DIR / "state.json"
HISTORY     = STATE_DIR / "state_history.jsonl"
RESULTS_LOG = CHECKS_DIR / "daily_results.jsonl"

MAX_HIST_AGE_HOURS = 2.0   # state_history must have been written in last N hours
MAX_BACKUP_DAYS    = 14


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _ts() -> str:
    return _now().isoformat()


def _fmt(ok: bool, name: str, msg: str) -> str:
    tag = "OK   " if ok else "ALERT"
    return f"  [{tag}] {name:<20} {msg}"


# ── Check 1: Health ─────────────────────────────────────────────

def check_health() -> tuple[bool, str]:
    issues = []

    if not HISTORY.exists():
        issues.append("state_history.jsonl missing")
    else:
        age_s = _now().timestamp() - HISTORY.stat().st_mtime
        if age_s > MAX_HIST_AGE_HOURS * 3600:
            issues.append(f"state_history stale ({age_s / 3600:.1f}h ago)")

    if not BOT_LOG.exists():
        issues.append("bot.log missing")

    if WD_LOG.exists():
        try:
            recent = WD_LOG.read_text(encoding="utf-8", errors="ignore").splitlines()[-100:]
            restarts = sum(1 for l in recent if "restart" in l.lower() or "crash-loop" in l.lower())
            if restarts > 3:
                issues.append(f"watchdog: {restarts} crash restarts in recent log")
        except Exception:
            pass

    if issues:
        return False, " | ".join(issues)
    return True, "services UP, state_history current"


# ── Check 2: Liquidity ──────────────────────────────────────────

def check_liquidity() -> tuple[bool, str]:
    """Scan recent cycle events for spread anomaly signals."""
    if not HISTORY.exists():
        return False, "no history file"

    cutoff = _now() - timedelta(hours=6)
    anomalous: list[str] = []

    try:
        lines = HISTORY.read_text(encoding="utf-8", errors="ignore").splitlines()
        for line in reversed(lines[-3000:]):
            try:
                ev = json.loads(line)
            except Exception:
                continue
            ts_str = ev.get("ts", "")
            try:
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                if ts < cutoff:
                    break
            except Exception:
                continue

            for sym, exec_data in (ev.get("executions") or {}).items():
                msg = str(exec_data.get("message", "")).lower()
                if "spread" in msg and any(k in msg for k in ("high", "anomaly", "spike", "abnormal")):
                    if sym not in anomalous:
                        anomalous.append(sym)
    except Exception as e:
        return False, f"read error: {e}"

    if anomalous:
        return False, f"spread anomaly detected: {anomalous}"
    return True, "spreads normal (last 6h)"


# ── Check 3: Alerts ─────────────────────────────────────────────

def check_alerts() -> tuple[bool, str]:
    """Count [KILL] / [ALERT] / CRITICAL lines in bot.log last 24h."""
    if not BOT_LOG.exists():
        return True, "no bot.log (skip)"

    cutoff = _now() - timedelta(hours=24)
    crits: list[str] = []

    try:
        lines = BOT_LOG.read_text(encoding="utf-8", errors="ignore").splitlines()
        for line in lines[-8000:]:
            if not any(k in line for k in ("[KILL]", "[ALERT]", "CRITICAL")):
                continue
            m = re.match(r"(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2})", line)
            if m:
                try:
                    ts = datetime.fromisoformat(m.group(1).replace(" ", "T")).replace(tzinfo=timezone.utc)
                    if ts < cutoff:
                        continue
                except Exception:
                    pass
            crits.append(line.strip()[-140:])
    except Exception as e:
        return False, f"log read error: {e}"

    if crits:
        return False, f"{len(crits)} critical alert(s) in 24h — last: {crits[-1]}"
    return True, "no critical alerts in 24h"


# ── Check 4: Logs ───────────────────────────────────────────────

def check_logs() -> tuple[bool, str]:
    """Count ERROR / WARNING lines in bot.log last 24h."""
    if not BOT_LOG.exists():
        return True, "no bot.log"

    cutoff = _now() - timedelta(hours=24)
    errors = warnings = 0

    try:
        lines = BOT_LOG.read_text(encoding="utf-8", errors="ignore").splitlines()
        for line in lines[-12000:]:
            m = re.match(r"(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2})", line)
            if m:
                try:
                    ts = datetime.fromisoformat(m.group(1).replace(" ", "T")).replace(tzinfo=timezone.utc)
                    if ts < cutoff:
                        continue
                except Exception:
                    pass
            upper = line.upper()
            if "CRITICAL" in upper or " ERROR " in upper:
                errors += 1
            elif "WARNING" in upper:
                warnings += 1
    except Exception as e:
        return False, f"log read error: {e}"

    if errors > 10:
        return False, f"{errors} ERROR/CRITICAL lines in 24h (warnings={warnings})"
    if errors > 0:
        return True, f"{errors} errors in 24h (warnings={warnings}) — monitor"
    return True, f"clean — warnings={warnings}"


# ── Check 5: Backups ────────────────────────────────────────────

def check_backups() -> tuple[bool, str]:
    """Snapshot state.json and rotate old backups."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts_tag = datetime.now().strftime("%Y%m%d_%H%M%S")
    saved: list[str] = []

    if STATE_FILE.exists():
        dest = BACKUP_DIR / f"state_{ts_tag}.json"
        try:
            shutil.copy2(STATE_FILE, dest)
            saved.append("state.json")
        except Exception as e:
            return False, f"state.json backup failed: {e}"

    removed = 0
    cutoff = _now() - timedelta(days=MAX_BACKUP_DAYS)
    for f in BACKUP_DIR.glob("state_*.json"):
        try:
            if datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc) < cutoff:
                f.unlink()
                removed += 1
        except Exception:
            pass

    hist_mb = HISTORY.stat().st_size / 1_048_576 if HISTORY.exists() else 0.0

    parts = [f"saved {saved}" if saved else "state.json not found"]
    if removed:
        parts.append(f"pruned {removed} old backups")
    if hist_mb > 50:
        parts.append(f"WARN state_history {hist_mb:.0f}MB — consider rotation")

    ok = bool(saved)
    return ok, " | ".join(parts)


# ── Runner ──────────────────────────────────────────────────────

def run_daily_check() -> int:
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    print(f"\n{'='*60}")
    print(f"  DAILY CHECK — {now_str}")
    print(f"{'='*60}")

    checks = [
        ("HEALTH",    check_health),
        ("LIQUIDITY", check_liquidity),
        ("ALERTS",    check_alerts),
        ("LOGS",      check_logs),
        ("BACKUPS",   check_backups),
    ]

    results: dict[str, dict] = {}
    all_ok = True

    for name, fn in checks:
        try:
            ok, msg = fn()
        except Exception as exc:
            ok, msg = False, f"check exception: {exc}"
        results[name] = {"ok": ok, "msg": msg}
        if not ok:
            all_ok = False
        print(_fmt(ok, name, msg))

    verdict = "ALL CLEAR" if all_ok else "ACTION REQUIRED"
    print(f"\n  Verdict: {verdict}")
    print(f"{'='*60}\n")

    CHECKS_DIR.mkdir(parents=True, exist_ok=True)
    record = {"ts": _ts(), "verdict": verdict, "checks": results}
    with open(RESULTS_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")

    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(run_daily_check())
