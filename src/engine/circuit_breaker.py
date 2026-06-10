from __future__ import annotations
"""
Circuit Breaker — V9.1

4-level protection system that responds to consecutive losses and drawdown.
Levels are cumulative: each higher level includes restrictions of lower ones.

  GREEN  — Normal trading, no restrictions.
  YELLOW — Caution: lot_multiplier × 0.5. Alert logged.
  ORANGE — Pause: no new entries. Existing positions managed normally.
  RED    — Halt: no new entries + request close of all positions.
           Requires manual reset or 24h automatic reset.

Trigger matrix (first condition met wins):
  Daily drawdown >= 5%   → RED
  Daily drawdown >= 3%   → ORANGE
  Daily drawdown >= 2%   → YELLOW
  Consecutive losses >= 5 → ORANGE
  Consecutive losses >= 3 → YELLOW

VIX panic/kill is handled separately in RegimeRouter → this module
is a drawdown/streak failsafe, not a macro failsafe.
"""
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import IntEnum

logger = logging.getLogger(__name__)


class CBLevel(IntEnum):
    GREEN  = 0
    YELLOW = 1
    ORANGE = 2
    RED    = 3

    def __str__(self) -> str:
        return self.name


# Thresholds
_DD_YELLOW    = 0.02   # -2% daily drawdown
_DD_ORANGE    = 0.03   # -3%
_DD_RED       = 0.05   # -5%
_LOSS_YELLOW  = 3      # consecutive losing trades
_LOSS_ORANGE  = 5

# Lot multipliers per level
LOT_MULT: dict[CBLevel, float] = {
    CBLevel.GREEN:  1.0,
    CBLevel.YELLOW: 0.5,
    CBLevel.ORANGE: 0.0,  # no new entries
    CBLevel.RED:    0.0,
}


@dataclass
class CBState:
    level: CBLevel = CBLevel.GREEN
    consecutive_losses: int = 0
    daily_start_equity: float = 0.0
    current_equity: float = 0.0
    last_trade_result: str = ""    # "win" | "loss" | ""
    red_triggered_at: str = ""     # ISO timestamp; empty = not active
    rationale: list[str] = field(default_factory=list)

    @property
    def daily_drawdown(self) -> float:
        if self.daily_start_equity <= 0:
            return 0.0
        return (self.daily_start_equity - self.current_equity) / self.daily_start_equity

    @property
    def can_open(self) -> bool:
        return self.level < CBLevel.ORANGE

    @property
    def lot_multiplier(self) -> float:
        return LOT_MULT[self.level]

    @property
    def request_close_all(self) -> bool:
        return self.level == CBLevel.RED


