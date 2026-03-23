"""
scripts/close_all.py
Fecha TODAS as posições abertas deste bot (por MAGIC_NUMBER).
Usa com cuidado!
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import src.mt5_connector as mt5c
import config.settings as cfg
from rich.console import Console

console = Console()

console.print("[bold red]⛔ Fechar todas as posições do bot[/]\n")

if not mt5c.connect():
    console.print("[red]Não foi possível ligar ao MT5[/]")
    sys.exit(1)

positions = mt5c.get_open_positions(magic=cfg.MAGIC_NUMBER)

if not positions:
    console.print("[green]Nenhuma posição aberta.[/]")
    mt5c.disconnect()
    sys.exit(0)

console.print(f"Encontradas [bold]{len(positions)}[/] posição(ões). A fechar...\n")

for pos in positions:
    result = mt5c.close_position(pos, cfg.MAGIC_NUMBER)
    if result["success"]:
        console.print(f"  [green]✔[/] {pos.symbol} ticket={pos.ticket} fechado")
    else:
        console.print(f"  [red]✘[/] {pos.symbol} ticket={pos.ticket} FALHOU: {result.get('error')}")

mt5c.disconnect()
console.print("\n[dim]Concluído.[/]")
