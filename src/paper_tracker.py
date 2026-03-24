"""
src/paper_tracker.py
Paper Trading Tracker — 30 dias de tracking persistente antes de ir live.

Funcionalidades:
- Persiste resumo diário num JSON (logs/paper_history.json)
- Calcula métricas rolling de 30 dias (Sharpe, MaxDD, win rate, etc.)
- Score de "go-live readiness" baseado em critérios objectivos
- Integrado com main.py e daily_report.py
"""

import os
import json
import csv
import numpy as np
from datetime import datetime, date, timedelta
from typing import Optional
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import config.settings as cfg


# ═══════════════════════════════════════════════════════════════
#  FICHEIRO DE HISTÓRICO
# ═══════════════════════════════════════════════════════════════

HISTORY_FILE = os.path.join(cfg.LOG_DIR, "paper_history.json")

# Critérios mínimos para ir live
GO_LIVE_CRITERIA = {
    "min_days":       30,     # mínimo 30 dias de paper
    "min_trades":     50,     # mínimo 50 trades
    "min_win_rate":   45.0,   # win rate >= 45%
    "min_sharpe":     0.5,    # Sharpe >= 0.5
    "max_dd_pct":     -15.0,  # max drawdown <= 15%
    "min_profit_factor": 1.2, # profit factor >= 1.2
    "max_consecutive_loss_days": 5,  # máximo 5 dias seguidos negativos
}


def _load_history() -> list:
    """Carrega histórico de days do ficheiro JSON."""
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save_history(history: list):
    """Salva histórico no ficheiro JSON."""
    os.makedirs(cfg.LOG_DIR, exist_ok=True)
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, default=str)


