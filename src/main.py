"""
src/main.py  —  v6
Loop principal com: MTF + Portfolio Manager + Triangular ARB + Macro Engine
+ Daily Report + Paper Tracker 30d + Índices/Metais
"""

import time
import argparse
import sys
import os
from datetime import datetime
import pandas as pd
import numpy as np

# Garante que o Python encontra os módulos na pasta src/
root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if root_dir not in sys.path:
    sys.path.append(root_dir)

import config.settings as cfg
import src.mt5_connector as mt5c
import src.strategy as strat
import src.logger as log
import src.dashboard_server as dash
import src.arb_runner as arb_runner

# Módulos opcionais
try:
    import src.macro_engine as macro
    _MACRO = True
except ImportError:
    print("⚠️ Erro ao importar macro_engine. Filtro macro desativado.")
    _MACRO = False

try:
    import src.optimizer as optimizer
    _OPT = True
except ImportError:
    _OPT = False

try:
    import src.multi_timeframe as mtf
    _MTF = True
except ImportError:
    _MTF = False

try:
    import src.portfolio_manager as pm
    _PM = True
except ImportError:
    _PM = False

try:
    import src.triangular_arb as tri_arb
    _TRI = True
except ImportError:
    _TRI = False

try:
    import src.daily_report as daily_report
    _REPORT = True
except ImportError:
    _REPORT = False

try:
    import src.paper_tracker as paper_tracker
    _PAPER_TRACKER = True
except ImportError:
    _PAPER_TRACKER = False

# ─── Estado global ───────────────────────────────────────────
last_bar_time: dict = {}
daily_states:  dict = {}
entry_z:       dict = {}
entry_atr:     dict = {}
_bars_cache:   dict = {}
_last_status:  dict = {}   # cache de último status por símbolo
PAPER_MODE = False


def _get_all_bars():   return _bars_cache
def _get_all_prices():
    prices = {}
    for sym in cfg.ALL_SYMBOLS + cfg.ARB_EXTRA_SYMBOLS:
        tick = mt5c.get_tick(sym)
        if tick:
            prices[sym] = (tick.bid + tick.ask) / 2
    return prices


# ─── Helpers ─────────────────────────────────────────────────

def get_bars_safe(symbol, params=None):
    ma_p   = (params or {}).get("MA_PERIOD", cfg.MA_PERIOD)
    sd_p   = (params or {}).get("STDDEV_PERIOD", cfg.STDDEV_PERIOD)
    needed = max(ma_p, sd_p, cfg.ATR_PERIOD, cfg.ATR_BASE_PERIOD) + 10
    df = mt5c.get_bars(symbol, cfg.TIMEFRAME, needed)
    if df is None or len(df) < needed - 5:
        log.warning(f"Dados insuficientes ({0 if df is None else len(df)} barras)", symbol)
        return None
    return df


def is_new_bar(symbol, df):
    last = df.index[-1]
    if last_bar_time.get(symbol) == last:
        return False
    last_bar_time[symbol] = last
    return True


def get_position_obj(symbol):
    # Procura Mean Reversion (Base)
    positions = mt5c.get_open_positions(symbol, cfg.MAGIC_NUMBER)
    if positions: return positions[0]
    # Procura Arbitragem Estatística (Base + 1)
    positions = mt5c.get_open_positions(symbol, cfg.MAGIC_NUMBER + 1)
    if positions: return positions[0]
    return None


def get_daily_closed_pnl(symbol):
    deals = mt5c.get_today_deals(symbol, cfg.MAGIC_NUMBER)
    return sum(d.profit for d in deals)


# ─── Processar símbolo ────────────────────────────────────────

