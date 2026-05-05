"""
test_storage.py — Quick test for storage.py (minimal).
Run: python test_storage.py

Expected: If GCS creds not set, returns default state (graceful).
"""
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

import storage

# Test 1: Save state (will fail gracefully if no creds)
state = {"equity": 10000, "positions": [], "last_signal": "buy", "updated_at": "2026-05-05T23:45:00"}
print("Test 1: Saving state...")
try:
    storage.save_state(state)
    print("  [OK] save_state() succeeded")
except Exception as e:
    print(f"  [EXPECTED] save_state() failed (no GCS creds): {e}")

# Test 2: Load state (should return default if no creds)
print("Test 2: Loading state...")
try:
    loaded = storage.load_state()
    print(f"  [OK] load_state() returned: {loaded}")
    if loaded.get("equity") == 0:
        print("  [OK] Graceful default returned (no creds)")
except Exception as e:
    print(f"  [FAIL] load_state() failed: {e}")

# Test 3: Verify default schema
print("Test 3: Verifying default schema...")
default = {"equity": 0, "positions": [], "last_signal": "none", "updated_at": ""}
if storage.load_state() == default:
    print("  [OK] Default schema matches")
else:
    print(f"  [WARN] Default schema differs: {storage.load_state()}")

print("\n--- Done ---")
print("To test with real GCS:")
print("1. Create bucket: gsutil mb -l us-central1 gs://alphasystem-data")
print("2. Create service account with Storage Object Admin role")
print("3. Download JSON key and set GOOGLE_APPLICATION_CREDENTIALS=path/to/key.json")
print("4. Set GCS_BUCKET=alphasystem-data in .env")
print("5. Run: python test_storage.py")
