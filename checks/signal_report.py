"""
checks/signal_report.py — Day 2: Signal quality report per asset.

Reads state_history.jsonl and produces a per-symbol table:
  - Signal counts  (BUY / SELL / HOLD per symbol)
  - Execution status breakdown (filled / blocked / rejected / dry_run)
  - Rejection reason categories (regime / gate / no_data / other)
  - Signal rate per day and anomaly flags

Two event formats handled:
  OLD: full cycle with signals/executions fields (detailed)
  NEW: {ts, cycle, n_results} (summary only — no per-symbol signal breakdown)

Usage:
  python checks/signal_report.py [--hours 24]
  python checks/signal_report.py --hours 168   # 7 days
"""
from __future__ import annotations

import json
import sys
import argparse
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT    = Path(__file__).resolve().parent.parent
HISTORY = ROOT / "state" / "state_history.jsonl"

REGIME_KW  = {"ranging", "volatile", "regime", "trending", "adx", "not tradeable"}
GATE_KW    = {"gate", "kill", "news", "correlation", "filter", "blocked", "risk"}
SPREAD_KW  = {"spread", "anomaly", "spike"}
NO_DATA_KW = {"no_data", "no market data", "missing", "stale", "no data"}


def _parse_ts(s: str) -> datetime | None:
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
    except Exception:
        return None


def _classify(message: str) -> str:
    m = message.lower()
    if any(k in m for k in NO_DATA_KW):
        return "no_data"
    if any(k in m for k in REGIME_KW):
        return "regime"
    if any(k in m for k in SPREAD_KW):
        return "spread"
    if any(k in m for k in GATE_KW):
        return "gate"
    return "other"


def load_events(hours: int) -> tuple[list[dict], list[dict]]:
    """Returns (detailed_cycles, summary_cycles)."""
    if not HISTORY.exists():
        return [], []

    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    detailed: list[dict] = []
    summary: list[dict] = []

    try:
        lines = HISTORY.read_text(encoding="utf-8", errors="ignore").splitlines()
        for line in lines:
            try:
                ev = json.loads(line)
            except Exception:
                continue
            ts = _parse_ts(ev.get("ts", ""))
            if not ts or ts < cutoff:
                continue
            if "signals" in ev and "executions" in ev:
                detailed.append(ev)
            elif "cycle" in ev and "n_results" in ev:
                summary.append(ev)
    except Exception:
        pass

    return detailed, summary


def build_symbol_stats(detailed: list[dict]) -> dict[str, dict]:
    stats: dict[str, dict] = defaultdict(lambda: {
        "signals":    {"BUY": 0, "SELL": 0, "HOLD": 0},
        "exec":       defaultdict(int),
        "rejections": defaultdict(int),
        "cycles":     0,
    })

    for ev in detailed:
        for sym, sig in (ev.get("signals") or {}).items():
            direction = sig if isinstance(sig, str) else sig.get("signal", "HOLD")
            direction = direction if direction in ("BUY", "SELL") else "HOLD"
            s = stats[sym]
            s["cycles"] += 1
            s["signals"][direction] += 1

        for sym, exec_data in (ev.get("executions") or {}).items():
            if sym not in stats:
                continue
            status = exec_data.get("status", "unknown")
            stats[sym]["exec"][status] += 1
            if status in ("rejected", "blocked"):
                cat = _classify(str(exec_data.get("message", "")))
                stats[sym]["rejections"][cat] += 1

    return dict(stats)


def print_summary_only(summary: list[dict], hours: int) -> None:
    if not summary:
        return
    total   = len(summary)
    results = sum(ev.get("n_results", 0) for ev in summary)
    days    = hours / 24
    rate    = results / days if days > 0 else 0

    print(f"\n  New-format cycles: {total}  |  Total signals: {results}  |  Rate: {rate:.1f}/day")
    if results == 0:
        print(f"  REVISAR — 0 directional signals in {hours}h.")
        print(f"  Possible causes: MT5 not connected, all symbols in RANGING, regime filter too strict.")
    else:
        print(f"  OK — signals present. Run with --hours covering older data for full breakdown.")


