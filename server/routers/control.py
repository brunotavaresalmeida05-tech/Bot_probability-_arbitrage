from __future__ import annotations
from typing import Optional, List

from fastapi import APIRouter
from pydantic import BaseModel, field_validator, model_validator

from server.control_writer import write_command, read_audit
import server.bot_manager as bot_manager

router = APIRouter(tags=["control"])


class ConfigPayload(BaseModel):
    max_spread:     Optional[float] = None
    max_daily_loss: Optional[float] = None
    symbols:        Optional[List[str]] = None

    @field_validator("max_spread")
    @classmethod
    def spread_positive(cls, v):
        if v is not None and v < 0:
            raise ValueError("max_spread must be >= 0")
        return v

    @field_validator("max_daily_loss")
    @classmethod
    def loss_positive(cls, v):
        if v is not None and v < 0:
            raise ValueError("max_daily_loss must be >= 0")
        return v

    @field_validator("symbols")
    @classmethod
    def symbols_nonempty(cls, v):
        if v is not None and len(v) == 0:
            raise ValueError("symbols list must not be empty")
        return v

    @model_validator(mode="after")
    def at_least_one_field(self):
        if all(v is None for v in [self.max_spread, self.max_daily_loss, self.symbols]):
            raise ValueError("At least one config field must be provided")
        return self


@router.get("/bot/status")
def bot_status():
    return bot_manager.status()


@router.post("/bot/start")
def bot_start():
    result = bot_manager.start()
    write_command("start", issued_by="dashboard")
    return {"ok": True, **result}


@router.post("/bot/stop")
def bot_stop():
    result = bot_manager.stop()
    write_command("stop", issued_by="dashboard")
    return {"ok": True, **result}


@router.post("/bot/config")
def bot_config(payload: ConfigPayload):
    cfg = payload.model_dump(exclude_none=True)
    entry = write_command("config", issued_by="dashboard", config=cfg)
    return {"ok": True, "command": entry["command"], "config": cfg, "issued_at": entry["issued_at"]}


@router.get("/bot/audit")
def bot_audit(limit: int = 100):
    return read_audit(limit=limit)
