"""server/bot_manager.py — Manage the bot subprocess lifecycle."""
from __future__ import annotations
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_BOT_ENTRY = _ROOT / "src" / "main.py"

_proc: subprocess.Popen | None = None


def start() -> dict:
    global _proc
    if _proc is not None and _proc.poll() is None:
        return {"started": False, "reason": "already_running", "pid": _proc.pid}
    _proc = subprocess.Popen(
        [sys.executable, str(_BOT_ENTRY)],
        cwd=str(_ROOT),
    )
    return {"started": True, "pid": _proc.pid}


def stop() -> dict:
    global _proc
    if _proc is None or _proc.poll() is not None:
        return {"stopped": False, "reason": "not_running"}
    _proc.terminate()
    try:
        _proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        _proc.kill()
    pid = _proc.pid
    _proc = None
    return {"stopped": True, "pid": pid}


def status() -> dict:
    global _proc
    if _proc is None:
        return {"running": False, "pid": None}
    if _proc.poll() is None:
        return {"running": True, "pid": _proc.pid}
    _proc = None
    return {"running": False, "pid": None}
