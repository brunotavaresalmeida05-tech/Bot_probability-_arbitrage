"""
src/portfolio_manager.py
Gestão de portfólio: correlação entre posições abertas, risco total, exposição.

Problemas que resolve:
- Evita ter 4 posições BUY em pares correlacionados (ex: EURUSD + GBPUSD + AUDUSD)
  → na realidade é 1 posição alavancada contra o USD
- Controla exposição total em % do saldo
- Ajusta lot size com base no risco do portfólio existente
- Detecta concentração de risco por moeda
"""

import pandas as pd
import numpy as np
from typing import Optional
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import config.settings as cfg
import src.mt5_connector as mt5c


# Correlações conhecidas entre pares (sinal: +1 move juntos, -1 move opostos)
PAIR_CORRELATIONS = {
    ("EURUSD", "GBPUSD"):  +0.85,
    ("EURUSD", "AUDUSD"):  +0.75,
    ("EURUSD", "NZDUSD"):  +0.72,
    ("EURUSD", "USDCHF"):  -0.90,
    ("GBPUSD", "AUDUSD"):  +0.70,
    ("USDJPY", "USDCHF"):  +0.75,
    ("USDJPY", "USDCAD"):  +0.65,
    ("AUDUSD", "NZDUSD"):  +0.92,
    ("XAUUSD", "EURUSD"):  +0.60,
    ("XAUUSD", "USDJPY"):  -0.55,
    ("US500",  "US100"):   +0.95,
    ("US500",  "GER40"):   +0.80,
    ("US500",  "XAUUSD"):  -0.40,
}

# Exposição máxima por moeda (% do saldo)
MAX_CURRENCY_EXPOSURE_PCT = 3.0
# Risco total máximo em aberto (% do saldo)
MAX_TOTAL_RISK_PCT = 6.0
# Correlação máxima entre posições novas e existentes
MAX_CORR_THRESHOLD = 0.70


def get_correlation(sym_a: str, sym_b: str) -> float:
    """Devolve correlação conhecida entre dois pares."""
    key1 = (sym_a, sym_b)
    key2 = (sym_b, sym_a)
    return PAIR_CORRELATIONS.get(key1, PAIR_CORRELATIONS.get(key2, 0.0))


def get_currency_exposure(positions: list) -> dict:
    """
    Calcula exposição por moeda nas posições abertas.
    Retorna dict: {currency: net_lots}  positivo=long, negativo=short
    """
    exposure = {}

    for pos in positions:
        sym = pos.symbol
        if len(sym) < 6:
            continue

        base  = sym[:3].upper()
        quote = sym[3:6].upper()
        lots  = pos.volume
        direction = 1 if pos.type == 0 else -1  # 0=BUY, 1=SELL

        # Long EURUSD = long EUR, short USD
        exposure[base]  = exposure.get(base, 0.0)  + direction * lots
        exposure[quote] = exposure.get(quote, 0.0) - direction * lots

    return {k: round(v, 4) for k, v in exposure.items()}


def get_total_risk_pct(positions: list, balance: float) -> float:
    """
    Estima o risco total das posições abertas em % do saldo.
    Usa a distância actual ao SL como proxy de risco.
    """
    if balance <= 0:
        return 0.0

    total_risk = 0.0
    for pos in positions:
        if pos.sl and pos.sl > 0:
            price = pos.price_current
            sl    = pos.sl
            dist  = abs(price - sl)
            sym_info = mt5c.get_symbol_info(pos.symbol)
            if sym_info and sym_info.trade_tick_size > 0:
                risk = (dist / sym_info.trade_tick_size) * sym_info.trade_tick_value * pos.volume
                total_risk += risk

    return round(total_risk / balance * 100, 3)


