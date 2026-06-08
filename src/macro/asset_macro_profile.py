"""
src/macro/asset_macro_profile.py — Asset Macro Profile Loader.

Reads config/macro_asset_map.yaml and provides per-symbol metadata:
  - risk_mode
  - primary/secondary drivers
  - key events (for widened blackout)
  - rate sensitivity
  - confirmation data requirements

Usage:
    profile = AssetMacroProfile()
    mode    = profile.risk_mode("USDJPY")          # "high"
    blackout = profile.blackout_minutes("USDJPY")  # 45
    drivers  = profile.primary_drivers("GOLD")     # ["real_yields","fed","dxy","stress"]
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger(__name__)

_MAP_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "macro_asset_map.yaml"

# Risk mode → global multiplier cap
_RISK_MODE_CAP: dict[str, float] = {
    "low":          1.00,
    "medium":       0.90,
    "medium_high":  0.80,
    "high":         0.70,
}

# Risk mode → additional event blackout multiplier
# (applied on top of the base PolicyShock blackout)
_RISK_MODE_EVENT_MULT: dict[str, float] = {
    "low":         0.80,
    "medium":      0.50,
    "medium_high": 0.35,
    "high":        0.15,
}


class AssetMacroProfile:
    """
    Singleton-style loader. Load once; call methods per-symbol.
    """

    def __init__(self, path: Path | None = None):
        self._path = path or _MAP_PATH
        self._data: dict = {}
        self._load()

    def _load(self) -> None:
        try:
            with open(self._path, encoding="utf-8") as f:
                raw = yaml.safe_load(f)
            self._data = raw.get("symbols", {})
            logger.info(f"[AssetMacroProfile] Loaded {len(self._data)} symbols.")
        except Exception as e:
            logger.warning(f"[AssetMacroProfile] Load failed: {e}")
            self._data = {}

    def _get(self, symbol: str) -> dict:
        return self._data.get(symbol, {})

    def risk_mode(self, symbol: str) -> str:
        return self._get(symbol).get("risk_mode", "medium")

    def risk_mode_cap(self, symbol: str) -> float:
        """Maximum lot multiplier based on symbol's risk mode."""
        return _RISK_MODE_CAP.get(self.risk_mode(symbol), 0.85)

    def blackout_minutes(self, symbol: str) -> int:
        return int(self._get(symbol).get("event_blackout_min", 15))

    def primary_drivers(self, symbol: str) -> list[str]:
        return self._get(symbol).get("primary_drivers", [])

    def secondary_drivers(self, symbol: str) -> list[str]:
        return self._get(symbol).get("secondary_drivers", [])

    def key_events(self, symbol: str) -> list[str]:
        return self._get(symbol).get("key_events", [])

    def rate_sensitivity(self, symbol: str) -> dict[str, float]:
        return self._get(symbol).get("rate_sensitivity", {})

    def confirm_data(self, symbol: str) -> list[str]:
        return self._get(symbol).get("confirm_data", [])

    def notes(self, symbol: str) -> str:
        return self._get(symbol).get("macro_notes", "")

    def event_mult_during_key_event(self, symbol: str) -> float:
        """Lot multiplier to apply when a key event is near."""
        return _RISK_MODE_EVENT_MULT.get(self.risk_mode(symbol), 0.40)

    def full_profile(self, symbol: str) -> dict:
        p = self._get(symbol)
        if not p:
            return {"symbol": symbol, "risk_mode": "medium", "known": False}
        return {
            "symbol":         symbol,
            "risk_mode":      p.get("risk_mode", "medium"),
            "primary":        p.get("primary_drivers", []),
            "secondary":      p.get("secondary_drivers", []),
            "key_events":     p.get("key_events", []),
            "blackout_min":   p.get("event_blackout_min", 15),
            "rate_sens":      p.get("rate_sensitivity", {}),
            "confirm":        p.get("confirm_data", []),
            "notes":          p.get("macro_notes", ""),
            "known":          True,
        }

    def all_symbols(self) -> list[str]:
        return list(self._data.keys())
