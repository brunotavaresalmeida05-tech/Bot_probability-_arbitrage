"""
src/backtest.py
Backtest vectorizado com dados históricos do MT5.
Corre com: python src/backtest.py
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pandas as pd
import numpy as np
from rich.console import Console
from rich.table import Table
from rich import box

import src.mt5_connector as mt5c
import src.strategy as strat
import config.settings as cfg

console = Console()


def backtest_symbol(symbol: str, bars: int = 5000) -> dict:
    df = mt5c.get_bars(symbol, cfg.TIMEFRAME, bars)
    if df is None or len(df) < 200:
        return {"symbol": symbol, "error": "dados insuficientes"}

    z_series, ma_series, atr_series, _ = strat.compute_zscore(df)
    sd_series = strat.compute_stddev(df["close"], cfg.STDDEV_PERIOD)

    trades = []
    position = None  # dict com entry info

    for i in range(len(df)):
        z     = z_series.iloc[i]
        ma    = ma_series.iloc[i]
        atr   = atr_series.iloc[i]
        sd    = sd_series.iloc[i]
        close = df["close"].iloc[i]

        if pd.isna(z) or pd.isna(ma) or pd.isna(atr):
            continue

        # Gerir posição aberta
        if position is not None:
            do_exit, reason = strat.should_exit(
                position["direction"], z, close, ma
            )
            # Também verificar SL hit
            if position["direction"] == "BUY" and close <= position["sl"]:
                do_exit, reason = True, "SL"
            elif position["direction"] == "SELL" and close >= position["sl"]:
                do_exit, reason = True, "SL"

            if do_exit:
                pnl = (close - position["entry"]) if position["direction"] == "BUY" else (position["entry"] - close)
                trades.append({
                    "i":        i,
                    "symbol":   symbol,
                    "dir":      position["direction"],
                    "entry":    position["entry"],
                    "exit":     close,
                    "sl":       position["sl"],
                    "z_entry":  position["z_entry"],
                    "z_exit":   z,
                    "pnl_raw":  pnl,
                    "reason":   reason,
                })
                position = None
            continue

        # Entrada
        signal = strat.get_signal(z, ma, close)
        if signal is None:
            continue

        sl = strat.compute_stop_loss(signal, close, ma, sd, atr)
        if sl <= 0:
            continue

        position = {
            "direction": signal,
            "entry":     close,
            "sl":        sl,
            "z_entry":   z,
        }

    if not trades:
        return {"symbol": symbol, "n_trades": 0}

    tdf = pd.DataFrame(trades)
    wins  = (tdf["pnl_raw"] > 0).sum()
    total = len(tdf)

    return {
        "symbol":    symbol,
        "n_trades":  total,
        "win_rate":  wins / total,
        "avg_pnl":   tdf["pnl_raw"].mean(),
        "total_pnl": tdf["pnl_raw"].sum(),
        "max_dd":    tdf["pnl_raw"].cumsum().sub(tdf["pnl_raw"].cumsum().cummax()).min(),
        "sl_exits":  (tdf["reason"] == "SL").sum(),
    }


def run():
    console.print("\n[bold blue]📊 Backtest — Mean Reversion Bot[/]\n")

    if not mt5c.connect():
        console.print("[red]Não foi possível ligar ao MT5[/]")
        sys.exit(1)

    results = []
    for sym in cfg.SYMBOLS:
        console.print(f"  A processar [cyan]{sym}[/]...", end=" ")
        r = backtest_symbol(sym)
        results.append(r)
        n = r.get("n_trades", 0)
        console.print(f"[green]{n} trades[/]")

    mt5c.disconnect()

    table = Table(title=f"Resultados ({cfg.TIMEFRAME})", box=box.SIMPLE_HEAVY,
                  header_style="bold magenta")
    table.add_column("Símbolo")
    table.add_column("Trades", justify="right")
    table.add_column("Win%", justify="right")
    table.add_column("Avg PnL (pts)", justify="right")
    table.add_column("Total PnL (pts)", justify="right")
    table.add_column("Max DD (pts)", justify="right")
    table.add_column("SL exits", justify="right")

    for r in results:
        if "error" in r:
            table.add_row(r["symbol"], "–", "–", "–", "–", "–", r["error"])
            continue
        n = r.get("n_trades", 0)
        if n == 0:
            table.add_row(r["symbol"], "0", "–", "–", "–", "–", "–")
            continue
        wr = r["win_rate"]
        wr_color = "green" if wr >= 0.5 else "red"
        total_color = "green" if r["total_pnl"] >= 0 else "red"
        table.add_row(
            r["symbol"],
            str(n),
            f"[{wr_color}]{wr:.1%}[/]",
            f"{r['avg_pnl']:.5f}",
            f"[{total_color}]{r['total_pnl']:.5f}[/]",
            f"{r['max_dd']:.5f}",
            str(r["sl_exits"]),
        )

    console.print("\n")
    console.print(table)
    console.print("\n[dim]Nota: PnL em pontos de preço (não em moeda — sem lot size aplicado)[/]")


if __name__ == "__main__":
    run()
