"""
scripts/check_connection.py
Verifica ligação ao MT5 e mostra estado dos símbolos configurados.
Corre com: python scripts/check_connection.py
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import MetaTrader5 as mt5
import src.mt5_connector as mt5c
import config.settings as cfg
from rich.console import Console
from rich.table import Table
from rich import box

console = Console()

console.print("\n[bold blue]🔌 Verificação de ligação ao MT5[/]\n")

if not mt5c.connect():
    console.print("[bold red]✘ FALHA: não foi possível ligar ao MT5.[/]")
    console.print("[yellow]Certifica-te que:[/]")
    console.print("  • O MetaTrader 5 está aberto e com sessão iniciada")
    console.print("  • O caminho em MT5_PATH está correto (config/settings.py)")
    sys.exit(1)

console.print("[bold green]✔ Ligação OK[/]\n")

acc = mt5c.get_account_info()
console.print(f"  Conta:    [bold]{acc.get('login')}[/]")
console.print(f"  Saldo:    [bold]{acc.get('balance'):.2f} {acc.get('currency')}[/]")
console.print(f"  Servidor: [bold]{acc.get('server')}[/]")
console.print(f"  Equity:   [bold]{acc.get('equity'):.2f}[/]\n")

table = Table(title="Símbolos configurados", box=box.SIMPLE_HEAVY,
              header_style="bold magenta")
table.add_column("Símbolo")
table.add_column("Bid", justify="right")
table.add_column("Ask", justify="right")
table.add_column("Spread (pts)", justify="right")
table.add_column("Dígitos", justify="right")
table.add_column("Estado")

for symbol in cfg.SYMBOLS:
    info = mt5c.get_symbol_info(symbol)
    tick = mt5c.get_tick(symbol)
    if info is None or tick is None:
        table.add_row(symbol, "–", "–", "–", "–", "[red]NÃO DISPONÍVEL[/]")
        continue
    spread = mt5c.get_spread_points(symbol)
    state  = "[green]OK[/]" if info.trade_mode != 0 else "[yellow]SÓ LEITURA[/]"
    table.add_row(
        symbol,
        f"{tick.bid:.{info.digits}f}",
        f"{tick.ask:.{info.digits}f}",
        f"{spread:.1f}",
        str(info.digits),
        state,
    )

console.print(table)
mt5c.disconnect()
console.print("\n[dim]Ligação encerrada.[/]")
