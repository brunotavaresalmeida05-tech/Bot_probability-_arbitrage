from __future__ import annotations
"""
AlphaSystem V9 — Entry Point
Run with: python -m src.main
NEVER: python src/main.py (src/signal/ shadows stdlib signal)
"""
import logging
import os
import signal
import time
from pathlib import Path

import yaml
from dotenv import load_dotenv

from src.engine.orchestrator import Orchestrator
from src.mt5_bridge import MT5Bridge
from src.session.market_sessions import current_sessions, is_tradeable_for, get_sleep_seconds

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "config.yaml"
PID_PATH = Path("state/bot.pid")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)
logger = logging.getLogger("main")

# Sleep intervals per session type (seconds)
_SLEEP = {
    "london_ny_overlap": 60,
    "london": 90,
    "new_york": 90,
    "asia": 300,
    "closed": 300,
}


def _load_config() -> dict:
    if not CONFIG_PATH.exists():
        logger.warning(f"Config not found at {CONFIG_PATH}, using defaults")
        return {}
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _build_engine_config(cfg: dict) -> dict:
    """Flatten config into dict expected by Orchestrator."""
    symbols = cfg.get("market", {}).get("symbols", [
        "EURUSD", "GBPUSD", "USDJPY", "Usa500", "UsaTec", "Ger40", "GOLD", "Brent", "LCrude"
    ])
    risk = cfg.get("risk", {})
    return {
        "symbols": symbols,
        "risk": {
            "max_daily_loss_pct": risk.get("max_daily_loss", 0.03),
            "max_weekly_loss_pct": 0.08,
            "min_lot": 0.01,
            "max_lot": 10.0,
        },
        "dry_run": cfg.get("mode", {}).get("dry_run", True),
    }


class BotApp:
    def __init__(self):
        self._shutdown = False
        self._engine: Orchestrator | None = None
        self._mt5: MT5Bridge | None = None
        self._cfg: dict = {}

    def _handle_signal(self, signum, frame):
        logger.info(f"Signal {signum} — shutting down")
        self._shutdown = True

    def setup(self):
        for p in ["logs", "state", "output"]:
            Path(p).mkdir(parents=True, exist_ok=True)

        load_dotenv()
        self._cfg = _load_config()
        dry_run = self._cfg.get("mode", {}).get("dry_run", True)

        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

        api_keys = {
            "FINNHUB_KEY": os.getenv("FINNHUB_API_KEY", ""),
            "FRED_KEY":    os.getenv("FRED_API_KEY", ""),
        }

        # MT5 connection
        live_enabled = self._cfg.get("live", {}).get("enabled", False)
        if live_enabled:
            self._mt5 = MT5Bridge(self._cfg, logger)
            self._mt5.connect()

        engine_cfg = _build_engine_config(self._cfg)
        self._engine = Orchestrator(
            mt5=self._mt5,
            config=engine_cfg,
            api_keys=api_keys,
            dry_run=dry_run,
        )
        self._engine.start_daemons()

        # Write PID
        PID_PATH.parent.mkdir(parents=True, exist_ok=True)
        PID_PATH.write_text(str(os.getpid()))

        mode = "DRY RUN" if dry_run else "LIVE"
        logger.info(f"AlphaSystem V9 started | mode={mode} live={live_enabled} symbols={len(engine_cfg.get('symbols',[]))}")

    def run(self):
        self.setup()
        try:
            while not self._shutdown:
                session = current_sessions()
                sleep_s = get_sleep_seconds(session)

                try:
                    state = self._engine.run_cycle()
                    # Pull MT5 account info every cycle
                    if self._mt5 and getattr(self._mt5, "connected", False):
                        try:
                            import MetaTrader5 as mt5lib
                            info = mt5lib.account_info()
                            if info:
                                self._engine.update_account(info)
                        except Exception:
                            pass
                    # Per-asset tradeability summary
                    syms = self._cfg.get("market", {}).get("symbols", [])
                    active_syms = [s for s in syms if is_tradeable_for(s, session)]
                    logger.info(
                        f"cycle={state['cycle_count']} session={state['session']} "
                        f"active_syms={len(active_syms)}/{len(syms)} "
                        f"scenario={state['scenario']} macro={state['macro']['global_regime']} "
                        f"signals={len(state['signals'])} sleep={sleep_s}s"
                    )
                    if active_syms:
                        logger.info(f"Analysing: {', '.join(active_syms)}")
                except Exception as e:
                    logger.exception(f"Cycle error: {e}")

                time.sleep(sleep_s)
        except KeyboardInterrupt:
            logger.info("KeyboardInterrupt")
        finally:
            self.cleanup()

    def cleanup(self):
        if self._engine:
            self._engine.stop()
        if self._mt5:
            self._mt5.shutdown()
        try:
            PID_PATH.unlink(missing_ok=True)
        except Exception:
            pass
        logger.info("AlphaSystem V9 stopped")


def main():
    BotApp().run()


if __name__ == "__main__":
    main()
