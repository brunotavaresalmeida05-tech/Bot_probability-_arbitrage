"""
src/arb_runner.py
Loop de arbitragem — usa pares qualificados por ADF + half-life.
"""

import pandas as pd
import numpy as np
from datetime import datetime
import time
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import config.settings as cfg
import src.mt5_connector as mt5c
import src.external_data as ext
import src.arb_strategy as arb
import src.logger as log

# Estado persistente
_qualified_pairs: list = []
_last_discovery: float = 0.0
DISCOVERY_INTERVAL = 3600  # redescobre a cada hora

arb_positions: dict = {}
arb_entry_z: dict = {}


def _get_all_bars(symbols: list) -> dict:
    bars = {}
    for sym in symbols:
        df = ext.get_enriched_bars(sym, cfg.TIMEFRAME, use_polygon=cfg.USE_POLYGON_DATA)
        if df is not None and len(df) > 50:
            bars[sym] = df
    return bars


def _get_all_prices(symbols: list) -> dict:
    prices = {}
    for sym in symbols:
        tick = mt5c.get_tick(sym)
        mt5_price = ((tick.bid + tick.ask) / 2) if tick else None
        if cfg.USE_POLYGON_DATA:
            info = ext.get_best_price_source(sym, mt5_price or 0)
            prices[sym] = info["best"]
        else:
            prices[sym] = mt5_price
    return prices


def run_arb_cycle(symbols: list, account_balance: float) -> list:
    global _qualified_pairs, _last_discovery

    results = []
    now = time.time()

    all_syms = list(set(symbols + cfg.ARB_EXTRA_SYMBOLS))
    bars = _get_all_bars(all_syms)
    prices = _get_all_prices(all_syms)

    if not bars:
        return results

    # Redescobrir pares qualificados (com ADF) periodicamente
    if now - _last_discovery > DISCOVERY_INTERVAL or not _qualified_pairs:
        _qualified_pairs = arb.discover_qualified_pairs(bars, cfg.ARB_MIN_CORRELATION)
        _last_discovery = now
        if _qualified_pairs:
            log.info(
                f"ARB: {len(_qualified_pairs)} pares qualificados (ADF + half-life)",
                "ARB",
            )
            for p in _qualified_pairs[:5]:
                log.info(
                    f"  {p['symbol_a']} ↔ {p['symbol_b']}  "
                    f"corr={p['correlation']:.3f}  "
                    f"ADF_p={p['adf_pvalue']:.3f}  "
                    f"HL={p['half_life']:.1f}b  "
                    f"qual={p['quality']:.3f}",
                    "ARB",
                )
        else:
            log.warning("ARB: nenhum par passou a qualificação ADF + half-life", "ARB")

    # Sinais Correlation Arb (apenas pares qualificados)
    corr_signals = []
    for pair in _qualified_pairs[: cfg.ARB_MAX_PAIRS]:
        sym_a = pair["symbol_a"]
        sym_b = pair["symbol_b"]
        if sym_a not in bars or sym_b not in bars:
            continue

        sig = arb.get_correlation_arb_signal(
            bars[sym_a], bars[sym_b], sym_a, sym_b, pair_quality=pair
        )
        if sig.get("signal_a"):
            corr_signals.append(sig)
            log.info(
                f"ARB CorrSignal: {sym_a}↔{sym_b} "
                f"Z={sig['z']:.3f} HL={sig.get('half_life','?')}b "
                f"→ {sig['signal_a']}/{sym_a} + {sig['signal_b']}/{sym_b}",
                "ARB",
            )

    # Spread arb
    spread_signals = arb.get_spread_arb_signal(prices, bars)
    for ss in spread_signals:
        stat_tag = "✓stat" if ss.get("stationary") else "✗stat"
        log.info(
            f"ARB SpreadSignal: {ss['symbol']} {ss['direction']} "
            f"Z={ss['z']:.3f} {stat_tag} ADF_p={ss.get('adf_pvalue',1):.3f}",
            "ARB",
        )

    # Macro arb
    macro_signals = {}
    if cfg.USE_FRED_DATA:
        for sym in symbols:
            if sym not in prices or sym not in bars:
                continue
            ms = arb.get_macro_arb_signal(sym, prices.get(sym, 0), bars[sym])
            macro_signals[sym] = ms
            if ms.get("signal"):
                log.info(
                    f"ARB MacroSignal: {sym} {ms['signal']} score={ms['score']:.3f}",
                    "ARB",
                )

    # Combinar e executar
    for sym in symbols:
        if sym not in bars or sym not in prices:
            continue

        corr_sig = next(
            (s for s in corr_signals if s["symbol_a"] == sym or s["symbol_b"] == sym),
            {},
        )
        macro_sig = macro_signals.get(sym, {})
        combined = arb.combine_arb_signals(corr_sig, spread_signals, macro_sig, sym)

        results.append(
            {
                "symbol": sym,
                "arb_signal": combined.get("signal"),
                "arb_score": combined.get("score", 0.0),
                "arb_reason": combined.get("reason", ""),
            }
        )

        if combined.get("signal") and cfg.ARB_TRADING_ENABLED:
            existing = mt5c.get_open_positions(sym, cfg.MAGIC_NUMBER + 1)
            if not existing:
                _open_arb_position(
                    sym,
                    combined["signal"],
                    combined["score"],
                    combined["reason"],
                    bars[sym],
                    account_balance,
                )

    _manage_arb_exits(bars, prices)
    return results


