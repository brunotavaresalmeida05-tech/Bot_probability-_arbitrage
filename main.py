"""
main.py — AlphaSystem V8 (minimal).
Saves state.json and events.csv to GCS via storage.py.
"""
from storage import save_state, save_events
import pandas as pd
from datetime import datetime

def main():
    # Save state.json
    state = {
        "equity": 10000,
        "balance": 10000,
        "positions": [],
        "last_signal": "buy",
        "updated_at": datetime.utcnow().isoformat()
    }
    save_state(state)
    print(f"[OK] Saved state.json: {state}")

    # Save events.csv
    events = pd.DataFrame([
        {
            "ts": datetime.utcnow().isoformat(),
            "event": "start",
            "detail": "bot iniciado",
            "asset": "BTCUSDT",
            "side": "buy",
            "price": 0,
            "quantity": 0
        }
    ])
    save_events(events)
    print(f"[OK] Saved events.csv: {events.shape[0]} rows")

if __name__ == "__main__":
    main()
