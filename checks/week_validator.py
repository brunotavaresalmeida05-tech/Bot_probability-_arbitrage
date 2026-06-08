"""
checks/week_validator.py — Day 7: 7-day validation + ADVANCE / MANTER / PAUSAR.

Usage:
  python checks/week_validator.py [--days 7] [--equity 10000] [--monte-carlo 2000]

Decision thresholds (from checklist):
  AVANÇAR  (scale to 0.75%): PF >= 1.3  AND max_DD <= 6%   AND WR >= 48%
  MANTER   (calibrate 7d):   PF in [1.1, 1.3) OR WR in [40%, 48%)
  PAUSAR   (revert):         PF < 1.0  OR  max_DD > 8%
  AGUARDAR:                  < 20 trades (decision unreliable)
"""
from __future__ import annotations

import json
import sys
import argparse
import random
from collections import defaultdict
from datetime import date, datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.monitoring.paper_validator import PaperValidator, TradeRecord

HISTORY = ROOT / "state" / "state_history.jsonl"

# ── Decision thresholds ────────────────────────────────────────
ADV_PF   = 1.3
ADV_DD   = 6.0   # max daily DD %
ADV_WR   = 48.0  # %
MANT_PF  = 1.1
MANT_WR  = 40.0  # %
PAUSE_PF = 1.0
PAUSE_DD = 8.0   # %
MIN_TRADES = 20


# ── Helpers ────────────────────────────────────────────────────

def _max_dd_pct(equity_curve: list[float]) -> float:
    if len(equity_curve) < 2:
        return 0.0
    peak = equity_curve[0]
    max_dd = 0.0
    for e in equity_curve:
        if e > peak:
            peak = e
        if peak > 0:
            dd = (peak - e) / peak * 100
            max_dd = max(max_dd, dd)
    return round(max_dd, 3)


# ── Monte Carlo ────────────────────────────────────────────────

def monte_carlo(
    trades: list[TradeRecord],
    start_equity: float = 10_000.0,
    n_sims: int = 2000,
    seed: int = 42,
) -> dict:
    if len(trades) < 5:
        return {"n_sims": 0, "note": f"insufficient trades ({len(trades)} < 5)"}

    rng = random.Random(seed)
    pnl = [t.profit for t in trades]
    n   = len(pnl)

    max_dds: list[float] = []
    finals:  list[float] = []

    for _ in range(n_sims):
        sample = rng.choices(pnl, k=n)
        eq     = start_equity
        curve  = [eq]
        for p in sample:
            eq += p
            curve.append(eq)
        max_dds.append(_max_dd_pct(curve))
        finals.append(curve[-1])

    max_dds.sort()

    def _pct(lst: list[float], q: float) -> float:
        return lst[max(0, int(len(lst) * q) - 1)]

    p_dd6    = sum(1 for d in max_dds if d > ADV_DD)  / n_sims * 100
    p_dd8    = sum(1 for d in max_dds if d > PAUSE_DD) / n_sims * 100
    p_profit = sum(1 for e in finals if e > start_equity) / n_sims * 100

    return {
        "n_sims":       n_sims,
        "n_trades":     n,
        "dd_p50":       round(_pct(max_dds, 0.50), 2),
        "dd_p90":       round(_pct(max_dds, 0.90), 2),
        "dd_p95":       round(_pct(max_dds, 0.95), 2),
        "p_dd_gt_6":    round(p_dd6, 1),
        "p_dd_gt_8":    round(p_dd8, 1),
        "p_profitable": round(p_profit, 1),
    }


# ── Per-symbol breakdown ───────────────────────────────────────

def symbol_breakdown(trades: list[TradeRecord]) -> dict[str, dict]:
    by_sym: dict[str, dict] = defaultdict(lambda: {"wins": 0, "losses": 0, "pnl": 0.0})
    for t in trades:
        s = by_sym[t.symbol]
        s["pnl"] += t.profit
        if t.profit > 0:
            s["wins"] += 1
        else:
            s["losses"] += 1

    result = {}
    for sym, s in sorted(by_sym.items()):
        n = s["wins"] + s["losses"]
        result[sym] = {
            "trades":     n,
            "win_rate":   round(s["wins"] / n * 100, 1) if n else 0.0,
            "pnl":        round(s["pnl"], 2),
            "expectancy": round(s["pnl"] / n, 4) if n else 0.0,
        }
    return result