def get_portfolio_correlation(new_symbol: str, new_direction: str,
                               open_positions: list) -> dict:
    """
    Calcula correlação efectiva entre nova posição e portfólio existente.
    Retorna score de correlação e lista de conflitos.
    """
    conflicts  = []
    max_corr   = 0.0

    for pos in open_positions:
        sym = pos.symbol
        pos_dir = "BUY" if pos.type == 0 else "SELL"
        corr    = get_correlation(new_symbol, sym)

        # Correlação efectiva: mesma direcção em pares correlacionados = risco acumulado
        if corr > 0 and new_direction == pos_dir:
            effective_corr = corr
        elif corr < 0 and new_direction != pos_dir:
            effective_corr = abs(corr)
        else:
            effective_corr = 0.0

        if effective_corr > 0.5:
            conflicts.append({
                "symbol":    sym,
                "direction": pos_dir,
                "corr":      round(corr, 3),
                "effective": round(effective_corr, 3),
            })
            max_corr = max(max_corr, effective_corr)

    return {
        "max_correlation": round(max_corr, 3),
        "conflicts":       conflicts,
        "is_too_correlated": max_corr >= MAX_CORR_THRESHOLD,
    }


def can_open_position(
    symbol: str,
    direction: str,
    lots: float,
    balance: float,
    magic: int = None,
) -> tuple[bool, str, float]:
    """
    Verifica se pode abrir nova posição do ponto de vista do portfólio.
    Retorna: (pode_abrir, motivo, lot_ajustado)

    Checks:
    1. Risco total não excede MAX_TOTAL_RISK_PCT
    2. Exposição por moeda não excede MAX_CURRENCY_EXPOSURE_PCT
    3. Correlação com posições existentes não excede MAX_CORR_THRESHOLD
    """
    positions = mt5c.get_open_positions(magic=magic) if magic else mt5c.get_open_positions()

    # 1. Risco total
    current_risk = get_total_risk_pct(positions, balance)
    if current_risk >= MAX_TOTAL_RISK_PCT:
        return False, f"Risco total={current_risk:.2f}% ≥ {MAX_TOTAL_RISK_PCT}%", 0.0

    # 2. Correlação
    corr_check = get_portfolio_correlation(symbol, direction, positions)
    if corr_check["is_too_correlated"]:
        conflicts = corr_check["conflicts"]
        msg = f"Alta correlação ({corr_check['max_correlation']:.2f}) com: " + \
              ", ".join(f"{c['symbol']}({c['direction']})" for c in conflicts[:3])
        # Não bloqueia, mas reduz lot
        adj_lots = round(lots * (1.0 - corr_check["max_correlation"] * 0.5), 2)
        return True, f"⚠ {msg} → lot reduzido para {adj_lots}", adj_lots

    # 3. Exposição por moeda
    if len(symbol) >= 6:
        base  = symbol[:3].upper()
        quote = symbol[3:6].upper()
        exposure = get_currency_exposure(positions)

        for ccy in [base, quote]:
            current_exp = abs(exposure.get(ccy, 0.0))
            if current_exp > MAX_CURRENCY_EXPOSURE_PCT / 100 * balance:
                return False, f"Exposição {ccy} = {current_exp:.2f} lotes já no limite", 0.0

    return True, "ok", lots


def get_portfolio_summary(magic: int = None) -> dict:
    """Resumo do portfólio actual para o dashboard."""
    positions = mt5c.get_open_positions(magic=magic) if magic else mt5c.get_open_positions()
    balance   = mt5c.get_account_info().get("balance", 1.0)

    exposure     = get_currency_exposure(positions)
    total_risk   = get_total_risk_pct(positions, balance)
    total_pnl    = sum(p.profit for p in positions)
    open_symbols = [p.symbol for p in positions]

    # Mapa de correlações entre posições abertas
    corr_pairs = []
    for i, pos_a in enumerate(positions):
        for pos_b in positions[i+1:]:
            corr = get_correlation(pos_a.symbol, pos_b.symbol)
            if abs(corr) > 0.5:
                dir_a = "BUY" if pos_a.type == 0 else "SELL"
                dir_b = "BUY" if pos_b.type == 0 else "SELL"
                corr_pairs.append({
                    "a":    f"{pos_a.symbol}({dir_a})",
                    "b":    f"{pos_b.symbol}({dir_b})",
                    "corr": round(corr, 3),
                })

    return {
        "n_positions":    len(positions),
        "total_pnl":      round(total_pnl, 2),
        "total_risk_pct": total_risk,
        "currency_exposure": exposure,
        "correlated_pairs":  corr_pairs,
        "open_symbols":      open_symbols,
    }
