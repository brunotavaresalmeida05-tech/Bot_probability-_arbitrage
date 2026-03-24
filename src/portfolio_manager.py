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
# Inclui nomes ActivTrades (Usa500, Ger40, GOLD, SILVER)
PAIR_CORRELATIONS = {
    ("EURUSD", "GBPUSD"):  +0.85,
    ("EURUSD", "AUDUSD"):  +0.75,
    ("EURUSD", "NZDUSD"):  +0.72,
    ("EURUSD", "USDCHF"):  -0.90,
    ("GBPUSD", "AUDUSD"):  +0.70,
    ("USDJPY", "USDCHF"):  +0.75,
    ("USDJPY", "USDCAD"):  +0.65,
    ("AUDUSD", "NZDUSD"):  +0.92,
    # Metais
    ("GOLD",   "EURUSD"):  +0.60,
    ("GOLD",   "USDJPY"):  -0.55,
    ("GOLD",   "SILVER"):  +0.90,
    ("GOLD",   "Usa500"):  -0.40,
    # Índices
    ("Usa500", "Ger40"):   +0.80,
    ("Usa500", "UK100"):   +0.85,
    ("Ger40",  "UK100"):   +0.75,
    ("Usa500", "EURUSD"):  +0.30,
    ("Usa500", "USDJPY"):  +0.45,
    # Crypto
    ("BTCUSD", "ETHUSD"):  +0.85,
    ("BTCUSD", "SOLUSD"):  +0.80,
    ("BTCUSD", "XRPUSD"):  +0.70,
    ("ETHUSD", "SOLUSD"):  +0.75,
    ("ETHUSD", "XRPUSD"):  +0.65,
    ("SOLUSD", "XRPUSD"):  +0.60,
    ("BTCUSD", "GOLD"):    +0.30,
    ("BTCUSD", "Usa500"):  +0.50,
}

# Exposição máxima por moeda (% do saldo)
MAX_CURRENCY_EXPOSURE_PCT = 3.0
# Risco total máximo em aberto (% do saldo)
MAX_TOTAL_RISK_PCT = 6.0
# Correlação máxima entre posições novas e existentes
MAX_CORR_THRESHOLD = 0.70
# Proteção Global: fechar tudo se drawdown atingir este limite (% do saldo)
GLOBAL_DRAWDOWN_LIMIT_PCT = 5.0


def check_global_drawdown_protector(magic: int = None) -> tuple[bool, str]:
    """
    Proteção Global: Se a soma das perdas flutuantes de todas as posições
    atingir o limite (ex: -5%), o bot fecha tudo.
    Retorna: (está_em_segurança, motivo_se_não)
    """
    account = mt5c.get_account_info()
    balance = account.get("balance", 0.0)
    equity  = account.get("equity", 0.0)
    
    if balance <= 0:
        return True, "Saldo zero"
        
    drawdown_pct = ((balance - equity) / balance) * 100
    
    if drawdown_pct >= GLOBAL_DRAWDOWN_LIMIT_PCT:
        msg = f"⛔ DRAWDOWN GLOBAL ATINGIDO: {drawdown_pct:.2f}% (Limite: {GLOBAL_DRAWDOWN_LIMIT_PCT}%)"
        # Fecha todas as posições (chamando o conector)
        mt5c.close_all_positions(magic=magic)
        return False, msg
        
    return True, "ok"


def get_correlation(sym_a: str, sym_b: str) -> float:
    """Devolve correlação conhecida entre dois pares."""
    key1 = (sym_a, sym_b)
    key2 = (sym_b, sym_a)
    return PAIR_CORRELATIONS.get(key1, PAIR_CORRELATIONS.get(key2, 0.0))


def get_currency_exposure(positions: list) -> dict:
    """
    Calcula exposição por moeda nas posições abertas.
    Retorna dict: {currency: net_lots}  positivo=long, negativo=short
    Suporta FX (6 chars), índices (US500, GER40) e metais (XAUUSD).
    """
    exposure = {}

    # Mapa de índices/metais → moedas equivalentes (nomes ActivTrades)
    INDEX_MAP = {
        "Usa500": ("US500", "USD"), "US500": ("US500", "USD"),
        "US100": ("US100", "USD"),  "Ger40": ("GER40", "EUR"),
        "GER40": ("GER40", "EUR"),  "UK100": ("UK100", "GBP"),
        "GOLD": ("XAU", "USD"),     "XAUUSD": ("XAU", "USD"),
        "SILVER": ("XAG", "USD"),   "XAGUSD": ("XAG", "USD"),
        "BTCUSD": ("BTC", "USD"),   "ETHUSD": ("ETH", "USD"),
        "SOLUSD": ("SOL", "USD"),   "XRPUSD": ("XRP", "USD"),
    }

    for pos in positions:
        sym = pos.symbol
        lots = pos.volume
        direction = 1 if pos.type == 0 else -1  # 0=BUY, 1=SELL

        if sym in INDEX_MAP:
            base, quote = INDEX_MAP[sym]
        elif len(sym) >= 6:
            base = sym[:3].upper()
            quote = sym[3:6].upper()
        else:
            continue

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


