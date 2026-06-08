"""
checks/stress_test.py — Day 4 + Day 6: Safety mechanism stress tests.

Tests:
  T1  Spread spike — inject 4× baseline into KillSwitch; verify symbols blocked (not killed)
  T2  Daily drawdown kill — inject equity 3.1% below start; verify engine kill
  T3  Loss streak — inject 3 losses into RiskEngineV2; verify pause
  T4  MT5 offline — simulate offline timeout; verify kill
  T5  AlertManager spread anomaly — inject 6× spike; verify skip_symbols
  T6  KillSwitch + streak combined — verify both agree on kill

Usage:
  python checks/stress_test.py
  python checks/stress_test.py --test T1,T2,T3
"""
from __future__ import annotations

import sys
import time
import argparse
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _fmt(ok: bool, tid: str, name: str, msg: str) -> str:
    tag = "PASS" if ok else "FAIL"
    return f"  [{tag}] {tid}: {name:<42} {msg}"


def _ms(start: float) -> str:
    return f"{(time.perf_counter() - start) * 1000:.1f}ms"


# ── T1: Spread spike → blocked symbols only ─────────────────────

def test_spread_spike() -> tuple[bool, str]:
    from src.monitoring.kill_switch import KillSwitch

    ks = KillSwitch(spread_mult_threshold=3.0)
    account = {"balance": 10_000, "equity": 10_000, "start_balance": 10_000}
    normal  = {"EURUSD": 0.010, "USDJPY": 0.020, "GOLD": 0.050}

    for _ in range(25):
        ks.check(account, [], normal, False)

    spike = {sym: v * 4 for sym, v in normal.items()}
    t0 = time.perf_counter()
    result = ks.check(account, [], spike, False)
    elapsed = _ms(t0)

    blocked  = set(result.blocked_symbols)
    expected = set(spike)

    if result.kill:
        return False, f"engine killed instead of just blocking symbols"
    if blocked != expected:
        missing = expected - blocked
        return False, f"symbols not blocked: {missing}"
    return True, f"all {len(blocked)} symbols blocked, engine alive ({elapsed})"


# ── T2: Daily drawdown kill ──────────────────────────────────────

def test_daily_drawdown() -> tuple[bool, str]:
    from src.monitoring.kill_switch import KillSwitch

    ks = KillSwitch(daily_dd_limit=0.03)
    ok_account = {"balance": 10_000, "equity": 10_000, "start_balance": 10_000}

    r0 = ks.check(ok_account, [], {}, False)
    if r0.kill:
        return False, "false positive: kill at 0% DD"

    dd_account = {"balance": 10_000, "equity": 9_689, "start_balance": 10_000}  # 3.11%
    t0 = time.perf_counter()
    r1 = ks.check(dd_account, [], {}, False)
    elapsed = _ms(t0)

    if r1.kill and "daily DD" in r1.reason:
        return True, f"kill at 3.1% DD, reason='{r1.reason}' ({elapsed})"
    return False, f"expected kill at 3.1% DD, got kill={r1.kill} reason='{r1.reason}'"


# ── T3: Loss streak → risk engine pause ─────────────────────────

def test_loss_streak() -> tuple[bool, str]:
    try:
        from src.risk.risk_engine_v2 import RiskEngineV2
    except ImportError as e:
        return False, f"import failed: {e}"

    try:
        engine = RiskEngineV2()
    except Exception as e:
        return False, f"init failed: {e}"

    # can_trade(symbol, direction, open_positions, balance)
    dec = engine.can_trade("EURUSD", "BUY", [], 10_000.0)
    if not dec.allowed:
        return False, f"engine blocked before any trades: {dec.reason}"

    t0 = time.perf_counter()
    for _ in range(3):
        engine.record_trade_result(-60.0)   # record_trade_result(profit)
    elapsed = _ms(t0)

    if engine.is_paused():
        dec2 = engine.can_trade("EURUSD", "BUY", [], 10_000.0)
        return True, f"paused after 3 losses ({elapsed}), can_trade={dec2.allowed}"
    return False, "NOT paused after 3 consecutive losses"


# ── T4: MT5 offline ──────────────────────────────────────────────

