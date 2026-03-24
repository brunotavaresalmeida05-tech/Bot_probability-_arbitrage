"""
src/logger.py
Logging rico no terminal (rich) + CSV de trades.
"""

import csv
import os
from datetime import datetime
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box
import sys
import io
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config.settings import CSV_LOG_FILE, LOG_DIR

# Forçar UTF-8 no stdout para suportar emojis no Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

console = Console(force_terminal=True)

CSV_HEADERS = [
    "timestamp", "symbol", "direction", "entry_price", "exit_price",
    "sl", "z_entry", "z_exit", "atr_entry", "profit_pips", "profit_currency", "reason"
]


def setup():
    os.makedirs(LOG_DIR, exist_ok=True)
    if not os.path.exists(CSV_LOG_FILE):
        with open(CSV_LOG_FILE, "w", newline="") as f:
            csv.writer(f).writerow(CSV_HEADERS)


def _now() -> str:
    return datetime.now().strftime("%H:%M:%S")


def info(msg: str, symbol: str = ""):
    tag = f"[bold cyan]{symbol}[/]" if symbol else ""
    console.print(f"[dim]{_now()}[/]  {tag}  {msg}")


def success(msg: str, symbol: str = ""):
    tag = f"[bold cyan]{symbol}[/]" if symbol else ""
    console.print(f"[dim]{_now()}[/]  {tag}  [bold green]✔ {msg}[/]")


def warning(msg: str, symbol: str = ""):
    tag = f"[bold cyan]{symbol}[/]" if symbol else ""
    console.print(f"[dim]{_now()}[/]  {tag}  [bold yellow]⚠ {msg}[/]")


def error(msg: str, symbol: str = ""):
    tag = f"[bold cyan]{symbol}[/]" if symbol else ""
    console.print(f"[dim]{_now()}[/]  {tag}  [bold red]✘ {msg}[/]")


def trade_open(symbol: str, direction: str, lots: float,
               entry: float, sl: float, z: float, atr: float):
    color = "green" if direction == "BUY" else "red"
    arrow = "▲" if direction == "BUY" else "▼"
    console.print(
        f"[dim]{_now()}[/]  [bold cyan]{symbol}[/]  "
        f"[bold {color}]{arrow} {direction} OPEN[/]  "
        f"lots=[bold]{lots}[/]  entry=[bold]{entry}[/]  "
        f"sl=[bold]{sl:.5f}[/]  Z=[bold]{z:.3f}[/]  ATR={atr:.5f}"
    )


def trade_close(symbol: str, direction: str, entry: float, exit_price: float,
                profit: float, z_exit: float, reason: str):
    color = "green" if profit >= 0 else "red"
    emoji = "💰" if profit >= 0 else "🔴"
    console.print(
        f"[dim]{_now()}[/]  [bold cyan]{symbol}[/]  "
        f"[bold {color}]{emoji} {direction} CLOSE[/]  "
        f"entry={entry}  exit={exit_price}  "
        f"[bold {color}]P&L={profit:+.2f}[/]  "
        f"Z={z_exit:.3f}  motivo=[italic]{reason}[/]"
    )


def print_header(symbols: list, account: dict):
    info_str = (
        f"[bold]Conta:[/] {account.get('login')}  "
        f"[bold]Saldo:[/] {account.get('balance', 0):.2f} {account.get('currency', '')}  "
        f"[bold]Servidor:[/] {account.get('server', '')}"
    )
    console.print(Panel(
        f"[bold white]🤖 Mean Reversion Bot[/]\n{info_str}\n"
        f"[bold]Símbolos:[/] {', '.join(symbols)}",
        border_style="bright_blue",
        box=box.ROUNDED
    ))


def print_status_table(rows: list):
    """
    rows: lista de dicts com keys:
    symbol, z, ma, close, spread, signal, position, pnl
    """
    table = Table(box=box.SIMPLE_HEAVY, show_header=True, header_style="bold magenta")
    table.add_column("Símbolo", style="cyan", width=10)
    table.add_column("Z-score", justify="right", width=9)
    table.add_column("Close", justify="right", width=12)
    table.add_column("MA", justify="right", width=12)
    table.add_column("Spread", justify="right", width=7)
    table.add_column("Sinal", justify="center", width=8)
    table.add_column("Posição", justify="center", width=10)
    table.add_column("P&L", justify="right", width=10)

    for r in rows:
        z     = r.get("z", float("nan"))
        
        # Lógica de cor e texto para Z-score
        if z == "busy":
            z_str = "[italic yellow]busy[/]"
            z_color = "yellow"
        elif isinstance(z, (int, float)):
            z_str = f"{z:+.3f}" if z == z else "n/a"
            z_color = "green" if (not np.isnan(z) and z < -1) else ("red" if (not np.isnan(z) and z > 1) else "white")
        else:
            z_str = str(z)
            z_color = "white"

        sig   = r.get("signal", "-")
        sig_str = (
            "[bold green]▲ BUY[/]" if sig == "BUY" else
            "[bold red]▼ SELL[/]" if sig == "SELL" else
            "[dim]–[/]"
        )

        pos   = r.get("position", "–")
        pnl   = r.get("pnl", None)
        pnl_str = f"{pnl:+.2f}" if pnl is not None else "–"
        pnl_color = "green" if (pnl or 0) >= 0 else "red"

        table.add_row(
            r.get("symbol", ""),
            f"[{z_color}]{z_str}[/]",
            str(r.get("close", "")),
            str(r.get("ma", "")),
            str(r.get("spread", "")),
            sig_str,
            pos,
            f"[{pnl_color}]{pnl_str}[/]",
        )
    console.print(table)


def log_trade_csv(
    symbol: str, direction: str, entry: float, exit_price: float,
    sl: float, z_entry: float, z_exit: float, atr_entry: float,
    profit_pips: float, profit_currency: float, reason: str
):
    row = [
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        symbol, direction,
        round(entry, 6), round(exit_price, 6), round(sl, 6),
        round(z_entry, 4), round(z_exit, 4), round(atr_entry, 6),
        round(profit_pips, 1), round(profit_currency, 2),
        reason
    ]
    with open(CSV_LOG_FILE, "a", newline="") as f:
        csv.writer(f).writerow(row)