def print_report(stats: dict, summary: list[dict], hours: int) -> None:
    days = hours / 24

    print(f"\n{'='*76}")
    print(f"  SIGNAL QUALITY REPORT — last {hours}h ({days:.1f}d)")
    print(f"{'='*76}")

    if not stats and not summary:
        print(f"\n  No data found in state_history.jsonl for the last {hours}h.")
        print(f"  Check that the bot has been running and writing to state/state_history.jsonl.")
        print(f"{'='*76}\n")
        return

    if stats:
        total_cycles = max((v["cycles"] for v in stats.values()), default=0)
        print(f"\n  Detailed cycles parsed: {total_cycles}")
        print(f"\n  {'Symbol':<12} {'BUY':>5} {'SELL':>5} {'HOLD':>5} |"
              f" {'filled':>6} {'blkd':>5} {'rejct':>5} | {'no_data':>7} {'regime':>7} {'spread':>6} {'gate':>5}")
        print(f"  {'-'*74}")

        all_ok = True
        for sym in sorted(stats):
            s = stats[sym]
            sig = s["signals"]
            exc = s["exec"]
            rej = s["rejections"]

            filled   = exc.get("filled", 0) + exc.get("dry_run", 0)
            blocked  = exc.get("blocked", 0)
            rejected = exc.get("rejected", 0)
            no_data  = rej.get("no_data", 0)
            regime   = rej.get("regime", 0)
            spread   = rej.get("spread", 0)
            gate     = rej.get("gate", 0)

            active = sig["BUY"] + sig["SELL"]
            flag = ""
            if active > 0 and filled == 0 and (rejected + blocked) > 0:
                flag = " [!]"
                all_ok = False

            print(
                f"  {sym:<12} {sig['BUY']:>5} {sig['SELL']:>5} {sig['HOLD']:>5} |"
                f" {filled:>6} {blocked:>5} {rejected:>5} |"
                f" {no_data:>7} {regime:>7} {spread:>6} {gate:>5}{flag}"
            )

        total_buys  = sum(v["signals"]["BUY"]  for v in stats.values())
        total_sells = sum(v["signals"]["SELL"] for v in stats.values())
        total_fills = sum(
            v["exec"].get("filled", 0) + v["exec"].get("dry_run", 0)
            for v in stats.values()
        )
        signal_rate = (total_buys + total_sells) / days if days > 0 else 0

        print(f"\n  Totals: BUY={total_buys}  SELL={total_sells}  fills={total_fills}  rate={signal_rate:.1f} signals/day")

        print(f"\n  Decision:")
        if total_buys + total_sells == 0:
            print(f"  REVISAR — 0 directional signals. Regime filter blocking all entries.")
        elif total_fills == 0 and total_buys + total_sells > 0:
            print(f"  REVISAR — signals generated but 0 executions. Check gates 1-7 and kill_switch.")
        elif not all_ok:
            print(f"  REVISAR — some symbols generating signals that are being blocked. See [!] rows.")
        else:
            print(f"  OK")

    if summary:
        print_summary_only(summary, hours)

    # Invariant check: RANGING symbols must have 0 directional signals
    ranging_violations = []
    for sym, s in stats.items():
        regime_blocks = s["rejections"].get("regime", 0)
        active_fills  = s["exec"].get("filled", 0) + s["exec"].get("dry_run", 0)
        if regime_blocks > 0 and active_fills > 0:
            ranging_violations.append(sym)

    if ranging_violations:
        print(f"\n  PAUSAR — {ranging_violations} had fills despite regime blocks. Audit gate logic.")

    print(f"{'='*76}\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hours", type=int, default=24)
    args = parser.parse_args()

    detailed, summary = load_events(args.hours)
    stats = build_symbol_stats(detailed)
    print_report(stats, summary, args.hours)


if __name__ == "__main__":
    main()