def process_symbol(symbol: str, account_balance: float) -> dict:
    status = {"symbol": symbol, "z": float("nan"), "close": "–",
              "ma": "–", "spread": "–", "signal": None, "position": "–", "pnl": None}

    params = optimizer.apply_best_params(symbol) if _OPT else {
        "MA_PERIOD": cfg.MA_PERIOD, "STDDEV_PERIOD": cfg.STDDEV_PERIOD,
        "Z_ENTER": cfg.Z_ENTER, "Z_EXIT": cfg.Z_EXIT, "Z_STOP": cfg.Z_STOP,
    }

    df = get_bars_safe(symbol, params)
    if df is None:
        return status

    _bars_cache[symbol] = df

    if not is_new_bar(symbol, df):
        # Reutilizar último status conhecido (Z, close, MA, spread)
        cached = _last_status.get(symbol, {})
        status["z"]      = cached.get("z", float("nan"))
        status["close"]  = cached.get("close", "–")
        status["ma"]     = cached.get("ma", "–")
        status["spread"] = cached.get("spread", "–")
        pos = get_position_obj(symbol)
        if pos:
            status["position"] = "BUY" if pos.type == 0 else "SELL"
            status["pnl"]      = pos.profit
        return status

    # Indicadores
    close   = df["close"]
    ma_s    = strat.compute_ma(close, params.get("MA_PERIOD", cfg.MA_PERIOD), cfg.MA_TYPE)
    sd_s    = strat.compute_stddev(close, params.get("STDDEV_PERIOD", cfg.STDDEV_PERIOD))
    atr_s   = strat.compute_atr(df, cfg.ATR_PERIOD)
    atr_b_s = strat.compute_atr(df, cfg.ATR_BASE_PERIOD)

    z_last        = float(((close - ma_s) / sd_s.replace(0, np.nan)).iloc[-1])
    ma_last       = float(ma_s.iloc[-1])
    atr_last      = float(atr_s.iloc[-1])
    atr_base_last = float(atr_b_s.iloc[-1])
    close_last    = float(close.iloc[-1])
    sd_last       = float(sd_s.iloc[-1])
    spread        = mt5c.get_spread_points(symbol)

    status.update({
        "z":      round(z_last, 4) if not np.isnan(z_last) else float("nan"),
        "close":  round(close_last, 5),
        "ma":     round(ma_last, 5),
        "spread": round(spread, 1),
    })
    # Guardar para uso entre candles
    _last_status[symbol] = {k: status[k] for k in ("z", "close", "ma", "spread")}

    # Macro context
    macro_score, macro_regime, macro_reasons = 0.0, "neutral", []
    lot_mult, macro_allowed = 1.0, True
    if _MACRO:
        ctx          = macro.get_macro_context(symbol)
        macro_score  = ctx.get("score", 0.0)
        macro_regime = ctx.get("regime", "neutral")
        macro_reasons = ctx.get("reason", [])[:3]
        lot_mult     = ctx.get("lot_multiplier", 1.0)
        macro_allowed = ctx.get("trade_allowed", True)

    # Multi-timeframe signal
    mtf_signal, mtf_confidence, h1_trend = None, 0.0, 0
    if _MTF and cfg.USE_MULTI_TIMEFRAME:
        mtf_result  = mtf.get_mtf_signal(symbol)
        mtf_signal  = mtf_result.get("signal")
        mtf_confidence = mtf_result.get("confidence", 0.0)
        h1_trend = mtf_result.get("h1_trend", 0)
        if mtf_signal:
            log.info(mtf.format_mtf_summary(mtf_result), symbol)

    dash.update_symbol(symbol, {
        "z":             round(z_last, 4) if not np.isnan(z_last) else None,
        "ma":            round(ma_last, 5),
        "close":         round(close_last, 5),
        "spread":        round(spread, 1),
        "atr":           round(atr_last, 6),
        "macro_score":   round(macro_score, 3),
        "macro_regime":  macro_regime,
        "macro_reasons": macro_reasons,
        "signal":        None, "position": None, "pnl": None,
    })

    if symbol not in daily_states:
        daily_states[symbol] = strat.DailyState(account_balance)
    state = daily_states[symbol]
    state.reset_if_new_day(account_balance)

    z_enter = params.get("Z_ENTER", cfg.Z_ENTER)
    z_exit  = params.get("Z_EXIT",  cfg.Z_EXIT)
    z_stop  = params.get("Z_STOP",  cfg.Z_STOP)

    # Gerir posição aberta
    pos = get_position_obj(symbol)
    if pos:
        pos_type = "BUY" if pos.type == 0 else "SELL"
        status["position"] = pos_type
        status["pnl"]      = pos.profit
        
        # Se os dados técnicos estão n/a, tentamos recuperar o que é possível (Ponte de Dados)
        if np.isnan(z_last):
            # Tenta recuperar de Mean Reversion
            val = entry_z.get(symbol)
            # Se não houver, tenta de Arbitragem (usando o dicionário do arb_runner)
            if val is None:
                val = arb_runner.arb_entry_z.get(symbol)
            
            if val is not None:
                z_last = val
                status["z"] = round(z_last, 4)
            else:
                status["z"] = "busy"

        tick = mt5c.get_tick(symbol)
        current_price = tick.bid if pos_type == "BUY" else tick.ask
        
        # Garante que Close não fica em branco se temos uma posição
        if status.get("close") == "–":
            status["close"] = round(current_price, 5)

        do_exit, reason = False, ""

        # Exit MTF
        if _MTF and cfg.USE_MULTI_TIMEFRAME:
            do_exit, reason = mtf.get_mtf_exit_signal(symbol, pos_type)

        # Exit Z-score (fallback)
        if not do_exit and not np.isnan(z_last):
            if pos_type == "BUY" and (z_last >= -z_exit or current_price >= ma_last):
                do_exit = True
                reason  = f"Z reverteu ({z_last:.3f})" if z_last >= -z_exit else "cruzou MA"
            elif pos_type == "SELL" and (z_last <= z_exit or current_price <= ma_last):
                do_exit = True
                reason  = f"Z reverteu ({z_last:.3f})" if z_last <= z_exit else "cruzou MA"

        # Exit macro adverso
        if not do_exit and macro_score <= cfg.MACRO_BLOCK_SCORE:
            do_exit = True
            reason  = f"macro adverso ({macro_score:.3f})"

        if do_exit:
            if not PAPER_MODE:
                result = mt5c.close_position(pos, cfg.MAGIC_NUMBER)
                ok = result["success"]
            else:
                ok = True

            if ok:
                pips = ((current_price - pos.price_open) if pos_type == "BUY"
                        else (pos.price_open - current_price))
                pips_scaled = pips / (mt5c.get_symbol_info(symbol).trade_tick_size or 0.00001)
                log.trade_close(symbol, pos_type, pos.price_open, current_price,
                                pos.profit, z_last, reason)
                state.record_trade_result(pos.profit)
                log.log_trade_csv(symbol, pos_type, pos.price_open, current_price,
                    pos.stop_loss, entry_z.get(pos.ticket, float("nan")),
                    z_last, entry_atr.get(pos.ticket, float("nan")),
                    pips_scaled, pos.profit, reason)
                dash.add_trade({"timestamp": datetime.now().strftime("%H:%M:%S"),
                    "symbol": symbol, "direction": pos_type,
                    "entry_price": round(pos.price_open, 6),
                    "exit_price": round(current_price, 6),
                    "profit_currency": round(pos.profit, 2), "reason": reason})
                status["position"] = "–"
                status["pnl"]      = None
            else:
                log.error(f"Falha ao fechar: {result.get('error')}", symbol)
        return status

    # Filtros
    closed_pnl = get_daily_closed_pnl(symbol)
    allowed, reason = strat.trading_allowed(symbol, state, atr_last, atr_base_last, closed_pnl)
    if not allowed:
        log.info(f"[dim]Bloqueado: {reason}[/]", symbol)
        return status

    if _MACRO and not macro_allowed:
        log.info(f"[dim]MACRO BLOCK: {macro_score:.3f} {macro_regime}[/]", symbol)
        return status

    # Sinal — combinação de Z-score, MTF e Filtro Macro
    z_signal = None
    if not np.isnan(z_last):
        if z_last <= -z_enter and close_last < ma_last:
            # Macro: só bloqueia em score muito adverso (< -0.5)
            if _MACRO and macro_score <= -0.5:
                log.info(f"[dim]BUY {symbol} bloqueado: macro={macro_score:.3f}[/]", symbol)
                return status
            z_signal = "BUY"
        elif z_last >= z_enter and close_last > ma_last:
            # Macro: só bloqueia em score muito adverso (> +0.5)
            if _MACRO and macro_score >= 0.5:
                log.info(f"[dim]SELL {symbol} bloqueado: macro={macro_score:.3f}[/]", symbol)
                return status
            z_signal = "SELL"

    # MTF confirma ou ajusta — Z-score é o sinal primário
    if _MTF and cfg.USE_MULTI_TIMEFRAME and mtf_signal:
        if z_signal == mtf_signal:
            # Ambos concordam — sinal forte, boost de lote
            signal     = z_signal
            lot_mult  *= (1.0 + mtf_confidence * 0.3)
            log.info(f"MTF+Z concordam: {signal} (conf={mtf_confidence:.2f})", symbol)
        elif z_signal and mtf_signal and z_signal != mtf_signal:
            # Discordam — usar Z mas reduzir lote (mean reversion é contrária à tendência)
            signal = z_signal
            lot_mult *= 0.7
            log.info(f"[dim]MTF({mtf_signal}) ≠ Z({z_signal}) → Z com lote reduzido[/]", symbol)
        else:
            signal = z_signal or mtf_signal
    else:
        signal = z_signal

    status["signal"] = signal
    if signal is None:
        return status

    # Portfolio check unificado (A Barreira Final)
    if _PM and cfg.USE_PORTFOLIO_MANAGER:
        sl_tmp = strat.compute_stop_loss(signal, close_last, ma_last, sd_last, atr_last)
        sl_dist_tmp = abs(close_last - sl_tmp) if sl_tmp > 0 else atr_last * 2
        risk_money_tmp = account_balance * cfg.RISK_PER_TRADE_PCT / 100.0
        base_lots = mt5c.calculate_lot_size(symbol, risk_money_tmp, sl_dist_tmp)

        is_valid, pm_reason = pm.validate_execution(
            "MEAN_REVERSION", symbol, signal, base_lots, account_balance, cfg.MAGIC_NUMBER
        )
        if not is_valid:
            log.info(f"[dim]{pm_reason}[/]", symbol)
            return status

    # Abrir posição
    sl = strat.compute_stop_loss(signal, close_last, ma_last, sd_last, atr_last)
    if sl <= 0:
        log.warning("SL inválido", symbol)
        return status

    sl_dist    = abs(close_last - sl)
    risk_money = account_balance * cfg.RISK_PER_TRADE_PCT / 100.0
    base_lots  = mt5c.calculate_lot_size(symbol, risk_money, sl_dist)

    # Aplicar multiplicadores
    lots = round(base_lots * min(lot_mult, cfg.MACRO_LOT_MAX_MULT), 2)
    info = mt5c.get_symbol_info(symbol)
    if info:
        lots = max(lots, info.volume_min)
        lots = min(lots, info.volume_max)

    if lots <= 0:
        log.warning("Lots = 0, skip", symbol)
        return status

    log.trade_open(symbol, signal, lots, close_last, sl, z_last, atr_last)
    if _MACRO and macro_score != 0:
        log.info(f"[dim]macro={macro_score:+.3f} {macro_regime} lot×{lot_mult:.2f}[/]", symbol)

    if not PAPER_MODE:
        result = mt5c.send_order(symbol, signal, lots, sl, 0.0, cfg.MAGIC_NUMBER, "MR")
        if result["success"]:
            ticket = result["ticket"]
            entry_z[symbol]   = z_last  # Agora usando o símbolo como chave
            entry_atr[ticket] = atr_last
            state.trades_today += 1
            status["position"] = signal
        else:
            log.error(f"Ordem falhou: {result.get('error')} ({result.get('retcode')})", symbol)
    else:
        log.info("[italic]PAPER: ordem simulada[/]", symbol)
        state.trades_today += 1
        status["position"] = signal

    return status


