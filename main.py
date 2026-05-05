"""
main.py — AlphaSystem V8 (minimal).
Saves state.json to GCS via storage.py.
"""
import time
from datetime import datetime
import json

from dotenv import load_dotenv
load_dotenv()

from storage import save_state, load_state


def build_state(equity=10000, balance=10000, last_signal="none", positions=None):
    """Build state dict (matches schema)."""
    return {
        "equity": equity,
        "balance": balance,
        "positions": positions if positions is not None else [],
        "last_signal": last_signal,
        "updated_at": datetime.utcnow().isoformat()
    }


def run_cycle():
    """Minimal cycle: load state → update → save state."""
    state = load_state()
    print(f"[{datetime.now()}] Loaded state: {state}")

    # Simulate bot logic (replace with real logic later)
    state["equity"] = state.get("equity", 10000) + 10  # simulate change
    state["updated_at"] = datetime.utcnow().isoformat()

    save_state(state)
    print(f"[{datetime.now()}] Saved state: {state}")


def main():
    print("AlphaSystem V8 started (minimal)")
    cycle_interval = 60  # 1 minute for testing
    try:
        while True:
            cycle_start = time.time()
            print(f"\n{'='*50}")
            print(f"CYCLE START - {datetime.now()}")
            run_cycle()
            elapsed = time.time() - cycle_start
            sleep_time = max(0, cycle_interval - elapsed)
            print(f"Cycle completed in {elapsed:.1f}s. Next in {sleep_time:.0f}s...")
            if sleep_time > 0:
                time.sleep(sleep_time)
    except KeyboardInterrupt:
        print("\nBot stopped by user.")


if __name__ == "__main__":
    main()