def _open_arb_position(symbol, direction, score, reason, df, balance):
    import src.strategy as strat

    atr_s = strat.compute_atr(df, cfg.ATR_PERIOD)
    atr = float(atr_s.iloc[-1]) if not atr_s.empty else 0.0
    if atr <= 0:
        return

    tick = mt5c.get_tick(symbol)
    if not tick:
        return

    entry = tick.ask if direction == "BUY" else tick.bid
    sl_dist = cfg.ARB_SL_ATR_MULT * atr
    sl = (entry - sl_dist) if direction == "BUY" else (entry + sl_dist)

    risk_money = balance * cfg.ARB_RISK_PCT / 100.0
    lots = mt5c.calculate_lot_size(symbol, risk_money, sl_dist)
    if lots <= 0:
        return

    log.trade_open(symbol, direction, lots, entry, sl, score, atr)
    log.info(f"ARB motivo: {reason[:80]}", "ARB")

    if not cfg.ARB_PAPER_MODE:
        result = mt5c.send_order(
            symbol,
            direction,
            lots,
            sl,
            0.0,
            cfg.MAGIC_NUMBER + 1,
            comment=f"ARB_{direction[:1]}",
        )
        if result["success"]:
            ticket = result["ticket"]
            arb_entry_z[symbol] = score  # Guardar Z-score de entrada usando o símbolo como chave
            log.success(f"ARB posição aberta: ticket={ticket}", symbol)
        else:
            log.error(f"ARB falhou: {result.get('error')}", symbol)
    else:
        log.info(f"ARB PAPER: {direction} {lots}L @ {entry:.5f} SL={sl:.5f}", symbol)


def _manage_arb_exits(bars, prices):
    import MetaTrader5 as mt5
    import src.strategy as strat

    positions = mt5c.get_open_positions(magic=cfg.MAGIC_NUMBER + 1)
    for pos in positions:
        sym = pos.symbol
        if sym not in bars:
            continue

        pos_type = "BUY" if pos.type == mt5.ORDER_TYPE_BUY else "SELL"
        df = bars[sym]
        z_series, _, _, _ = strat.compute_zscore(df)
        z = float(z_series.iloc[-1]) if not z_series.empty else float("nan")

        do_exit, reason = arb.arb_should_exit(pos_type, z)
        if do_exit:
            if not cfg.ARB_PAPER_MODE:
                result = mt5c.close_position(pos, cfg.MAGIC_NUMBER + 1)
                if result["success"]:
                    log.trade_close(
                        sym,
                        pos_type,
                        pos.price_open,
                        prices.get(sym, 0),
                        pos.profit,
                        z,
                        reason,
                    )
            else:
                log.info(f"ARB PAPER: fechar {pos_type} Z={z:.3f} {reason}", sym)