# ─── Loop principal ───────────────────────────────────────────

def run(mode: str):
    global PAPER_MODE
    PAPER_MODE = (mode == "paper")

    log.setup()
    log.info("A ligar ao MetaTrader 5...")
    if not mt5c.connect():
        log.error("Não foi possível ligar ao MT5.")
        sys.exit(1)

    # Validar quais símbolos existem no broker
    active_symbols = []
    for sym in cfg.ALL_SYMBOLS:
        info = mt5c.get_symbol_info(sym)
        if info is not None and info.trade_mode != 0:
            active_symbols.append(sym)
        else:
            log.warning(f"Símbolo {sym} não disponível no broker — removido")
    if not active_symbols:
        log.error("Nenhum símbolo disponível. Verifica config/settings.py")
        sys.exit(1)

    account = mt5c.get_account_info()
    log.print_header(active_symbols, account)

    if PAPER_MODE:
        log.warning("⚠ MODO PAPER: sem ordens reais")

    log.info(f"Loop a cada {cfg.LOOP_INTERVAL_SECONDS}s | TF: {cfg.TIMEFRAME}")
    log.info(f"Símbolos: {len(cfg.SYMBOLS)} FX + {len(cfg.INDICES_SYMBOLS)} índices + {len(cfg.METALS_SYMBOLS)} metais")
    log.info("─" * 60)

    dash_url = dash.start_server(port=8765, open_browser=True)
    dash.set_trading_allowed(True)
    dash.set_system_state("RUNNING")
    dash.start_tick_stream(active_symbols + cfg.ARB_EXTRA_SYMBOLS)
    log.success(f"Dashboard: {dash_url}", "DASH")
    log.success("Fast tick stream activo (200ms)", "DASH")

    if _OPT and cfg.OPTIMIZER_ENABLED:
        optimizer.start_optimizer_thread(active_symbols)

    if _MACRO and cfg.USE_MACRO_ENGINE:
        macro.start_macro_engine(active_symbols, _get_all_bars, _get_all_prices)
        log.success("Macro Engine iniciado (7 camadas)", "MACRO")

    if _MTF and cfg.USE_MULTI_TIMEFRAME:
        log.success("Multi-Timeframe activo (M5+H1+D1)", "MTF")

    if _PM and cfg.USE_PORTFOLIO_MANAGER:
        log.success("Portfolio Manager activo (FX + índices + metais)", "PM")

    if _TRI and cfg.TRIANGULAR_ARB_ENABLED:
        log.success("Triangular ARB activo", "TRI")

    # Relatório diário automático
    if _REPORT:
        daily_report.start_daily_report_scheduler()
        log.success("Relatório diário automático activo", "REPORT")

    # Paper tracker
    if _PAPER_TRACKER and PAPER_MODE:
        log.success("Paper Tracker 30d activo", "PAPER")

    try:
        while True:
            now = datetime.now()
            account = mt5c.get_account_info()
            balance = account.get("balance", 0.0)
            equity = account.get("equity", balance)
            dash.update_account(account)
            rows = []

            # Mean Reversion + MTF — todos os símbolos activos
            for symbol in active_symbols:
                try:
                    row = process_symbol(symbol, balance)
                    rows.append(row)
                except Exception as e:
                    log.error(f"Erro: {e}", symbol)

            log.print_status_table(rows)

            # Macro summary
            if _MACRO and cfg.USE_MACRO_ENGINE:
                for sym in active_symbols:
                    ctx = macro.get_macro_context(sym)
                    sc  = ctx.get("score", 0.0)
                    reg = ctx.get("regime", "?")
                    mul = ctx.get("lot_multiplier", 1.0)
                    c   = "green" if sc > 0.2 else ("red" if sc < -0.2 else "dim")
                    log.info(f"[{c}]{sc:+.3f} {reg} lot×{mul:.2f}[/]", f"MACRO/{sym}")

            # Arbitragem Stat (apenas pares FX)
            try:
                arb_results = arb_runner.run_arb_cycle(cfg.SYMBOLS, balance)
                active = [r for r in arb_results if r.get("arb_signal")]
                if active:
                    log.info(f"ARB sinais: {len(active)}", "ARB")
            except Exception as e:
                log.error(f"ARB erro: {e}", "ARB")

            # Arbitragem Triangular
            if _TRI and cfg.TRIANGULAR_ARB_ENABLED:
                try:
                    opps = tri_arb.run_triangular_cycle()
                    if opps:
                        log.info(f"TRIANGULAR: {len(opps)} oportunidades detectadas", "TRI")
                except Exception as e:
                    log.error(f"TRI erro: {e}", "TRI")

            # Portfolio summary
            if _PM and cfg.USE_PORTFOLIO_MANAGER:
                try:
                    summary = pm.get_portfolio_summary(cfg.MAGIC_NUMBER)
                    if summary["n_positions"] > 0:
                        log.info(
                            f"Portfólio: {summary['n_positions']} pos | "
                            f"risco={summary['total_risk_pct']:.2f}% | "
                            f"P&L={summary['total_pnl']:+.2f}",
                            "PM"
                        )
                        if summary["correlated_pairs"]:
                            for cp in summary["correlated_pairs"][:3]:
                                log.info(f"  Corr: {cp['a']} ↔ {cp['b']} ({cp['corr']:.2f})", "PM")
                except Exception as e:
                    log.error(f"PM erro: {e}", "PM")

            # Paper tracker — registar ao fim da sessão
            if _PAPER_TRACKER and PAPER_MODE:
                if now.hour == cfg.SESSION_END_HOUR and now.minute < 15:
                    paper_tracker.end_of_day_hook(balance, equity)

            log.info(f"[dim]Próxima verificação em {cfg.LOOP_INTERVAL_SECONDS}s[/]")
            time.sleep(cfg.LOOP_INTERVAL_SECONDS)

    except KeyboardInterrupt:
        log.warning("Bot parado (Ctrl+C)")
    finally:
        # Registar dia no paper tracker antes de sair
        if _PAPER_TRACKER and PAPER_MODE:
            try:
                account = mt5c.get_account_info()
                paper_tracker.end_of_day_hook(
                    account.get("balance", 0),
                    account.get("equity", 0),
                )
                paper_tracker.print_go_live_report()
            except Exception:
                pass

        # Gerar relatório diário ao fechar
        if _REPORT:
            try:
                paper_stats = None
                if _PAPER_TRACKER:
                    paper_stats = paper_tracker.get_rolling_stats()
                path = daily_report.generate_daily_report(paper_stats=paper_stats)
                log.success(f"Relatório diário: {path}", "REPORT")
            except Exception as e:
                log.error(f"Erro relatório: {e}", "REPORT")

        mt5c.disconnect()
        log.info("MT5 desligado.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["live", "paper"], default="paper")
    args = parser.parse_args()
    run(args.mode)
