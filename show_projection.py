"""
show_projection.py
Prints capital compounding projection based on 1.5%/week growth rate.
Run: python show_projection.py
"""

import sys, os
sys.path.insert(0, os.path.dirname(__file__))

import config.settings as cfg
from src.capital_scaling import get_retail_milestone, get_retail_lot_size

WEEKLY_GROWTH = 0.015   # 1.5% per week (conservative)
TRADES_PER_WEEK = 10    # average

# Projection table from task
MILESTONES = [
    {'week': 0,  'note': 'Current'},
    {'week': 2,  'note': ''},
    {'week': 4,  'note': 'Milestone 1 target'},
    {'week': 8,  'note': ''},
    {'week': 12, 'note': ''},
    {'week': 16, 'note': 'Milestone 2 target'},
    {'week': 24, 'note': ''},
    {'week': 36, 'note': 'Milestone 3 target'},
    {'week': 52, 'note': 'Annual target'},
]


def project(initial: float, weeks: int, growth: float = WEEKLY_GROWTH) -> float:
    return initial * ((1 + growth) ** weeks)


def weekly_pnl(balance: float, growth: float = WEEKLY_GROWTH) -> tuple:
    pnl = balance * growth
    return pnl * 0.7, pnl * 1.3   # low, high estimate


def main():
    try:
        from src.mt5_connector import get_account_info, connect
        if connect():
            info = get_account_info()
            initial = info.get('balance', cfg.INITIAL_CAPITAL)
            from src.mt5_connector import disconnect; disconnect()
        else:
            initial = cfg.INITIAL_CAPITAL
    except Exception:
        initial = cfg.INITIAL_CAPITAL

    print()
    print("=" * 75)
    print("  TRADING BOT V6 — CAPITAL PROJECTION (1.5% / week, conservative)")
    print(f"  Starting balance: €{initial:.2f}")
    print("=" * 75)
    print(f"  {'Week':<6} {'Balance':>10} {'Lot':>6} {'Milestone':<16} "
          f"{'P&L est/week':>14}  {'Note'}")
    print("  " + "-" * 72)

    prev_week = 0
    for entry in MILESTONES:
        w = entry['week']
        bal = project(initial, w)
        m = get_retail_milestone(bal)
        lot = get_retail_lot_size(bal)
        lo, hi = weekly_pnl(bal)
        note = entry.get('note', '')
        print(f"  {w:<6} €{bal:>8.0f}  {lot:>5.2f}  {m['name']:<16} "
              f"  +€{lo:.0f}–€{hi:.0f}   {note}")

    print()
    print(f"  Compound assumptions: {WEEKLY_GROWTH*100:.1f}%/week | "
          f"~{TRADES_PER_WEEK} trades/week")
    print("=" * 75)
    print()


if __name__ == '__main__':
    main()