# ── Decision ───────────────────────────────────────────────────

def decide(
    win_rate: float,
    profit_factor: float,
    max_daily_dd: float,
    total_trades: int,
    mc: dict,
) -> tuple[str, list[str]]:
    reasons: list[str] = []

    if total_trades < MIN_TRADES:
        return "AGUARDAR", [f"apenas {total_trades} trades — mínimo {MIN_TRADES} para decisão fiável"]

    # PAUSAR — hard failures
    if profit_factor < PAUSE_PF or max_daily_dd > PAUSE_DD:
        if profit_factor < PAUSE_PF:
            reasons.append(f"PF={profit_factor:.3f} < {PAUSE_PF:.1f}")
        if max_daily_dd > PAUSE_DD:
            reasons.append(f"max_DD={max_daily_dd:.1f}% > {PAUSE_DD:.0f}%")
        mc_p = mc.get("p_dd_gt_8", 0)
        if mc_p > 40:
            reasons.append(f"MC P(DD>8%)={mc_p:.0f}% elevado")
        return "PAUSAR", reasons

    # AVANÇAR — all criteria pass
    mc_safe = mc.get("p_dd_gt_6", 100) < 25
    if profit_factor >= ADV_PF and max_daily_dd <= ADV_DD and win_rate >= ADV_WR and mc_safe:
        reasons.append(f"PF={profit_factor:.3f} >= {ADV_PF}")
        reasons.append(f"WR={win_rate:.1f}% >= {ADV_WR:.0f}%")
        reasons.append(f"max_DD={max_daily_dd:.1f}% <= {ADV_DD:.0f}%")
        reasons.append(f"MC P(DD>6%)={mc.get('p_dd_gt_6', '?')}% < 25%")
        return "AVANÇAR", reasons

    # MANTER — partial pass
    reasons.append(f"PF={profit_factor:.3f}  WR={win_rate:.1f}%  DD={max_daily_dd:.1f}%")
    gaps: list[str] = []
    if profit_factor < ADV_PF:
        gaps.append(f"PF abaixo de {ADV_PF} (actual {profit_factor:.3f})")
    if win_rate < ADV_WR:
        gaps.append(f"WR abaixo de {ADV_WR:.0f}% (actual {win_rate:.1f}%)")
    if max_daily_dd > ADV_DD:
        gaps.append(f"DD acima de {ADV_DD:.0f}% (actual {max_daily_dd:.1f}%)")
    if not mc_safe:
        gaps.append(f"MC P(DD>6%)={mc.get('p_dd_gt_6', '?')}% >= 25%")
    reasons.extend(gaps)
    return "MANTER", reasons


# ── Print ──────────────────────────────────────────────────────

