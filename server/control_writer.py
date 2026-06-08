from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path

CONTROL_PATH = Path("state/control.json")
AUDIT_PATH   = Path("state/control_log.jsonl")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_command(command: str, issued_by: str, config: dict | None = None) -> dict:
    CONTROL_PATH.parent.mkdir(parents=True, exist_ok=True)
    AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)

    entry = {
        "command":   command,
        "issued_by": issued_by,
        "issued_at": _now(),
    }
    if config is not None:
        entry["config"] = config

    CONTROL_PATH.write_text(json.dumps(entry, ensure_ascii=False), encoding="utf-8")

    audit_entry = {"action": command, "issued_by": issued_by, "ts": entry["issued_at"]}
    if config is not None:
        audit_entry["config"] = config
    with AUDIT_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(audit_entry, ensure_ascii=False) + "\n")

    return entry


def read_audit(limit: int = 100) -> list[dict]:
    if not AUDIT_PATH.exists():
        return []
    try:
        lines = AUDIT_PATH.read_text(encoding="utf-8").strip().splitlines()
        tail = lines[-limit:] if len(lines) > limit else lines
        return [json.loads(line) for line in tail if line.strip()]
    except Exception:
        return []


def read_pending() -> dict | None:
    """Read and clear the pending control command (called by the bot each cycle)."""
    if not CONTROL_PATH.exists():
        return None
    try:
        data = json.loads(CONTROL_PATH.read_text(encoding="utf-8"))
        if data.get("command"):
            CONTROL_PATH.write_text(
                json.dumps({**data, "command": None}, ensure_ascii=False),
                encoding="utf-8",
            )
            return data
    except Exception:
        pass
    return None