class CircuitBreaker:
    """
    Stateful circuit breaker. Thread-safe via internal lock.

    Usage:
        cb = CircuitBreaker()
        cb.set_session_equity(account.equity)  # call once per session start

        # After each trade closes:
        cb.record_trade_result("loss")

        # Each cycle: update equity and evaluate
        cb.update(current_equity=account.equity)
        if not cb.state.can_open:
            skip_new_entries()
        lot_mult *= cb.state.lot_multiplier
    """

    def __init__(
        self,
        dd_yellow:   float = _DD_YELLOW,
        dd_orange:   float = _DD_ORANGE,
        dd_red:      float = _DD_RED,
        loss_yellow: int   = _LOSS_YELLOW,
        loss_orange: int   = _LOSS_ORANGE,
    ):
        self._dd_yellow   = dd_yellow
        self._dd_orange   = dd_orange
        self._dd_red      = dd_red
        self._loss_yellow = loss_yellow
        self._loss_orange = loss_orange
        self._lock = threading.Lock()
        self.state = CBState()
        self._date = datetime.now(timezone.utc).date().isoformat()

    # ── Public API ─────────────────────────────────────────────────────

    def set_session_equity(self, equity: float) -> None:
        """Call once at session start or daily reset."""
        with self._lock:
            if self.state.daily_start_equity == 0.0:
                self.state.daily_start_equity = equity
                self.state.current_equity = equity

    def record_trade_result(self, result: str) -> None:
        """Call after each trade closes. result: 'win' | 'loss'"""
        with self._lock:
            self.state.last_trade_result = result
            if result == "loss":
                self.state.consecutive_losses += 1
                logger.debug(f"[CB] consecutive_losses={self.state.consecutive_losses}")
            elif result == "win":
                self.state.consecutive_losses = 0

    def update(self, current_equity: float) -> CBState:
        """
        Evaluate current conditions and update level.
        Call every cycle. Returns current CBState.
        """
        with self._lock:
            self._maybe_daily_reset(current_equity)
            self.state.current_equity = current_equity
            if self.state.daily_start_equity == 0.0:
                self.state.daily_start_equity = current_equity

            self.state = self._evaluate(self.state)
            return self.state

    def manual_reset(self) -> None:
        """Reset RED level manually (operator intervention)."""
        with self._lock:
            if self.state.level == CBLevel.RED:
                logger.warning("[CB] Manual reset from RED → GREEN")
                self.state.level = CBLevel.GREEN
                self.state.red_triggered_at = ""
                self.state.consecutive_losses = 0
                self.state.rationale = ["manual_reset"]

    # ── Internal ───────────────────────────────────────────────────────

    def _maybe_daily_reset(self, equity: float) -> None:
        today = datetime.now(timezone.utc).date().isoformat()
        if self._date != today:
            self._date = today
            prev_level = self.state.level

            # Auto-reset RED after 24h
            if self.state.level == CBLevel.RED and self.state.red_triggered_at:
                try:
                    triggered = datetime.fromisoformat(self.state.red_triggered_at)
                    now = datetime.now(timezone.utc)
                    if (now - triggered).total_seconds() >= 86_400:
                        logger.warning("[CB] RED auto-reset after 24h")
                        self.state.level = CBLevel.GREEN
                        self.state.red_triggered_at = ""
                except Exception:
                    pass

            self.state.daily_start_equity = equity
            self.state.consecutive_losses = 0
            self.state.rationale = []
            if prev_level != CBLevel.RED:
                self.state.level = CBLevel.GREEN
            logger.info(f"[CB] Daily reset. start_equity={equity:.2f}")

    def _evaluate(self, s: CBState) -> CBState:
        dd = s.daily_drawdown
        losses = s.consecutive_losses
        rationale: list[str] = []

        # Determine new level from conditions (highest wins)
        new_level = CBLevel.GREEN

        if dd >= self._dd_red:
            new_level = CBLevel.RED
            rationale.append(f"drawdown={dd:.1%}>={self._dd_red:.1%}")
        elif dd >= self._dd_orange:
            new_level = CBLevel.ORANGE
            rationale.append(f"drawdown={dd:.1%}>={self._dd_orange:.1%}")
        elif dd >= self._dd_yellow:
            new_level = CBLevel.YELLOW
            rationale.append(f"drawdown={dd:.1%}>={self._dd_yellow:.1%}")

        if losses >= self._loss_orange and new_level < CBLevel.ORANGE:
            new_level = CBLevel.ORANGE
            rationale.append(f"consecutive_losses={losses}>={self._loss_orange}")
        elif losses >= self._loss_yellow and new_level < CBLevel.YELLOW:
            new_level = CBLevel.YELLOW
            rationale.append(f"consecutive_losses={losses}>={self._loss_yellow}")

        # Level changes
        prev = s.level
        if new_level != prev:
            if new_level > prev:
                logger.warning(
                    f"[CB] {prev} → {new_level}: {rationale}"
                )
            else:
                logger.info(
                    f"[CB] Recovery: {prev} → {new_level}"
                )

        s.level = new_level
        s.rationale = rationale

        if new_level == CBLevel.RED and not s.red_triggered_at:
            s.red_triggered_at = datetime.now(timezone.utc).isoformat()
            logger.error(
                f"[CB] RED triggered — halt all entries. "
                f"drawdown={dd:.1%} losses={losses}"
            )

        return s