def print_report(
    val,
    mc: dict,
    sym_bd: dict,
    decision: str,
    reasons: list[str],
    days: int,
) -> None:
    sep  = "=" * 62
    sep2 = "-" * 62

    print(f"\n{sep}")
    print(f"  WEEK VALIDATOR — {datetime.now().strftime('%Y-%m-%d %H:%M')} — {days}d")
    print(sep)

    # Core metrics (reuse PaperValidator's formatted lines — labels only)
    wins   = sum(1 for t in val.recent_trades if t.is_win)
    losses = len(val.recent_trades) - wins
    exp    = val.total_pnl / val.total_trades if val.total_trades else 0.0
    avg_w  = val.gross_profit / wins  if wins   > 0 else 0.0
    avg_l  = val.gross_loss   / losses if losses > 0 else 0.0

    print(f"\n  METRICAS CORE ({val.total_trades} trades):")
    print(f"    {'Win Rate':<22} {val.win_rate:>6.1f}%   target >= {ADV_WR:.0f}%")
    print(f"    {'Profit Factor':<22} {val.profit_factor:>6.3f}    target >= {ADV_PF:.1f}")
    print(f"    {'Max Daily DD':<22} {val.max_daily_dd:>6.1f}%   target <= {ADV_DD:.0f}%")
    print(f"    {'Stability (dias)':<22} {val.days_stable:>6d}")
    print(f"    {'Total PnL (EUR)':<22} {val.total_pnl:>+7.2f}")
    print(f"    {'Expectancy (EUR/trade)':<22} {exp:>+7.2f}")
    print(f"    {'Avg win':<22} {avg_w:>+7.2f}    Avg loss {-avg_l:>+7.2f}")

    # Per-day
    if val.daily_stats:
        print(f"\n  POR DIA (últimos 7):")
        print(f"    {'Date':<12} {'Trades':>6} {'P&L':>8} {'DD%':>6}")
        for d in val.daily_stats[-7:]:
            day_pnl = d.gross_profit - d.gross_loss
            print(f"    {str(d.date):<12} {d.trades:>6} {day_pnl:>+8.2f} {d.drawdown_pct:>5.1f}%")

    # Per-symbol
    if sym_bd:
        print(f"\n  POR SIMBOLO:")
        print(f"    {'Symbol':<16} {'N':>5} {'WR':>6} {'PnL':>8} {'Expect':>8}")
        for sym, s in sorted(sym_bd.items(), key=lambda x: -x[1]["trades"]):
            print(f"    {sym:<16} {s['trades']:>5} {s['win_rate']:>5.1f}% {s['pnl']:>+8.2f} {s['expectancy']:>+8.4f}")

    # Monte Carlo
    if mc.get("n_sims", 0) > 0:
        print(f"\n  MONTE CARLO ({mc['n_sims']} sims, {mc['n_trades']} trades):")
        print(f"    DD p50={mc['dd_p50']:.1f}%  p90={mc['dd_p90']:.1f}%  p95={mc['dd_p95']:.1f}%")
        print(f"    P(DD > {ADV_DD:.0f}%) = {mc['p_dd_gt_6']:.0f}%   P(DD > {PAUSE_DD:.0f}%) = {mc['p_dd_gt_8']:.0f}%")
        print(f"    P(profitable) = {mc['p_profitable']:.0f}%")
    else:
        print(f"\n  MONTE CARLO: {mc.get('note', 'N/A')}")

    # Decision
    markers = {"AVANÇAR": ">>>", "PAUSAR": "!!!", "MANTER": "---", "AGUARDAR": "..."}
    marker = markers.get(decision, "   ")

    print(f"\n  {sep2}")
    print(f"  DECISAO: {marker} {decision}")
    for r in reasons:
        print(f"    * {r}")

    if decision == "AVANÇAR":
        print(f"\n  Proximo passo: risk_pct_per_trade 0.005 -> 0.0075")
        print(f"  Ficheiro: config/strategies.yaml linha 65 (risk_pct_per_trade)")
    elif decision == "MANTER":
        print(f"\n  Proximo passo: correr mais 7 dias, rever entry/SL por simbolo")
    elif decision == "PAUSAR":
        print(f"\n  Proximo passo: desativar estrategias em strategies.yaml, auditar gates")
    elif decision == "AGUARDAR":
        print(f"\n  Proximo passo: acumular trades — correr ao fim de mais {MIN_TRADES - val.total_trades} trades")

    print(f"  {sep}\n")


# ── Main ───────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days",         type=int,   default=7)
    parser.add_argument("--equity",       type=float, default=10_000.0)
    parser.add_argument("--monte-carlo",  type=int,   default=2000, dest="mc_sims")
    args = parser.parse_args()

    start = date.today() - timedelta(days=args.days)
    validator = PaperValidator(history_path=HISTORY, start_date=start)

    try:
        import MetaTrader5 as _mt5
        val = validator.evaluate(mt5=_mt5)
    except ImportError:
        val = validator.evaluate(mt5=None)

    sym_bd   = symbol_breakdown(val.recent_trades)
    mc       = monte_carlo(val.recent_trades, start_equity=args.equity, n_sims=args.mc_sims)
    decision, reasons = decide(
        val.win_rate, val.profit_factor, val.max_daily_dd, val.total_trades, mc
    )

    print_report(val, mc, sym_bd, decision, reasons, args.days)

    return 0 if decision in ("AVANÇAR", "MANTER") else 1


if __name__ == "__main__":
    sys.exit(main())