def _read_trades_for_date(target_date: date) -> list:
    """Lê trades do CSV para uma data específica."""
    target_str = target_date.strftime("%Y-%m-%d")
    trades = []
    csv_path = cfg.CSV_LOG_FILE

    if not os.path.exists(csv_path):
        return trades

    try:
        with open(csv_path, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("timestamp", "").startswith(target_str):
                    trades.append(row)
    except Exception:
        pass

    return trades


# ═══════════════════════════════════════════════════════════════
#  REGISTO DIÁRIO
# ═══════════════════════════════════════════════════════════════

def record_day(
    account_balance: float,
    equity: float = None,
    target_date: date = None,
) -> dict:
    """
    Regista o resumo de um dia de paper trading.
    Chamado ao fim da sessão (pelo scheduler ou pelo main.py).
    """
    target_date = target_date or date.today()
    trades = _read_trades_for_date(target_date)

    pnl_list = [float(t.get("profit_currency", 0)) for t in trades]
    pips_list = [float(t.get("profit_pips", 0)) for t in trades]
    wins = [p for p in pnl_list if p > 0]
    losses = [p for p in pnl_list if p < 0]

    day_record = {
        "date":          target_date.strftime("%Y-%m-%d"),
        "balance":       round(account_balance, 2),
        "equity":        round(equity or account_balance, 2),
        "n_trades":      len(trades),
        "pnl":           round(sum(pnl_list), 2),
        "pnl_pips":      round(sum(pips_list), 1),
        "wins":          len(wins),
        "losses":        len(losses),
        "win_rate":      round(len(wins) / len(trades) * 100, 1) if trades else 0.0,
        "best_trade":    round(max(pnl_list), 2) if pnl_list else 0.0,
        "worst_trade":   round(min(pnl_list), 2) if pnl_list else 0.0,
        "symbols_traded": list(set(t.get("symbol", "") for t in trades)),
    }

    # Carregar, atualizar (evitar duplicados), salvar
    history = _load_history()
    history = [d for d in history if d["date"] != day_record["date"]]
    history.append(day_record)
    history.sort(key=lambda x: x["date"])
    _save_history(history)

    return day_record


# ═══════════════════════════════════════════════════════════════
#  MÉTRICAS ROLLING 30 DIAS
# ═══════════════════════════════════════════════════════════════

def get_rolling_stats(window: int = 30) -> dict:
    """
    Calcula métricas rolling dos últimos N dias.
    Retorna dict com todas as métricas e score de go-live.
    """
    history = _load_history()

    if not history:
        return {
            "days_running": 0, "total_trades": 0, "total_pnl": 0.0,
            "win_rate": 0.0, "sharpe": 0.0, "max_dd_pct": 0.0,
            "profit_factor": 0.0, "go_live_ready": False,
            "go_live_checks": {}, "daily_pnl": [],
        }

    # Últimos N dias
    recent = history[-window:]
    days_running = len(history)

    # Métricas agregadas
    total_trades = sum(d["n_trades"] for d in recent)
    total_wins = sum(d["wins"] for d in recent)
    total_losses = sum(d["losses"] for d in recent)
    daily_pnl = [d["pnl"] for d in recent]
    total_pnl = sum(daily_pnl)
    win_rate = round(total_wins / total_trades * 100, 1) if total_trades > 0 else 0.0

    # Sharpe ratio (diário → anualizado)
    pnl_arr = np.array(daily_pnl) if daily_pnl else np.array([0.0])
    sharpe = 0.0
    if len(pnl_arr) > 1 and pnl_arr.std() > 0:
        sharpe = float((pnl_arr.mean() / pnl_arr.std()) * np.sqrt(252))

    # Max drawdown
    equity = []
    running = recent[0]["balance"] if recent else 0
    for d in recent:
        running += d["pnl"]
        equity.append(running)
    eq_arr = np.array(equity) if equity else np.array([0.0])
    peak = np.maximum.accumulate(eq_arr)
    dd = ((eq_arr - peak) / np.where(peak > 0, peak, 1)) * 100
    max_dd_pct = float(dd.min()) if len(dd) > 0 else 0.0

    # Profit factor
    gross_profit = sum(p for p in daily_pnl if p > 0)
    gross_loss = abs(sum(p for p in daily_pnl if p < 0))
    profit_factor = round(gross_profit / gross_loss, 4) if gross_loss > 0 else float("inf")
    if profit_factor == float("inf"):
        profit_factor = 99.99

    # Consecutive loss days
    max_consec_loss = 0
    consec = 0
    for p in daily_pnl:
        if p < 0:
            consec += 1
            max_consec_loss = max(max_consec_loss, consec)
        else:
            consec = 0

    # Avg win / avg loss
    all_pnl_trades = []
    for d in recent:
        trades = _read_trades_for_date(
            datetime.strptime(d["date"], "%Y-%m-%d").date()
        )
        for t in trades:
            all_pnl_trades.append(float(t.get("profit_currency", 0)))

    wins_money = [p for p in all_pnl_trades if p > 0]
    losses_money = [p for p in all_pnl_trades if p < 0]
    avg_win = round(np.mean(wins_money), 2) if wins_money else 0.0
    avg_loss = round(np.mean(losses_money), 2) if losses_money else 0.0

    # Go-live checks
    c = GO_LIVE_CRITERIA
    checks = {
        "days_30":        {"pass": days_running >= c["min_days"],
                           "value": days_running, "target": c["min_days"]},
        "min_trades":     {"pass": total_trades >= c["min_trades"],
                           "value": total_trades, "target": c["min_trades"]},
        "win_rate":       {"pass": win_rate >= c["min_win_rate"],
                           "value": win_rate, "target": c["min_win_rate"]},
        "sharpe":         {"pass": sharpe >= c["min_sharpe"],
                           "value": round(sharpe, 2), "target": c["min_sharpe"]},
        "max_drawdown":   {"pass": max_dd_pct >= c["max_dd_pct"],
                           "value": round(max_dd_pct, 2), "target": c["max_dd_pct"]},
        "profit_factor":  {"pass": profit_factor >= c["min_profit_factor"],
                           "value": profit_factor, "target": c["min_profit_factor"]},
        "consec_losses":  {"pass": max_consec_loss <= c["max_consecutive_loss_days"],
                           "value": max_consec_loss,
                           "target": c["max_consecutive_loss_days"]},
    }

    go_live_ready = all(ch["pass"] for ch in checks.values())

    return {
        "days_running":       days_running,
        "window":             len(recent),
        "total_trades":       total_trades,
        "total_pnl":          round(total_pnl, 2),
        "win_rate":           win_rate,
        "sharpe":             round(sharpe, 2),
        "max_dd_pct":         round(max_dd_pct, 2),
        "profit_factor":      profit_factor,
        "avg_win":            avg_win,
        "avg_loss":           avg_loss,
        "max_consec_loss_days": max_consec_loss,
        "go_live_ready":      go_live_ready,
        "go_live_checks":     checks,
        "daily_pnl":          [round(p, 2) for p in daily_pnl],
        "equity_curve":       [round(e, 2) for e in equity],
        "start_date":         history[0]["date"] if history else None,
        "last_date":          history[-1]["date"] if history else None,
    }


# ═══════════════════════════════════════════════════════════════
#  INTEGRAÇÃO COM MAIN LOOP
# ═══════════════════════════════════════════════════════════════

_last_record_date: Optional[date] = None


def end_of_day_hook(account_balance: float, equity: float = None):
    """
    Chamado pelo main.py ao fim da sessão para registar o dia.
    Evita registos duplicados.
    """
    global _last_record_date
    today = date.today()

    if _last_record_date == today:
        return

    record_day(account_balance, equity)
    _last_record_date = today

    # Log do estado
    try:
        import src.logger as log
        stats = get_rolling_stats()
        go = "READY" if stats["go_live_ready"] else f"dia {stats['days_running']}/30"
        log.info(
            f"PAPER TRACKER: {go} | "
            f"P&L={stats['total_pnl']:+.2f} | "
            f"WR={stats['win_rate']:.1f}% | "
            f"Sharpe={stats['sharpe']:.2f} | "
            f"MaxDD={stats['max_dd_pct']:.2f}%",
            "PAPER"
        )
    except Exception:
        pass


def print_go_live_report():
    """Imprime relatório de readiness no terminal."""
    stats = get_rolling_stats()
    checks = stats.get("go_live_checks", {})

    print("\n" + "=" * 60)
    print("  PAPER TRADING — GO-LIVE READINESS REPORT")
    print("=" * 60)
    print(f"  Dias de paper: {stats['days_running']}")
    print(f"  Período:       {stats.get('start_date','?')} → {stats.get('last_date','?')}")
    print(f"  Total trades:  {stats['total_trades']}")
    print(f"  P&L total:     {stats['total_pnl']:+.2f}")
    print("-" * 60)

    for name, ch in checks.items():
        icon = "PASS" if ch["pass"] else "FAIL"
        print(f"  [{icon}] {name:20s}  {ch['value']}  (target: {ch['target']})")

    print("-" * 60)
    if stats["go_live_ready"]:
        print("  RESULTADO: PRONTO PARA LIVE")
    else:
        failed = [n for n, c in checks.items() if not c["pass"]]
        print(f"  RESULTADO: NAO PRONTO — falhou: {', '.join(failed)}")
    print("=" * 60 + "\n")


# ═══════════════════════════════════════════════════════════════
#  ENTRY POINT
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print_go_live_report()
