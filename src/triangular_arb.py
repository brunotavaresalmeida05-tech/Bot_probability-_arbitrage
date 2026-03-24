"""
src/triangular_arb.py
Arbitragem Triangular FX — 3 pernas simultâneas.

Ideia: EURUSD × USDCHF ≈ EURCHF (em equilíbrio)
Se EURUSD × USDCHF ≠ EURCHF → existe lucro possível

Fluxo:
  USD → EUR (comprar EURUSD)
  EUR → CHF (vender EURCHF)  
  CHF → USD (vender USDCHF)
  Se valor final > valor inicial + custos → executa

Nota: exige execução quase simultânea das 3 pernas.
Em CFD retail há slippage — a estratégia é mais de detecção
e alerta do que de execução automática pura.
"""

import MetaTrader5 as mt5
import numpy as np
from datetime import datetime
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import config.settings as cfg
import src.mt5_connector as mt5c
import src.logger as log


# Triângulos FX conhecidos (A, B, C) onde A×B≈C ou A/B≈C
TRIANGLES = [
    # (base, quote, cross, op_cross)
    # op_cross: "multiply" = base×quote≈cross  "divide" = base/quote≈cross
    ("EURUSD", "USDCHF", "EURCHF", "multiply"),   # EUR/USD × USD/CHF = EUR/CHF
    ("EURUSD", "USDJPY", "EURJPY", "multiply"),   # EUR/USD × USD/JPY = EUR/JPY
    ("GBPUSD", "USDCHF", "GBPCHF", "multiply"),
    ("GBPUSD", "USDJPY", "GBPJPY", "multiply"),
    ("AUDUSD", "USDJPY", "AUDJPY", "multiply"),
    ("AUDUSD", "USDCAD", "AUDCAD", "multiply"),
    ("NZDUSD", "USDJPY", "NZDJPY", "multiply"),
    ("EURUSD", "GBPUSD", "EURGBP", "divide"),     # EUR/USD / GBP/USD = EUR/GBP
    ("EURUSD", "AUDUSD", "EURAUD", "divide"),
    ("GBPUSD", "AUDUSD", "GBPAUD", "divide"),
]

MIN_PROFIT = cfg.TRIANGULAR_ARB_MIN_PROFIT if hasattr(cfg, "TRIANGULAR_ARB_MIN_PROFIT") else 0.0003


def get_prices(symbols: list) -> dict:
    """Obtém bid/ask para lista de símbolos."""
    prices = {}
    for sym in symbols:
        tick = mt5c.get_tick(sym)
        if tick:
            prices[sym] = {"bid": tick.bid, "ask": tick.ask,
                           "mid": (tick.bid + tick.ask) / 2,
                           "spread": tick.ask - tick.bid}
    return prices


def calc_triangle_profit(prices: dict, a: str, b: str, c: str, op: str) -> dict:
    """
    Calcula lucro potencial do triângulo (A, B, C).
    
    Caminho 1 (forward):  USD → A_base → C_base → USD
    Caminho 2 (reverse):  USD → C_base → A_base → USD
    
    Retorna: profit_pct, direction, costs_pct
    """
    if a not in prices or b not in prices or c not in prices:
        return {"profit": 0.0, "profit_pips": 0.0, "direction": None,
                "deviation": 0.0, "spread_cost": 0.0, "net_profit": 0.0,
                "viable": False, "synthetic": 0.0, "actual": 0.0}

    pa = prices[a]
    pb = prices[b]
    pc = prices[c]

    # Custo de spread (aproximação: 1 pip por leg)
    spread_cost = (pa["spread"] / pa["mid"] +
                   pb["spread"] / pb["mid"] +
                   pc["spread"] / pc["mid"])

    if op == "multiply":
        # Synthetic: A_mid × B_mid
        synthetic = pa["mid"] * pb["mid"]
        actual    = pc["mid"]

        # Forward: compra A (ask), compra B (ask), vende C (bid)
        synthetic_ask = pa["ask"] * pb["ask"]
        forward_pnl   = pc["bid"] - synthetic_ask
        forward_pct   = forward_pnl / synthetic_ask

        # Reverse: vende A (bid), vende B (bid), compra C (ask)
        synthetic_bid = pa["bid"] * pb["bid"]
        reverse_pnl   = synthetic_bid - pc["ask"]
        reverse_pct   = reverse_pnl / pc["ask"]

    else:  # divide
        # Synthetic: A_mid / B_mid
        synthetic = pa["mid"] / pb["mid"] if pb["mid"] > 0 else 0
        actual    = pc["mid"]

        # Forward: compra A (ask), vende B (bid), vende C (bid)
        synthetic_ask = pa["ask"] / pb["bid"] if pb["bid"] > 0 else 0
        forward_pnl   = pc["bid"] - synthetic_ask
        forward_pct   = forward_pnl / synthetic_ask if synthetic_ask > 0 else 0

        # Reverse
        synthetic_bid = pa["bid"] / pb["ask"] if pb["ask"] > 0 else 0
        reverse_pnl   = synthetic_bid - pc["ask"]
        reverse_pct   = reverse_pnl / pc["ask"] if pc["ask"] > 0 else 0

    best_pct  = max(forward_pct, reverse_pct)
    direction = "forward" if forward_pct >= reverse_pct else "reverse"
    deviation = (actual - synthetic) / synthetic if synthetic > 0 else 0

    return {
        "profit":     round(float(best_pct), 6),
        "profit_pips": round(float(best_pct) * 10000, 2),
        "direction":  direction,
        "deviation":  round(float(deviation), 6),
        "spread_cost": round(float(spread_cost), 6),
        "net_profit": round(float(best_pct - spread_cost), 6),
        "viable":     best_pct > MIN_PROFIT and best_pct > spread_cost,
        "synthetic":  round(float(synthetic), 6),
        "actual":     round(float(actual), 6),
    }


