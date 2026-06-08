from __future__ import annotations
import asyncio
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path

import jwt
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

_DASHBOARD_DIR = Path(__file__).resolve().parent.parent / "dashboard"

from server.auth import check_credentials, create_token, verify_token, _secret
from server.routers import status, trades, history, control
from server.routers import dashboard_api
from server.routers import v9
from server.state_reader import read_state
from server.ws.hub import hub
from src.session_scheduler import SessionScheduler

_scheduler = SessionScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(hub.start_polling())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="AlphaSystem API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(status.router,        prefix="/api")
app.include_router(trades.router,        prefix="/api")
app.include_router(history.router,       prefix="/api")
app.include_router(control.router,       prefix="/api")
app.include_router(dashboard_api.router, prefix="/api")
app.include_router(v9.router,           prefix="/api")


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    username: str
    password: str


@app.post("/api/auth/login")
def login(body: LoginRequest):
    if not check_credentials(body.username, body.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return {"access_token": create_token(body.username), "token_type": "bearer"}


# ---------------------------------------------------------------------------
# Public endpoints
# ---------------------------------------------------------------------------

@app.get("/api/health")
def health():
    return {"ok": True, "version": "1.0.0"}


@app.get("/api/session")
def session_info():
    return _scheduler.session_info()


# ---------------------------------------------------------------------------
# WebSocket
# ---------------------------------------------------------------------------

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket, token: str = ""):
    await ws.accept()
    try:
        jwt.decode(token, _secret(), algorithms=["HS256"])
    except Exception:
        await ws.close(code=1008, reason="Invalid token")
        return

    hub.add(ws)
    await hub.send_initial(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        hub.remove(ws)


# Serve dashboard/ as static files at root — must come AFTER all API routes
# so /api/* and /ws routes take priority.
if _DASHBOARD_DIR.exists():
    app.mount("/", StaticFiles(directory=str(_DASHBOARD_DIR), html=True), name="dashboard")
