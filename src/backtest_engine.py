"""
src/backtest_engine.py
Backtest completo com relatório HTML interactivo.
Métricas: equity curve, drawdown, Sharpe, profit factor, win rate, avg hold time.
Corre com: python src/backtest_engine.py
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Optional
import sys, os, json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import config.settings as cfg
import src.mt5_connector as mt5c
import src.logger as log


# ═══════════════════════════════════════════════════════════════
#  MOTOR DE BACKTEST
# ═══════════════════════════════════════════════════════════════

def _compute_indicators(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    close = df["close"]
    h, l, c = df["high"], df["low"], df["close"]
    prev_c = c.shift(1)

    ma  = close.rolling(params["MA_PERIOD"]).mean()
    sd  = close.rolling(params["STDDEV_PERIOD"]).std(ddof=0).replace(0, np.nan)
    tr  = pd.concat([h-l, (h-prev_c).abs(), (l-prev_c).abs()], axis=1).max(axis=1)
    atr = tr.rolling(params["ATR_PERIOD"]).mean()
    z   = (close - ma) / sd

    df = df.copy()
    df["ma"], df["sd"], df["atr"], df["z"] = ma, sd, atr, z
    return df


def run_backtest(
    symbol: str,
    timeframe: str = "D1",
    bars: int = 500,
    params: dict = None,
    initial_balance: float = 10000.0,
    risk_pct: float = 0.5,
) -> dict:
    """
    Backtest vectorizado completo.
    Retorna dict com todas as métricas e dados para o relatório HTML.
    """
    p = params or {
        "MA_PERIOD":     cfg.MA_PERIOD,
        "STDDEV_PERIOD": cfg.STDDEV_PERIOD,
        "ATR_PERIOD":    cfg.ATR_PERIOD,
        "Z_ENTER":       cfg.Z_ENTER,
        "Z_EXIT":        cfg.Z_EXIT,
        "Z_STOP":        cfg.Z_STOP,
        "SL_ATR_MULT":   cfg.SL_ATR_MULT,
    }

    df_raw = mt5c.get_bars(symbol, timeframe, bars + 50)
    if df_raw is None or len(df_raw) < 100:
        return {"error": f"Dados insuficientes para {symbol}"}

    df = _compute_indicators(df_raw, p)
    df = df.dropna()

    trades    = []
    position  = None
    balance   = initial_balance
    equity    = [initial_balance]
    equity_ts = [str(df.index[0])]

    for i in range(len(df)):
        row = df.iloc[i]
        z, ma, atr, close = row["z"], row["ma"], row["atr"], row["close"]
        ts = str(df.index[i])

        if pd.isna(z) or pd.isna(atr) or atr <= 0:
            continue

        # Gerir posição aberta
        if position is not None:
            ptype  = position["type"]
            entry  = position["entry"]
            sl     = position["sl"]
            entry_z = position["z_entry"]
            entry_i = position["bar_i"]

            sl_hit  = (ptype == "BUY" and close <= sl) or (ptype == "SELL" and close >= sl)
            z_exit  = (ptype == "BUY" and z >= -p["Z_EXIT"]) or (ptype == "SELL" and z <= p["Z_EXIT"])
            z_stop  = (ptype == "BUY" and z <= -p["Z_STOP"]) or (ptype == "SELL" and z >= p["Z_STOP"])
            ma_cross = (ptype == "BUY" and close >= ma) or (ptype == "SELL" and close <= ma)

            if sl_hit or z_exit or z_stop or ma_cross:
                pnl_price = (close - entry) if ptype == "BUY" else (entry - close)
                sl_dist   = abs(entry - sl)

                # Calcular P&L monetário
                sym_info = mt5c.get_symbol_info(symbol)
                if sym_info and sym_info.trade_tick_size > 0:
                    tick_size  = sym_info.trade_tick_size
                    tick_value = sym_info.trade_tick_value
                    risk_money = balance * risk_pct / 100.0
                    lots = max(
                        (risk_money / ((sl_dist / tick_size) * tick_value)),
                        sym_info.volume_min
                    ) if sl_dist > 0 else sym_info.volume_min
                    pnl_money = pnl_price / tick_size * tick_value * lots
                else:
                    pnl_money = pnl_price * 1000  # fallback

                balance += pnl_money
                hold_bars = i - entry_i

                if sl_hit:   exit_reason = "SL"
                elif z_stop: exit_reason = "Z_STOP"
                elif z_exit: exit_reason = "Z_EXIT"
                else:        exit_reason = "MA_CROSS"

                trades.append({
                    "entry_time":  position["ts"],
                    "exit_time":   ts,
                    "symbol":      symbol,
                    "type":        ptype,
                    "entry":       round(entry, 6),
                    "exit":        round(close, 6),
                    "sl":          round(sl, 6),
                    "z_entry":     round(entry_z, 4),
                    "z_exit":      round(z, 4),
                    "pnl":         round(pnl_money, 2),
                    "pnl_pct":     round(pnl_money / (balance - pnl_money) * 100, 3),
                    "hold_bars":   hold_bars,
                    "exit_reason": exit_reason,
                    "balance":     round(balance, 2),
                })
                position = None

            equity.append(round(balance, 2))
            equity_ts.append(ts)
            continue

        # Tentar entrada
        if z <= -p["Z_ENTER"] and close < ma:
            sl = close - p["SL_ATR_MULT"] * atr
            position = {"type": "BUY", "entry": close, "sl": sl,
                        "z_entry": z, "bar_i": i, "ts": ts}
        elif z >= p["Z_ENTER"] and close > ma:
            sl = close + p["SL_ATR_MULT"] * atr
            position = {"type": "SELL", "entry": close, "sl": sl,
                        "z_entry": z, "bar_i": i, "ts": ts}

        equity.append(round(balance, 2))
        equity_ts.append(ts)

    return _compute_metrics(trades, equity, equity_ts, initial_balance, symbol, timeframe, p)


def _compute_metrics(trades, equity, equity_ts, initial_balance, symbol, timeframe, params):
    if not trades:
        return {"symbol": symbol, "timeframe": timeframe, "n_trades": 0,
                "error": "Sem trades no período"}

    arr = np.array([t["pnl"] for t in trades])
    eq  = np.array(equity)

    # Equity curve metrics
    total_return  = (eq[-1] - initial_balance) / initial_balance * 100
    peak          = np.maximum.accumulate(eq)
    drawdown      = (eq - peak) / peak * 100
    max_dd        = float(drawdown.min())
    max_dd_idx    = int(np.argmin(drawdown))

    # Trade metrics
    wins      = arr[arr > 0]
    losses    = arr[arr < 0]
    win_rate  = len(wins) / len(arr) if len(arr) > 0 else 0
    avg_win   = float(wins.mean()) if len(wins) > 0 else 0
    avg_loss  = float(losses.mean()) if len(losses) > 0 else 0
    pf        = abs(wins.sum() / losses.sum()) if losses.sum() != 0 else float("inf")
    sharpe    = (arr.mean() / arr.std() * np.sqrt(252)) if arr.std() > 0 else 0
    avg_hold  = float(np.mean([t["hold_bars"] for t in trades]))
    expectancy = float(arr.mean())

    # Exit breakdown
    exit_counts = {}
    for t in trades:
        r = t["exit_reason"]
        exit_counts[r] = exit_counts.get(r, 0) + 1

    return {
        "symbol":        symbol,
        "timeframe":     timeframe,
        "params":        params,
        "n_trades":      len(trades),
        "win_rate":      round(win_rate, 4),
        "total_return":  round(total_return, 2),
        "max_dd":        round(max_dd, 2),
        "sharpe":        round(sharpe, 4),
        "profit_factor": round(pf, 4),
        "avg_win":       round(avg_win, 2),
        "avg_loss":      round(avg_loss, 2),
        "expectancy":    round(expectancy, 2),
        "avg_hold_bars": round(avg_hold, 1),
        "exit_breakdown": exit_counts,
        "equity":        equity,
        "equity_ts":     equity_ts,
        "trades":        trades,
        "initial_balance": initial_balance,
    }


# ═══════════════════════════════════════════════════════════════
#  GERADOR DE RELATÓRIO HTML
# ═══════════════════════════════════════════════════════════════

def generate_html_report(results: list, output_path: str = None) -> str:
    """
    Gera relatório HTML interactivo com Chart.js.
    results: lista de dicts de run_backtest()
    """
    if output_path is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(cfg.LOG_DIR, f"backtest_report_{ts}.html")

    os.makedirs(cfg.LOG_DIR, exist_ok=True)

    # Preparar dados para JS
    charts_data = []
    summary_rows = []

    for r in results:
        if "error" in r and r.get("n_trades", 0) == 0:
            continue

        charts_data.append({
            "symbol":    r["symbol"],
            "timeframe": r["timeframe"],
            "equity":    r.get("equity", []),
            "labels":    r.get("equity_ts", []),
        })

        # Calcular drawdown series
        eq = np.array(r.get("equity", [r["initial_balance"]]))
        pk = np.maximum.accumulate(eq)
        dd = ((eq - pk) / pk * 100).tolist()

        charts_data[-1]["drawdown"] = [round(x, 2) for x in dd]

        summary_rows.append(r)

    charts_json = json.dumps(charts_data)
    summary_json = json.dumps(summary_rows, default=str)

    html = f"""<!DOCTYPE html>
