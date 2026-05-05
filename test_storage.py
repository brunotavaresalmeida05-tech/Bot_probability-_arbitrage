"""
test_storage.py — Quick test for storage.py (minimal).
Run: python test_storage.py
"""
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

import storage

# Test 1: Save state
state = {"equity": 10000, "positions": [], "last_signal": "buy", "updated_at": "2026-05-05T23:45:00"}
print("Test 1: Saving state...")
try:
    storage.save_state(state)
    print("  [OK] save_state() succeeded")
except Exception as e:
    print(f"  [FAIL] save_state() failed: {e}")

# Test 2: Load state
print("Test 2: Loading state...")
try:
    loaded = storage.load_state()
    print(f"  [OK] load_state() returned: {loaded}")
    if loaded == state:
        print("  [OK] Round-trip match!")
    else:
        print("  [WARN] Loaded state differs from saved state")
except Exception as e:
    print(f"  [FAIL] load_state() failed: {e}")

# Test 3: Load non-existent state (should return default)
print("Test 3: Loading non-existent state...")
try:
    # Temporarily break the path to simulate missing file
    import storage as stg
    original = stg.GCS_BUCKET
    stg.GCS_BUCKET = "non-existent-bucket-12345"
    default = stg.load_state()
    print(f"  [OK] Default state returned: {default}")
    stg.GCS_BUCKET = original
except Exception as e:
    print(f"  [FAIL] Default state failed: {e}")

print("\n--- Done ---")
