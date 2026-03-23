"""
src/dashboard_server.py
Servidor web leve (FastAPI + WebSockets) que alimenta o dashboard em tempo real.
"""

import json
import threading
import time
import webbrowser
from datetime import datetime
from typing import Any
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

try:
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect
    from fastapi.responses import HTMLResponse
    import uvicorn
except ImportError:
    print("ERRO: instala as dependências do dashboard: pip install fastapi uvicorn")
    sys.exit(1)

# ─────────────────────────────────────────────
#  DATA STORE
# ─────────────────────────────────────────────

_lock = threading.Lock()

_store: dict[str, Any] = {
    "account": {},
    "symbols": {},
    "trades": [],
    "equity_curve": [],
    "open_positions": [],  # ← lido directamente do MT5
    "started_at": datetime.now().isoformat(),
    "last_update": None,
}

MAX_EQUITY_POINTS = 500
MAX_TRADES = 50


def update_account(account: dict):
    with _lock:
        _store["account"] = account
        _store["last_update"] = datetime.now().isoformat()
        _store["equity_curve"].append(
            {
                "t": datetime.now().strftime("%H:%M:%S"),
                "v": account.get("equity", 0),
            }
        )
        if len(_store["equity_curve"]) > MAX_EQUITY_POINTS:
            _store["equity_curve"].pop(0)

    # Actualizar posições abertas directamente do MT5
    _refresh_positions()


def _refresh_positions():
    """Lê TODAS as posições abertas do MT5 directamente."""
    try:
        import MetaTrader5 as mt5

        positions = mt5.positions_get()
        if positions is None:
            positions = []

        rows = []
        for p in positions:
            rows.append(
                {
                    "ticket": p.ticket,
                    "symbol": p.symbol,
                    "type": "BUY" if p.type == mt5.ORDER_TYPE_BUY else "SELL",
                    "lots": p.volume,
                    "entry": round(p.price_open, 6),
                    "sl": round(p.sl, 6) if p.sl else 0,
                    "tp": round(p.tp, 6) if p.tp else 0,
                    "profit": round(p.profit, 2),
                    "magic": p.magic,
                    "comment": p.comment,
                    "time": datetime.fromtimestamp(p.time).strftime("%H:%M:%S"),
                }
            )

        with _lock:
            _store["open_positions"] = rows

    except Exception:
        pass


def update_symbol(symbol: str, data: dict):
    with _lock:
        if symbol not in _store["symbols"]:
            _store["symbols"][symbol] = {"zscore_history": []}
        _store["symbols"][symbol].update(data)
        _store["symbols"][symbol]["zscore_history"].append(
            {
                "t": datetime.now().strftime("%H:%M:%S"),
                "v": data.get("z", None),
            }
        )
        if len(_store["symbols"][symbol]["zscore_history"]) > MAX_EQUITY_POINTS:
            _store["symbols"][symbol]["zscore_history"].pop(0)
        _store["last_update"] = datetime.now().isoformat()


def add_trade(trade: dict):
    with _lock:
        _store["trades"].insert(0, trade)
        if len(_store["trades"]) > MAX_TRADES:
            _store["trades"].pop()


def get_snapshot() -> dict:
    _refresh_positions()  # sempre fresco
    with _lock:
        return json.loads(json.dumps(_store))


# ─────────────────────────────────────────────
#  FASTAPI APP
# ─────────────────────────────────────────────

app = FastAPI(title="MT5 Bot Dashboard")
_clients: list[WebSocket] = []
_clients_lock = threading.Lock()


@app.get("/", response_class=HTMLResponse)
async def index():
    html_path = os.path.join(os.path.dirname(__file__), "..", "dashboard", "index.html")
    with open(html_path, "r", encoding="utf-8") as f:
        return f.read()


@app.get("/api/snapshot")
async def snapshot():
    return get_snapshot()


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    with _clients_lock:
        _clients.append(ws)
    try:
        await ws.send_text(json.dumps(get_snapshot()))
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        with _clients_lock:
            if ws in _clients:
                _clients.remove(ws)


import asyncio


async def _broadcast(data: str):
    with _clients_lock:
        dead = []
        for ws in _clients:
            try:
                await ws.send_text(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            _clients.remove(ws)


async def broadcast_loop(interval: float = 1.5):
    while True:
        await asyncio.sleep(interval)
        data = json.dumps(get_snapshot())
        await _broadcast(data)


@app.on_event("startup")
async def startup():
    asyncio.create_task(broadcast_loop())


# ─────────────────────────────────────────────
#  LANÇAR SERVIDOR
# ─────────────────────────────────────────────

_server_thread = None


def start_server(host: str = "127.0.0.1", port: int = 8765, open_browser: bool = True):
    global _server_thread

    config = uvicorn.Config(
        app, host=host, port=port, log_level="warning", loop="asyncio"
    )
    server = uvicorn.Server(config)

    def _run():
        server.run()

    _server_thread = threading.Thread(target=_run, daemon=True)
    _server_thread.start()

    if open_browser:

        def _open():
            time.sleep(1.5)
            webbrowser.open(f"http://{host}:{port}")

        threading.Thread(target=_open, daemon=True).start()

    return f"http://{host}:{port}"
