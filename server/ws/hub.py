from __future__ import annotations
import asyncio
import json
from fastapi import WebSocket

from server.state_reader import read_state


class ConnectionHub:
    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()

    def add(self, ws: WebSocket) -> None:
        self._connections.add(ws)

    def remove(self, ws: WebSocket) -> None:
        self._connections.discard(ws)

    async def send_initial(self, ws: WebSocket) -> None:
        state = read_state()
        await ws.send_text(json.dumps(state, default=str))

    async def broadcast(self, payload: str) -> None:
        dead: set[WebSocket] = set()
        for ws in self._connections:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.add(ws)
        self._connections -= dead

    async def start_polling(self) -> None:
        last_ts: str | None = None
        try:
            while True:
                await asyncio.sleep(1)
                if not self._connections:
                    continue
                state = read_state()
                ts = state.get("ts")
                if ts != last_ts:
                    last_ts = ts
                    await self.broadcast(json.dumps(state, default=str))
        except asyncio.CancelledError:
            pass


hub = ConnectionHub()
