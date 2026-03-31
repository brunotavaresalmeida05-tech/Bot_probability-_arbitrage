"""
src/dashboard_server.py
Servidor web leve (FastAPI + WebSockets) que alimenta o dashboard em tempo real.
Fast-tick streaming: preços/equity actualizados a cada ~200ms.
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

from src.analytics.performance_tracker import PerformanceTracker
_tracker = PerformanceTracker(initial_balance=500.0)

_lock = threading.Lock()

_store: dict[str, Any] = {
    "account": {},
    "symbols": {},
    "trades": [],
    "equity_curve": [],
    "open_positions": [],  # ← lido directamente do MT5
    "system_health": {},
    "symbol_quality": {},
    "scaling": {},
    "capital_scaling": {},
    "projections": {},
    "strategies_performance": [],
    "realtime": {},
    "started_at": datetime.now().isoformat(),
    "last_update": None,
    "tick_ts": None,       # timestamp ms do último tick
}

MAX_EQUITY_POINTS = 500
MAX_TRADES = 50

# ─────────────────────────────────────────────
#  TRACKER UPDATER
# ─────────────────────────────────────────────

def _update_tracker_metrics():
    """Recalcula métricas do tracker e actualiza o store."""
    with _lock:
        balance = _store["account"].get("balance", 0)
        equity = _store["account"].get("equity", 0)
        trades = _store["trades"]
        open_pos = _store["open_positions"]
        
        _tracker.update_data(balance, equity, trades)
        
        _store["capital_scaling"] = _tracker.get_capital_scaling_progress()
        _store["projections"] = _tracker.get_projections()
        _store["strategies_performance"] = _tracker.get_strategy_performance()
        _store["realtime"] = _tracker.get_realtime_tracking(open_pos)

# ─────────────────────────────────────────────
#  HEALTH & QUALITY UPDATERS
# ─────────────────────────────────────────────

def update_system_health(health: dict):
    with _lock:
        _store["system_health"] = health
        _store["last_update"] = datetime.now().isoformat()

def update_symbol_quality(symbol: str, quality: dict):
    with _lock:
        _store["symbol_quality"][symbol] = quality
        _store["last_update"] = datetime.now().isoformat()

# ─────────────────────────────────────────────
#  SCALING UPDATERS
# ─────────────────────────────────────────────

def update_scaling(current_cap: float):
    """Actualiza dados de scaling para o dashboard."""
    try:
        import config.settings as cfg
        from src.risk.compounding_manager import CompoundingManager
        
        mgr = CompoundingManager(
            initial_capital=500.0,
            target_monthly_return=getattr(cfg, 'TARGET_MONTHLY_RETURN', 0.15)
        )
        mgr.current_capital = current_cap
        
        params = mgr.get_current_params()
        
        # Encontrar próximo milestone
        next_m = 500
        milestones = sorted(mgr.milestones.keys())
        for m in milestones:
            if m > current_cap:
                next_m = m
                break
        else:
            next_m = milestones[-1] * 2 # Fallback
            
        prev_m = 0
        for m in reversed(milestones):
            if m <= current_cap:
                prev_m = m
                break
        
        prog_pct = 0
        if next_m > prev_m:
            prog_pct = ((current_cap - prev_m) / (next_m - prev_m)) * 100
            
        with _lock:
            _store["scaling"] = {
                "current_capital": current_cap,
                "next_milestone": next_m,
                "progress_pct": min(prog_pct, 100),
                "risk_per_trade": params['risk_per_trade'],
                "max_positions": params['max_positions'],
                "projections": mgr.project_growth(12)
            }
    except Exception as e:
        print(f"Erro ao atualizar scaling dashboard: {e}")

# ─────────────────────────────────────────────
#  FAST TICK STREAMER  (preços a cada ~200ms)
# ─────────────────────────────────────────────
_tick_thread = None
_tick_symbols: list[str] = []


def _fast_tick_loop():
    """Thread que lê ticks do MT5 a alta frequência e actualiza _store."""
    try:
        import MetaTrader5 as mt5
    except ImportError:
        return

    while True:
        try:
            # Actualizar preços de cada símbolo
            for sym in _tick_symbols:
                tick = mt5.symbol_info_tick(sym)
                if tick is None:
                    continue
                with _lock:
                    if sym in _store["symbols"]:
                        _store["symbols"][sym]["bid"] = round(tick.bid, 6)
                        _store["symbols"][sym]["ask"] = round(tick.ask, 6)
                        _store["symbols"][sym]["close"] = round((tick.bid + tick.ask) / 2, 6)
                        _store["symbols"][sym]["tick_time"] = tick.time

            # Actualizar account equity em tempo real
            info = mt5.account_info()
            if info:
                with _lock:
                    _store["account"]["equity"] = round(info.equity, 2)
                    _store["account"]["balance"] = round(info.balance, 2)
                    _store["account"]["margin"] = round(info.margin, 2)
                    _store["account"]["free_margin"] = round(info.margin_free, 2)
                    _store["tick_ts"] = int(time.time() * 1000)

            # Actualizar posições abertas (P&L em tempo real)
            _refresh_positions()

        except Exception:
            pass

        time.sleep(0.2)  # ~200ms = 5 updates/segundo


def start_tick_stream(symbols: list[str]):
    """Inicia o streamer de ticks de alta frequência."""
    global _tick_thread, _tick_symbols
    _tick_symbols = list(symbols)
    if _tick_thread is None:
        _tick_thread = threading.Thread(target=_fast_tick_loop, daemon=True)
        _tick_thread.start()


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


async def broadcast_loop(interval: float = 0.2):
    """Broadcast a cada 200ms para updates em tempo real."""
    counter = 0
    while True:
        await asyncio.sleep(interval)
        
        # Recalcular métricas pesadas a cada ~1s (5 ciclos de 200ms)
        counter += 1
        if counter >= 5:
            _update_tracker_metrics()
            counter = 0
            
        data = json.dumps(get_snapshot())
        await _broadcast(data)


@app.on_event("startup")
async def startup():
    asyncio.create_task(broadcast_loop())


# ─────────────────────────────────────────────
#  HELPERS usados pelo main.py
# ─────────────────────────────────────────────

def set_trading_allowed(v: bool):
    with _lock:
        _store["trading_allowed"] = v


def set_system_state(state: str):
    with _lock:
        _store["system_state"] = state


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
