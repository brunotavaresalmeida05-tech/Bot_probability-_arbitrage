"""
Main loop — AlphaSystem V8
Cycle: load symbols → fetch candles → compute indicators →
update context → orchestrate (regime + strategy + risk + execution) → log
Saves state, events, history to Google Cloud Storage via storage.py.
"""

import time
import os
from datetime import datetime
from pathlib import Path
import json
import io
import pandas as pd

# GCS config
from dotenv import load_dotenv
load_dotenv()

# Reusable GCS helpers
from storage import get_fs, save_json, load_json, save_csv, load_csv

# Core modules
from core.context import MarketContext
from core.regime import RegimeDetector
from core.strategy import CoreStrategy
from core.risk import RiskEngine
from core.execution import ExecutionEngine
from core.orchestrator import TradingOrchestrator

# Account helpers
from core.mt5_account import get_account_state, get_open_positions_count

# Data and indicators
from core.data_feed import compute_indicators, fetch_candles_from_mt5

# Watchlist
import watchlist as watchlist

# Logging and snapshots
from core.logging import log
from core.snapshot import save_cycle_log


def build_system():
    """Build and return system components."""
    context = MarketContext()
    regime = RegimeDetector()
    strategy = CoreStrategy()
    risk = RiskEngine()
    execution = ExecutionEngine()
    orchestrator = TradingOrchestrator(context, regime, strategy, risk, execution)
    return context, orchestrator


def run_cycle(symbols: list, open_positions: dict, fs=None):
    """Execute a complete cycle for each symbol. Saves to GCS."""
    context, orchestrator = build_system()

    if fs is None:
        fs = get_fs()

    results = []
    state = load_json("state.json", fs)

    for symbol in symbols:
        print(f"\n[{datetime.now()}] Processing {symbol}...")

        # 1. Fetch candles
        candles = fetch_candles_from_mt5(symbol, "M5", 300)
        if candles is None:
            print(f"  [x] Failed to fetch candles for {symbol}")
            continue

        # 2. Compute indicators
        indicators = compute_indicators(candles)

        # 3. Update context
        context.update_symbol(symbol, "M5", candles, indicators)

        # 4. Account state and open positions
        account_state = get_account_state()
        open_pos_count = get_open_positions_count(symbol)

        # 5. Process symbol (regime + signal + risk + execution)
        result = orchestrator.process_symbol(
            symbol=symbol,
            account_state=account_state,
            open_positions_count=open_pos_count
        )

        # 6. Manage open positions (if any)
        if symbol in open_positions:
            mgmt_result = orchestrator.manage_open_positions(
                symbol=symbol,
                position=open_positions[symbol],
                account_state=account_state
            )
            result["management"] = mgmt_result

        # 7. Structured logging
        regime_obj = result.get("regime")
        signal_obj = result.get("signal")
        log.info("cycle_result", extra={
            "symbol": symbol,
            "status": result.get("status"),
            "regime": regime_obj.regime if regime_obj else None,
            "signal_side": signal_obj.side if signal_obj else None,
        })

        # 8. Save snapshot to GCS
        save_json(f"snapshot_{symbol}.json", {
            "symbol": symbol,
            "timestamp": datetime.now().isoformat(),
            "result": result,
            "account": account_state,
            "open_positions_count": open_pos_count,
        }, fs)

        # Update state
        state["equity"] = account_state.get("equity", 0)
        state["last_signal"] = signal_obj.side if signal_obj else "none"

        # Append to history (JSON)
        now_iso = datetime.now().isoformat()
        history_entry = {
            "time": now_iso,
            "symbol": symbol,
            "equity": account_state.get("equity"),
            "signal": signal_obj.side if signal_obj else None,
        }
        history = load_json("history.json", fs)
        if not isinstance(history, list):
            history = []
        history.append(history_entry)
        save_json("history.json", history, fs)

        # Append to events (CSV)
        execution_obj = result.get("execution")
        events_entry = {
            "time": now_iso,
            "symbol": symbol,
            "regime": regime_obj.regime if regime_obj else None,
            "signal": signal_obj.side if signal_obj else None,
            "retcode": execution_obj.retcode if execution_obj else None,
        }
        events_df = load_csv("events.csv", fs)
        if events_df.empty:
            events_df = pd.DataFrame([events_entry])
        else:
            events_df = pd.concat([events_df, pd.DataFrame([events_entry])], ignore_index=True)
        save_csv("events.csv", events_df, fs)

        # Keep cycle log for backward compatibility
        save_cycle_log({
            "timestamp": now_iso,
            "symbol": symbol,
            "equity": account_state.get("equity"),
            "balance": account_state.get("balance"),
            "status": result.get("status"),
            "regime": regime_obj.regime if regime_obj else None,
            "signal": signal_obj.side if signal_obj else None,
            "retcode": execution_obj.retcode if execution_obj else None,
            "result": result
        })

        results.append(result)
        print(f"  -> Status: {result.get('status')}")

    # Save final state
    save_json("state.json", state, fs)
    return results


def main():
    # Initial setup
    symbols = [s["name"] for s in watchlist.WATCHLIST]
    if not symbols:
        print("Watchlist empty. Using EURUSD as default.")
        symbols = ["EURUSD"]

    open_positions = {}

    print(f"AlphaSystem V8 started - {len(symbols)} symbols")
    print(f"Symbols: {symbols}")

    cycle_interval = 300  # 5 minutes

    try:
        while True:
            cycle_start = time.time()
            print(f"\n{'='*50}")
            print(f"CYCLE START - {datetime.now()}")

            run_cycle(symbols, open_positions)

            elapsed = time.time() - cycle_start
            sleep_time = max(0, cycle_interval - elapsed)
            print(f"\nCycle completed in {elapsed:.1f}s. Next in {sleep_time:.0f}s...")
            if sleep_time > 0:
                time.sleep(sleep_time)

    except KeyboardInterrupt:
        print("\nSystem stopped by user.")


if __name__ == "__main__":
    main()