def scan_triangles() -> list:
    """
    Varre todos os triângulos e devolve oportunidades viáveis.
    Ordena por lucro potencial.
    """
    # Obter todos os símbolos necessários
    all_syms = set()
    for a, b, c, _ in TRIANGLES:
        all_syms.update([a, b, c])

    prices = get_prices(list(all_syms))
    if not prices:
        return []

    opportunities = []
    for a, b, c, op in TRIANGLES:
        result = calc_triangle_profit(prices, a, b, c, op)
        if result["net_profit"] > MIN_PROFIT:
            opportunities.append({
                "triangle":   f"{a}→{b}→{c}",
                "sym_a":      a,
                "sym_b":      b,
                "sym_c":      c,
                "op":         op,
                "direction":  result["direction"],
                "profit_pct": result["profit"],
                "profit_pips": result["profit_pips"],
                "net_profit": result["net_profit"],
                "deviation":  result["deviation"],
                "spread_cost": result["spread_cost"],
                "viable":     result["viable"],
                "prices":     {
                    a: prices[a]["mid"],
                    b: prices[b]["mid"],
                    c: prices[c]["mid"],
                }
            })

    return sorted(opportunities, key=lambda x: x["net_profit"], reverse=True)


def execute_triangle(opp: dict, account_balance: float) -> dict:
    """
    Executa as 3 pernas do triângulo.
    ATENÇÃO: execução sequencial em CFD tem risco de slippage entre pernas.
    Recomendado apenas com TRIANGULAR_ARB_PAPER=True primeiro.
    """
    if cfg.TRIANGULAR_ARB_PAPER if hasattr(cfg, "TRIANGULAR_ARB_PAPER") else True:
        log.info(
            f"TRIANGULAR PAPER: {opp['triangle']} {opp['direction']} "
            f"profit={opp['profit_pips']:.2f}pips net={opp['net_profit']*100:.4f}%",
            "TRI"
        )
        return {"success": True, "paper": True}

    # Calcular lots
    risk_money = account_balance * cfg.ARB_RISK_PCT / 100.0
    lots = 0.01  # mínimo para triangular arb

    sym_a, sym_b, sym_c = opp["sym_a"], opp["sym_b"], opp["sym_c"]
    direction = opp["direction"]
    magic = cfg.MAGIC_NUMBER + 2  # magic específico para triangular arb

    results = []

    if opp["op"] == "multiply":
        if direction == "forward":
            # Compra A, compra B, vende C
            orders = [
                (sym_a, "BUY",  lots),
                (sym_b, "BUY",  lots),
                (sym_c, "SELL", lots),
            ]
        else:
            # Vende A, vende B, compra C
            orders = [
                (sym_a, "SELL", lots),
                (sym_b, "SELL", lots),
                (sym_c, "BUY",  lots),
            ]
    else:  # divide
        if direction == "forward":
            orders = [(sym_a, "BUY", lots), (sym_b, "SELL", lots), (sym_c, "SELL", lots)]
        else:
            orders = [(sym_a, "SELL", lots), (sym_b, "BUY", lots), (sym_c, "BUY", lots)]

    for sym, direction_leg, lot in orders:
        result = mt5c.send_order(sym, direction_leg, lot, 0, 0, magic,
                                  comment=f"TRI_{opp['triangle'][:8]}")
        results.append(result)
        if not result["success"]:
            log.error(f"TRIANGULAR: falha na perna {sym} {direction_leg}: {result.get('error')}", "TRI")
            # Tentar fechar pernas já abertas
            break

    success = all(r["success"] for r in results)
    return {"success": success, "legs": results}


def run_triangular_cycle() -> list:
    """Loop principal — detecta e executa oportunidades."""
    if not getattr(cfg, "TRIANGULAR_ARB_ENABLED", False):
        return []

    opps = scan_triangles()

    if opps:
        for opp in opps[:3]:
            log.info(
                f"TRIANGULAR: {opp['triangle']} {opp['direction']} "
                f"profit={opp['profit_pips']:.2f}pips "
                f"net={opp['net_profit']*100:.4f}% "
                f"dev={opp['deviation']*100:.4f}%",
                "TRI"
            )

    return opps