<html lang="pt">
<head>
<meta charset="UTF-8">
<title>Backtest Report — {datetime.now().strftime('%Y-%m-%d %H:%M')}</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
  :root{{--bg:#0d1117;--surf:#161b22;--brd:#30363d;--txt:#e6edf3;--mut:#8b949e;
         --grn:#3fb950;--red:#f85149;--blu:#58a6ff;--purp:#bc8cff;}}
  *{{box-sizing:border-box;margin:0;padding:0;}}
  body{{background:var(--bg);color:var(--txt);font-family:'Segoe UI',system-ui,sans-serif;
        font-size:13px;padding:24px;}}
  h1{{font-size:20px;font-weight:600;margin-bottom:8px;}}
  h2{{font-size:14px;font-weight:600;color:var(--mut);text-transform:uppercase;
      letter-spacing:.8px;margin:24px 0 12px;}}
  .cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin-bottom:24px;}}
  .card{{background:var(--surf);border:1px solid var(--brd);border-radius:8px;padding:14px;}}
  .card-label{{font-size:10px;color:var(--mut);text-transform:uppercase;letter-spacing:.8px;margin-bottom:6px;}}
  .card-value{{font-size:22px;font-weight:700;}}
  .pos{{color:var(--grn);}} .neg{{color:var(--red);}} .neu{{color:var(--blu);}}
  .chart-grid{{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:24px;}}
  .chart-box{{background:var(--surf);border:1px solid var(--brd);border-radius:8px;padding:16px;}}
  .chart-title{{font-size:11px;color:var(--mut);text-transform:uppercase;letter-spacing:.8px;margin-bottom:12px;}}
  .chart-wrap{{height:200px;}}
  table{{width:100%;border-collapse:collapse;font-size:12px;}}
  th{{text-align:left;padding:8px 10px;font-size:10px;font-weight:600;text-transform:uppercase;
      letter-spacing:.8px;color:var(--mut);border-bottom:1px solid var(--brd);}}
  td{{padding:9px 10px;border-bottom:1px solid #1e2530;}}
  tr:hover td{{background:#1c2333;}}
  .badge{{display:inline-block;padding:2px 8px;border-radius:10px;font-size:10px;font-weight:600;}}
  .b-buy{{background:#1a3a1a;color:var(--grn);}}
  .b-sell{{background:#3a1a1a;color:var(--red);}}
  .tabs{{display:flex;gap:8px;margin-bottom:16px;flex-wrap:wrap;}}
  .tab{{background:#1e2530;border:1px solid var(--brd);color:var(--mut);
        padding:6px 14px;border-radius:6px;cursor:pointer;font-size:12px;}}
  .tab.active{{background:var(--surf);color:var(--txt);border-color:#58a6ff;}}
  .sym-panel{{display:none;}} .sym-panel.active{{display:block;}}
</style>
</head>
<body>
<h1>📊 Backtest Report</h1>
<p style="color:var(--mut);margin-bottom:20px">Gerado em {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>

<div class="tabs" id="tabs"></div>
<div id="panels"></div>

<script>
const DATA    = {charts_json};
const SUMMARY = {summary_json};

function fmt(v,d=2){{return (v===null||v===undefined||isNaN(v))?'–':Number(v).toFixed(d);}}
function fmtPct(v){{
  const s=fmt(v);
  return `<span class="${{v>=0?'pos':'neg'}}">${{v>=0?'+':''}}${{s}}%</span>`;
}}

const tabs   = document.getElementById('tabs');
const panels = document.getElementById('panels');

DATA.forEach((d,i)=>{{
  const sym = d.symbol+'_'+d.timeframe;
  const r   = SUMMARY[i] || {{}};

  // Tab
  const tab = document.createElement('button');
  tab.className = 'tab'+(i===0?' active':'');
  tab.textContent = d.symbol+' '+d.timeframe;
  tab.onclick = ()=>{{
    document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));
    document.querySelectorAll('.sym-panel').forEach(p=>p.classList.remove('active'));
    tab.classList.add('active');
    document.getElementById('panel_'+i).classList.add('active');
  }};
  tabs.appendChild(tab);

  // Panel
  const panel = document.createElement('div');
  panel.className = 'sym-panel'+(i===0?' active':'');
  panel.id = 'panel_'+i;

  const wr  = ((r.win_rate||0)*100).toFixed(1);
  const pf  = r.profit_factor===Infinity?'∞':fmt(r.profit_factor);
  panel.innerHTML = `
    <div class="cards">
      <div class="card"><div class="card-label">Retorno total</div>
        <div class="card-value ${{(r.total_return||0)>=0?'pos':'neg'}}">${{fmtPct(r.total_return).replace('<span class="pos">','').replace('<span class="neg">','').replace('</span>','')}}</div></div>
      <div class="card"><div class="card-label">Trades</div>
        <div class="card-value neu">${{r.n_trades||0}}</div></div>
      <div class="card"><div class="card-label">Win Rate</div>
        <div class="card-value ${{wr>=50?'pos':'neg'}}">${{wr}}%</div></div>
      <div class="card"><div class="card-label">Sharpe</div>
        <div class="card-value ${{(r.sharpe||0)>=1?'pos':(r.sharpe||0)>=0?'neu':'neg'}}">${{fmt(r.sharpe)}}</div></div>
      <div class="card"><div class="card-label">Max Drawdown</div>
        <div class="card-value neg">${{fmt(r.max_dd)}}%</div></div>
      <div class="card"><div class="card-label">Profit Factor</div>
        <div class="card-value ${{(r.profit_factor||0)>=1.5?'pos':'neu'}}">${{pf}}</div></div>
      <div class="card"><div class="card-label">Avg Win</div>
        <div class="card-value pos">+${{fmt(r.avg_win)}}</div></div>
      <div class="card"><div class="card-label">Avg Loss</div>
        <div class="card-value neg">${{fmt(r.avg_loss)}}</div></div>
    </div>
    <div class="chart-grid">
      <div class="chart-box"><div class="chart-title">Equity Curve</div>
        <div class="chart-wrap"><canvas id="eq_${{i}}"></canvas></div></div>
      <div class="chart-box"><div class="chart-title">Drawdown (%)</div>
        <div class="chart-wrap"><canvas id="dd_${{i}}"></canvas></div></div>
    </div>
    <h2>Trades (${{r.n_trades||0}})</h2>
    <table>
      <thead><tr><th>Entrada</th><th>Saída</th><th>Dir</th><th>Entry</th>
        <th>Exit</th><th>Z entry</th><th>Hold</th><th>P&L</th><th>Motivo</th></tr></thead>
      <tbody id="trades_${{i}}"></tbody>
    </table>`;
  panels.appendChild(panel);

  // Charts
  setTimeout(()=>{{
    const opts = {{animation:false,responsive:true,maintainAspectRatio:false,
      plugins:{{legend:{{display:false}}}},
      scales:{{x:{{ticks:{{color:'#8b949e',maxTicksLimit:8,font:{{size:9}}}},grid:{{color:'#1e2530'}}}},
               y:{{ticks:{{color:'#8b949e',font:{{size:9}}}},grid:{{color:'#1e2530'}}}}}}}};

    const n = Math.min(d.labels.length, d.equity.length);
    const lbls = d.labels.slice(0,n).map(l=>l.substring(0,10));

    new Chart(document.getElementById('eq_'+i), {{type:'line',
      data:{{labels:lbls,datasets:[{{data:d.equity.slice(0,n),borderColor:'#58a6ff',
        backgroundColor:'rgba(88,166,255,.06)',borderWidth:1.5,pointRadius:0,fill:true,tension:.2}}]}},
      options:{{...opts,scales:{{...opts.scales,y:{{...opts.scales.y,position:'right'}}}}}}}});

    new Chart(document.getElementById('dd_'+i), {{type:'line',
      data:{{labels:lbls,datasets:[{{data:d.drawdown.slice(0,n),borderColor:'#f85149',
        backgroundColor:'rgba(248,81,73,.06)',borderWidth:1.5,pointRadius:0,fill:true,tension:.2}}]}},
      options:{{...opts,scales:{{...opts.scales,y:{{...opts.scales.y,position:'right'}}}}}}}});

    // Trades table
    const tbody = document.getElementById('trades_'+i);
    const trades = r.trades||[];
    tbody.innerHTML = trades.slice(0,200).map(t=>{{
      const db = t.type==='BUY'?'<span class="badge b-buy">▲ BUY</span>':'<span class="badge b-sell">▼ SELL</span>';
      const pc = t.pnl>=0?'pos':'neg';
      return `<tr><td>${{(t.entry_time||'').substring(0,16)}}</td>
        <td>${{(t.exit_time||'').substring(0,16)}}</td>
        <td>${{db}}</td><td>${{t.entry}}</td><td>${{t.exit}}</td>
        <td>${{t.z_entry}}</td><td>${{t.hold_bars}}b</td>
        <td><span class="${{pc}}">${{t.pnl>=0?'+':''}}${{t.pnl.toFixed(2)}}</span></td>
        <td style="color:#8b949e;font-size:11px">${{t.exit_reason}}</td></tr>`;
    }}).join('');
  }}, 100);
}});
</script>
</body></html>"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    return output_path


# ═══════════════════════════════════════════════════════════════
#  ENTRY POINT
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Backtest Engine")
    parser.add_argument("--symbols",    default=",".join(cfg.SYMBOLS))
    parser.add_argument("--timeframe",  default="D1")
    parser.add_argument("--bars",       type=int, default=500)
    parser.add_argument("--balance",    type=float, default=10000.0)
    parser.add_argument("--risk",       type=float, default=0.5)
    parser.add_argument("--output",     default=None)
    args = parser.parse_args()

    if not mt5c.connect():
        print("Erro: não foi possível ligar ao MT5")
        sys.exit(1)

    symbols = [s.strip() for s in args.symbols.split(",")]
    results = []

    print(f"\n📊 Backtest: {symbols} | {args.timeframe} | {args.bars} barras\n")

    for sym in symbols:
        print(f"  A processar {sym}...", end=" ")
        r = run_backtest(sym, args.timeframe, args.bars, None, args.balance, args.risk)
        results.append(r)
        if "error" not in r:
            print(f"✔ {r['n_trades']} trades | Retorno: {r['total_return']:+.1f}% | "
                  f"Sharpe: {r['sharpe']:.3f} | MaxDD: {r['max_dd']:.1f}%")
        else:
            print(f"✘ {r.get('error','')}")

    mt5c.disconnect()

    path = generate_html_report(results, args.output)
    print(f"\n✔ Relatório gerado: {path}")
    print("  Abre o ficheiro no browser para ver os gráficos.\n")
