"""
AlphaSystem V9 — launcher completo.

Inicia em paralelo:
  1. FastAPI server  (port 8000)  — dashboard + WebSocket
  2. Trading bot     (src.main)   — MT5 abre automaticamente via MT5_PATH

Uso:
  python start.py

Parar:
  Ctrl+C  (termina os dois processos)
"""
from __future__ import annotations
import os
import signal
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PY   = sys.executable


def _start(args: list[str], name: str) -> subprocess.Popen:
    proc = subprocess.Popen(
        args,
        cwd=str(ROOT),
        stdout=None,   # herda o terminal — logs visíveis
        stderr=None,
    )
    print(f"[start] {name} PID={proc.pid}")
    return proc


def _wait_server(port: int = 8000, timeout: int = 20) -> bool:
    """Aguarda o servidor responder no porto indicado."""
    import socket
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return True
        except OSError:
            time.sleep(0.5)
    return False


def main() -> None:
    procs: list[subprocess.Popen] = []

    def _shutdown(*_):
        print("\n[start] A parar processos...")
        for p in procs:
            try:
                p.terminate()
            except Exception:
                pass
        for p in procs:
            try:
                p.wait(timeout=5)
            except Exception:
                pass
        print("[start] Encerrado.")
        sys.exit(0)

    signal.signal(signal.SIGINT,  _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    # 1 — FastAPI server
    server = _start([PY, "run_server.py", "--port", "8000"], "server")
    procs.append(server)

    # 2 — Trading bot (abre MT5 automaticamente via MT5_PATH no .env)
    bot = _start([PY, "-m", "src.main"], "bot")
    procs.append(bot)

    # Abre o browser assim que o servidor responder
    if _wait_server(8000):
        print("[start] Dashboard disponivel em http://localhost:8000")
        webbrowser.open("http://localhost:8000")
    else:
        print("[start] AVISO: server nao respondeu em 20s — verifica logs")

    # Mantém o launcher vivo; se um dos processos morrer, termina tudo
    try:
        while True:
            for p in procs:
                if p.poll() is not None:
                    print(f"[start] processo PID={p.pid} terminou inesperadamente — a parar tudo")
                    _shutdown()
            time.sleep(2)
    except KeyboardInterrupt:
        _shutdown()


if __name__ == "__main__":
    main()