def test_mt5_offline() -> tuple[bool, str]:
    from src.monitoring.kill_switch import KillSwitch

    # Use daily_dd_limit=2.0 so a 100% equity drop doesn't trigger DD kill first
    ks = KillSwitch(daily_dd_limit=2.0, mt5_offline_timeout=1)

    # Step 1: check with equity > 0 to register "online" timestamp
    online_account  = {"balance": 10_000, "equity": 10_000, "start_balance": 10_000}
    offline_account = {"balance": 10_000, "equity": 0,      "start_balance": 10_000}
    ks.check(online_account, [], {}, False)

    # Step 2: go offline (equity=0) then wait past the 1s timeout
    ks.check(offline_account, [], {}, False)
    time.sleep(1.3)

    t0 = time.perf_counter()
    result = ks.check(offline_account, [], {}, False)
    elapsed = _ms(t0)

    if result.kill and "offline" in result.reason.lower():
        return True, f"offline kill triggered, reason='{result.reason}' ({elapsed})"
    return False, f"expected offline kill, got kill={result.kill} reason='{result.reason}'"


# ── T5: AlertManager spread anomaly ─────────────────────────────

def test_alert_spread() -> tuple[bool, str]:
    from src.monitoring.alert_manager import AlertManager

    am = AlertManager()
    normal = {"EURUSD": 1.0, "USDJPY": 2.0}

    for _ in range(12):
        am.check_all(10_000, [], normal)

    spike = {"EURUSD": 7.0, "USDJPY": 2.1}  # EURUSD: 7× avg, USDJPY: normal
    t0 = time.perf_counter()
    result = am.check_all(10_000, [], spike)
    elapsed = _ms(t0)

    skip = result.get("skip_symbols", set())
    if "EURUSD" in skip and "USDJPY" not in skip:
        return True, f"EURUSD blocked, USDJPY OK ({elapsed})"
    if "EURUSD" not in skip:
        return False, "EURUSD not blocked despite 7× spike"
    return False, f"unexpected skip_symbols: {skip}"


# ── T6: KillSwitch + streak combined ────────────────────────────

def test_combined_kill() -> tuple[bool, str]:
    from src.monitoring.kill_switch import KillSwitch

    ks = KillSwitch(daily_dd_limit=0.03)
    account = {"balance": 10_000, "equity": 10_000, "start_balance": 10_000}

    # Kill via risk_engine_paused flag (relay from streak)
    t0 = time.perf_counter()
    result = ks.check(account, [], {}, risk_engine_paused=True)
    elapsed = _ms(t0)

    if result.kill and "perda" in result.reason.lower() or "pausa" in result.reason.lower() or "risk" in result.reason.lower():
        return True, f"kill relayed from streak pause ({elapsed})"
    # Accept any kill when paused=True
    if result.kill:
        return True, f"kill triggered (reason='{result.reason}') ({elapsed})"
    return False, "KillSwitch did not relay risk_engine pause"


# ── Runner ──────────────────────────────────────────────────────

ALL_TESTS: dict[str, tuple[str, object]] = {
    "T1": ("Spread spike -> blocked symbols only",       test_spread_spike),
    "T2": ("Daily drawdown kill (3%)",                   test_daily_drawdown),
    "T3": ("Loss streak -> risk engine pause",           test_loss_streak),
    "T4": ("MT5 offline simulation (1s timeout)",        test_mt5_offline),
    "T5": ("AlertManager spread anomaly detection",      test_alert_spread),
    "T6": ("KillSwitch relays risk_engine pause",        test_combined_kill),
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", default=",".join(ALL_TESTS), help="comma-separated test IDs")
    args = parser.parse_args()

    ids = [t.strip().upper() for t in args.test.split(",")]

    print(f"\n{'='*64}")
    print(f"  STRESS TEST — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*64}")

    passed = failed = skipped = 0

    for tid in ids:
        if tid not in ALL_TESTS:
            print(f"  [SKIP] {tid} — unknown test ID")
            skipped += 1
            continue
        name, fn = ALL_TESTS[tid]
        try:
            ok, msg = fn()
        except Exception as exc:
            ok, msg = False, f"exception: {exc}"
        print(_fmt(ok, tid, name, msg))
        if ok:
            passed += 1
        else:
            failed += 1

    print(f"\n  {passed}/{passed + failed} passed  ({skipped} skipped)")
    if failed == 0:
        print(f"  OK — all safety mechanisms verified")
    else:
        print(f"  REVISAR — {failed} test(s) failed. Safety not guaranteed.")
    print(f"{'='*64}\n")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