def get_currency_exposure_financial(positions: list, balance: float) -> dict:
    """
    Calcula exposição por moeda em VALOR FINANCEIRO (% do saldo).
    Retorna dict: {currency: exposure_pct}
    """
    if balance <= 0: return {}
    
    lots_exposure = get_currency_exposure(positions)
    financial_exposure = {}
    
    for ccy, lots in lots_exposure.items():
        # Aproximação: assume alavancagem 100:1 e valor nominal ~100k por lote
        # Em produção, mt5c.calculate_nominal_value seria ideal
        nominal_value = abs(lots) * 100000 
        exposure_pct = (nominal_value / balance) * 100
        financial_exposure[ccy] = round(exposure_pct, 2)
        
    return financial_exposure


def has_sufficient_margin(symbol: str, lots: float, balance: float) -> bool:
    """
    Verifica se a conta tem margem livre suficiente para abrir a posição.
    """
    account = mt5c.get_account_info()
    free_margin = account.get("margin_free", 0.0)
    
    # Estimativa simples de margem necessária (baseada em alavancagem 1:100)
    # Em produção, mt5.order_check() seria usado para precisão absoluta.
    margin_required = (lots * 100000) / 100.0 # Ex: 1 lote EURUSD = 1000 EUR de margem
    
    return free_margin > (margin_required * 1.2) # 20% de buffer de segurança


def validate_execution(
    strategy_type: str,
    symbol: str,
    direction: str,
    lots: float,
    balance: float,
    magic: int = None
) -> tuple[bool, str]:
    """
    A ÚLTIMA BARREIRA antes do MetaTrader 5.
    Integra Drawdown, Correlação, Exposição e Margem.
    """
    # 1. Validar via regras de portfólio (Drawdown, Correlação, Exposição)
    can_open, reason, _ = can_open_position(symbol, direction, lots, balance, magic)
    if not can_open:
        return False, f"PORTFOLIO BLOCK: {reason}"
        
    # 2. Validar Margem
    if not has_sufficient_margin(symbol, lots, balance):
        return False, "MARGIN BLOCK: Margem livre insuficiente para esta operação"
        
    return True, "ok"


def can_open_position(
    symbol: str,
    direction: str,
    lots: float,
    balance: float,
    magic: int = None,
) -> tuple[bool, str, float]:
    """
    Verifica se pode abrir nova posição do ponto de vista do portfólio.
    """
    # 0. Check Proteção Global (Drawdown)
    safe, msg = check_global_drawdown_protector(magic)
    if not safe:
        return False, msg, 0.0

    positions = mt5c.get_open_positions(magic=magic) if magic else mt5c.get_open_positions()

    # 1. Risco total
    current_risk = get_total_risk_pct(positions, balance)
    if current_risk >= MAX_TOTAL_RISK_PCT:
        return False, f"Risco total={current_risk:.2f}% ≥ {MAX_TOTAL_RISK_PCT}%", 0.0

    # 2. Correlação (Matriz em Tempo Real)
    corr_check = get_portfolio_correlation(symbol, direction, positions)
    if corr_check["is_too_correlated"]:
        conflicts = corr_check["conflicts"]
        msg = f"Risco de Correlação: {symbol} muito ligado a " + \
              ", ".join(f"{c['symbol']}({c['effective']:.2f})" for c in conflicts[:2])
        return False, msg, 0.0

    # 3. Exposição por moeda (% do Saldo)
    exposure_pct = get_currency_exposure_financial(positions, balance)
    base = symbol[:3].upper() if len(symbol) >= 6 else symbol
    quote = symbol[3:6].upper() if len(symbol) >= 6 else "USD"
    
    for ccy in [base, quote]:
        if exposure_pct.get(ccy, 0) >= MAX_CURRENCY_EXPOSURE_PCT:
            return False, f"Exposição {ccy} ({exposure_pct[ccy]}%) atingiu o limite ({MAX_CURRENCY_EXPOSURE_PCT}%)", 0.0

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
