"""
src/daily_report.py
Relatório diário automático — HTML com trades, P&L, resumo macro, equity.
Gerado automaticamente ao fim da sessão ou por trigger manual.
"""

import os
import json
import csv
import threading
from datetime import datetime, date, timedelta
from typing import Optional
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import config.settings as cfg


# ═══════════════════════════════════════════════════════════════
#  RECOLHA DE DADOS DO DIA
# ═══════════════════════════════════════════════════════════════

def _read_today_trades() -> list:
    """Lê trades de hoje do CSV."""
    today_str = date.today().strftime("%Y-%m-%d")
    trades = []
    csv_path = cfg.CSV_LOG_FILE

    if not os.path.exists(csv_path):
        return trades

    try:
        with open(csv_path, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                ts = row.get("timestamp", "")
                if ts.startswith(today_str):
                    trades.append(row)
    except Exception:
        pass

    return trades


def _compute_daily_stats(trades: list) -> dict:
    """Calcula estatísticas do dia."""
    if not trades:
        return {
            "n_trades": 0, "pnl_total": 0.0, "pnl_pips": 0.0,
            "wins": 0, "losses": 0, "win_rate": 0.0,
            "avg_win": 0.0, "avg_loss": 0.0, "best_trade": 0.0,
            "worst_trade": 0.0, "by_symbol": {}, "by_reason": {},
        }

    pnl_list = []
    pips_list = []
    by_symbol = {}
    by_reason = {}

    for t in trades:
        pnl = float(t.get("profit_currency", 0))
        pips = float(t.get("profit_pips", 0))
        sym = t.get("symbol", "?")
        reason = t.get("reason", "?")

        pnl_list.append(pnl)
        pips_list.append(pips)

        if sym not in by_symbol:
            by_symbol[sym] = {"n": 0, "pnl": 0.0, "pips": 0.0}
        by_symbol[sym]["n"] += 1
        by_symbol[sym]["pnl"] += pnl
        by_symbol[sym]["pips"] += pips

        if reason not in by_reason:
            by_reason[reason] = 0
        by_reason[reason] += 1

    wins = [p for p in pnl_list if p > 0]
    losses = [p for p in pnl_list if p < 0]

    return {
        "n_trades":    len(trades),
        "pnl_total":   round(sum(pnl_list), 2),
        "pnl_pips":    round(sum(pips_list), 1),
        "wins":        len(wins),
        "losses":      len(losses),
        "win_rate":    round(len(wins) / len(trades) * 100, 1) if trades else 0.0,
        "avg_win":     round(sum(wins) / len(wins), 2) if wins else 0.0,
        "avg_loss":    round(sum(losses) / len(losses), 2) if losses else 0.0,
        "best_trade":  round(max(pnl_list), 2) if pnl_list else 0.0,
        "worst_trade": round(min(pnl_list), 2) if pnl_list else 0.0,
        "by_symbol":   {k: {kk: round(vv, 2) for kk, vv in v.items()}
                        for k, v in by_symbol.items()},
        "by_reason":   by_reason,
    }


def _get_macro_summary() -> dict:
    """Obtém resumo macro actual de todos os símbolos."""
    summary = {}
    try:
        import src.macro_engine as macro
        for sym in cfg.SYMBOLS + cfg.INDICES_SYMBOLS + cfg.METALS_SYMBOLS:
            ctx = macro.get_macro_context(sym)
            if ctx and ctx.get("score", 0) != 0:
                summary[sym] = {
                    "score":   ctx.get("score", 0.0),
                    "regime":  ctx.get("regime", "neutral"),
                    "reasons": ctx.get("reason", [])[:3],
                }
    except Exception:
        pass
    return summary


def _get_portfolio_summary() -> dict:
    """Obtém estado do portfólio."""
    try:
        import src.portfolio_manager as pm
        return pm.get_portfolio_summary(cfg.MAGIC_NUMBER)
    except Exception:
        return {}


def _get_account_info() -> dict:
    """Obtém info da conta."""
    try:
        import src.mt5_connector as mt5c
        return mt5c.get_account_info()
    except Exception:
        return {}


# ═══════════════════════════════════════════════════════════════
#  GERADOR DE HTML
# ═══════════════════════════════════════════════════════════════

def generate_daily_report(
    output_path: str = None,
    account: dict = None,
    paper_stats: dict = None,
) -> str:
    """
    Gera relatório HTML do dia.
    paper_stats: dict com métricas rolling do paper_tracker (opcional).
    """
    today = date.today()
    today_str = today.strftime("%Y-%m-%d")

    if output_path is None:
        os.makedirs(cfg.LOG_DIR, exist_ok=True)
        output_path = os.path.join(cfg.LOG_DIR, f"daily_report_{today_str}.html")

    trades = _read_today_trades()
    stats = _compute_daily_stats(trades)
    macro = _get_macro_summary()
    global_macro_score = sum(m.get("score", 0) for m in macro.values()) / len(macro) if macro else 0.0
    global_macro_label = "Bullish" if global_macro_score > 0.1 else ("Bearish" if global_macro_score < -0.1 else "Neutral")
    global_macro_class = "pos" if global_macro_score > 0.1 else ("neg" if global_macro_score < -0.1 else "neu")

    portfolio = _get_portfolio_summary()
    account = account or _get_account_info()

    trades_json = json.dumps(trades, default=str)
    stats_json = json.dumps(stats, default=str)
    macro_json = json.dumps(macro, default=str)
    portfolio_json = json.dumps(portfolio, default=str)
    paper_json = json.dumps(paper_stats or {}, default=str)

    pnl_class = "pos" if stats["pnl_total"] >= 0 else "neg"
    pnl_sign = "+" if stats["pnl_total"] >= 0 else ""
    wr_class = "pos" if stats["win_rate"] >= 50 else "neg"

    # Trades table rows
    trade_rows = ""
    for t in trades:
        pnl = float(t.get("profit_currency", 0))
        pc = "pos" if pnl >= 0 else "neg"
        d = t.get("direction", "?")
        badge = f'<span class="badge b-buy">&#9650; {d}</span>' if d == "BUY" \
            else f'<span class="badge b-sell">&#9660; {d}</span>'
        trade_rows += f"""<tr>
            <td>{t.get('timestamp','')[-8:]}</td>
            <td>{t.get('symbol','')}</td>
            <td>{badge}</td>
            <td>{t.get('entry_price','')}</td>
            <td>{t.get('exit_price','')}</td>
            <td>{t.get('z_entry','')}</td>
            <td>{t.get('z_exit','')}</td>
            <td><span class="{pc}">{pnl_sign if pnl>=0 else ''}{pnl:.2f}</span></td>
            <td style="color:#8b949e">{t.get('reason','')}</td>
        </tr>"""

    # Macro rows
    macro_rows = ""
    for sym, m in macro.items():
        sc = m.get("score", 0)
        sc_class = "pos" if sc > 0.2 else ("neg" if sc < -0.2 else "neu")
        reasons = ", ".join(m.get("reasons", [])[:2]) or "—"
        macro_rows += f"""<tr>
            <td>{sym}</td>
            <td><span class="{sc_class}">{sc:+.3f}</span></td>
            <td>{m.get('regime','?')}</td>
            <td style="color:#8b949e;font-size:11px">{reasons}</td>
        </tr>"""

    # By-symbol rows
    sym_rows = ""
    for sym, d in stats["by_symbol"].items():
        sc = "pos" if d["pnl"] >= 0 else "neg"
        sym_rows += f"""<tr>
            <td>{sym}</td><td>{d['n']}</td>
            <td><span class="{sc}">{'+' if d['pnl']>=0 else ''}{d['pnl']:.2f}</span></td>
            <td>{d['pips']:.1f}</td>
        </tr>"""

    # Paper tracker section
    paper_section = ""
    if paper_stats:
        ps = paper_stats
        days = ps.get("days_running", 0)
        go_live = ps.get("go_live_ready", False)
        go_class = "pos" if go_live else "neg"
        go_text = "PRONTO PARA LIVE" if go_live else f"PAPER: dia {days}/30"
        paper_section = f"""
        <h2>Paper Trading — 30 Dias</h2>
        <div class="cards">
            <div class="card"><div class="card-label">Estado</div>
                <div class="card-value {go_class}">{go_text}</div></div>
            <div class="card"><div class="card-label">P&amp;L Acumulado</div>
                <div class="card-value {'pos' if ps.get('total_pnl',0)>=0 else 'neg'}">{ps.get('total_pnl',0):+.2f}</div></div>
            <div class="card"><div class="card-label">Sharpe (30d)</div>
                <div class="card-value {'pos' if ps.get('sharpe',0)>=1 else 'neu'}">{ps.get('sharpe',0):.2f}</div></div>
            <div class="card"><div class="card-label">Max Drawdown</div>
                <div class="card-value neg">{ps.get('max_dd_pct',0):.2f}%</div></div>
            <div class="card"><div class="card-label">Win Rate (30d)</div>
                <div class="card-value {'pos' if ps.get('win_rate',0)>=50 else 'neg'}">{ps.get('win_rate',0):.1f}%</div></div>
            <div class="card"><div class="card-label">Total Trades</div>
                <div class="card-value neu">{ps.get('total_trades',0)}</div></div>
        </div>
        """

    html = f"""<!DOCTYPE html>
<html lang="pt">
<head>
<meta charset="UTF-8">
<title>Relatorio Diario — {today_str}</title>
<style>
  :root{{--bg:#0d1117;--surf:#161b22;--brd:#30363d;--txt:#e6edf3;--mut:#8b949e;
         --grn:#3fb950;--red:#f85149;--blu:#58a6ff;--purp:#bc8cff;}}
  *{{box-sizing:border-box;margin:0;padding:0;}}
  body{{background:var(--bg);color:var(--txt);font-family:'Segoe UI',system-ui,sans-serif;
        font-size:13px;padding:24px;max-width:1100px;margin:0 auto;}}
  h1{{font-size:20px;font-weight:600;margin-bottom:4px;}}
  h2{{font-size:14px;font-weight:600;color:var(--mut);text-transform:uppercase;
      letter-spacing:.8px;margin:28px 0 12px;}}
  .subtitle{{color:var(--mut);margin-bottom:20px;font-size:12px;}}
  .cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-bottom:20px;}}
  .card{{background:var(--surf);border:1px solid var(--brd);border-radius:8px;padding:14px;}}
  .card-label{{font-size:10px;color:var(--mut);text-transform:uppercase;letter-spacing:.8px;margin-bottom:6px;}}
  .card-value{{font-size:20px;font-weight:700;}}
  .pos{{color:var(--grn);}} .neg{{color:var(--red);}} .neu{{color:var(--blu);}}
  table{{width:100%;border-collapse:collapse;font-size:12px;margin-bottom:20px;}}
  th{{text-align:left;padding:8px 10px;font-size:10px;font-weight:600;text-transform:uppercase;
      letter-spacing:.8px;color:var(--mut);border-bottom:1px solid var(--brd);}}
  td{{padding:8px 10px;border-bottom:1px solid #1e2530;}}
  tr:hover td{{background:#1c2333;}}
  .badge{{display:inline-block;padding:2px 8px;border-radius:10px;font-size:10px;font-weight:600;}}
  .b-buy{{background:#1a3a1a;color:var(--grn);}}
  .b-sell{{background:#3a1a1a;color:var(--red);}}
  .section{{background:var(--surf);border:1px solid var(--brd);border-radius:8px;padding:20px;margin-bottom:20px;}}
  .grid-2{{display:grid;grid-template-columns:1fr 1fr;gap:16px;}}
  @media(max-width:700px){{.grid-2{{grid-template-columns:1fr;}}}}
</style>
</head>
<body>
<h1>Relatorio Diario</h1>
<p class="subtitle">{today.strftime('%A, %d %B %Y')} &middot;
Conta: {account.get('login','')} &middot;
Saldo: {account.get('balance',0):.2f} {account.get('currency','')}</p>

<div class="cards">
    <div class="card"><div class="card-label">P&amp;L do Dia</div>
        <div class="card-value {pnl_class}">{pnl_sign}{stats['pnl_total']:.2f}</div></div>
    <div class="card"><div class="card-label">Macro Global</div>
        <div class="card-value {global_macro_class}">{global_macro_score:+.2f} ({global_macro_label})</div></div>
    <div class="card"><div class="card-label">Trades</div>
        <div class="card-value neu">{stats['n_trades']}</div></div>
    <div class="card"><div class="card-label">Win Rate</div>
        <div class="card-value {wr_class}">{stats['win_rate']:.1f}%</div></div>
    <div class="card"><div class="card-label">Wins / Losses</div>
        <div class="card-value"><span class="pos">{stats['wins']}</span> / <span class="neg">{stats['losses']}</span></div></div>
    <div class="card"><div class="card-label">Melhor Trade</div>
        <div class="card-value pos">+{stats['best_trade']:.2f}</div></div>
    <div class="card"><div class="card-label">Pior Trade</div>
        <div class="card-value neg">{stats['worst_trade']:.2f}</div></div>
</div>

{paper_section}

<div class="grid-2">
    <div class="section">
        <h2 style="margin-top:0">P&amp;L por Simbolo</h2>
        <table>
            <thead><tr><th>Simbolo</th><th>Trades</th><th>P&amp;L</th><th>Pips</th></tr></thead>
            <tbody>{sym_rows if sym_rows else '<tr><td colspan="4" style="color:var(--mut)">Sem trades hoje</td></tr>'}</tbody>
        </table>
    </div>
    <div class="section">
        <h2 style="margin-top:0">Macro Intelligence</h2>
        <table>
            <thead><tr><th>Simbolo</th><th>Score</th><th>Regime</th><th>Razoes</th></tr></thead>
            <tbody>{macro_rows if macro_rows else '<tr><td colspan="4" style="color:var(--mut)">Sem dados macro</td></tr>'}</tbody>
        </table>
    </div>
</div>

<h2>Trades do Dia ({stats['n_trades']})</h2>
<table>
    <thead><tr><th>Hora</th><th>Simbolo</th><th>Dir</th><th>Entry</th>
        <th>Exit</th><th>Z entry</th><th>Z exit</th><th>P&amp;L</th><th>Motivo</th></tr></thead>
    <tbody>{trade_rows if trade_rows else '<tr><td colspan="9" style="color:var(--mut)">Sem trades hoje</td></tr>'}</tbody>
</table>

<p style="color:var(--mut);margin-top:30px;font-size:11px;text-align:center">
    Gerado automaticamente em {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} &middot; QuantPro Bot v6
</p>
</body></html>"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    return output_path


# ═══════════════════════════════════════════════════════════════
#  SCHEDULER — gera relatório automaticamente ao fim da sessão
# ═══════════════════════════════════════════════════════════════

_report_thread = None
_last_report_date: Optional[date] = None


def start_daily_report_scheduler():
    """Lança thread que gera relatório ao fim da sessão."""
    global _report_thread

    def _loop():
        global _last_report_date
        import time
        while True:
            now = datetime.now()
            # Gera relatório 5 min após fim da sessão
            if (now.hour == cfg.SESSION_END_HOUR and now.minute >= 5
                    and _last_report_date != now.date()):
                try:
                    import src.logger as log
                    paper_stats = None
                    try:
                        import src.paper_tracker as pt
                        paper_stats = pt.get_rolling_stats()
                    except Exception:
                        pass

                    path = generate_daily_report(paper_stats=paper_stats)
                    _last_report_date = now.date()
                    log.success(f"Relatório diário: {path}", "REPORT")
                except Exception as e:
                    import src.logger as log
                    log.error(f"Erro ao gerar relatório: {e}", "REPORT")

            time.sleep(60)  # verifica a cada minuto

    _report_thread = threading.Thread(target=_loop, daemon=True, name="daily_report")
    _report_thread.start()


# ═══════════════════════════════════════════════════════════════
#  ENTRY POINT MANUAL
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import src.mt5_connector as mt5c
    import src.logger as log

    log.setup()
    if not mt5c.connect():
        print("Erro: MT5 não conectado")
        sys.exit(1)

    path = generate_daily_report()
    mt5c.disconnect()

    print(f"\n Relatório gerado: {path}")
    print("  Abre no browser para visualizar.\n")
