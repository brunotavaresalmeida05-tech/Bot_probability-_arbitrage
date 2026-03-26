"""
src/main.py  —  v5
Loop principal com: MTF + Portfolio Manager + Triangular ARB + Macro Engine
"""

import time
import argparse
import sys
import os
import threading
from datetime import datetime
import pandas as pd
import numpy as np
from fastapi import FastAPI
from fastapi.responses import JSONResponse
import uvicorn

# FastAPI app para health checks
health_app = FastAPI()

# Variáveis globais de status
bot_status = {
    'status': 'starting',
    'start_time': datetime.now(),
    'balance': 0.0,
    'positions': 0,
    'last_update': datetime.now()
}

@health_app.get("/")
def root():
    return {"message": "Trading Bot v6 - Running on Railway"}

@health_app.get("/health")
def health():
    uptime_seconds = (datetime.now() - bot_status['start_time']).total_seconds()
    
    return JSONResponse({
        "status": bot_status['status'],
        "uptime_seconds": uptime_seconds,
        "uptime_hours": uptime_seconds / 3600,
        "balance": bot_status['balance'],
        "open_positions": bot_status['positions'],
        "last_update": bot_status['last_update'].isoformat(),
        "timestamp": datetime.now().isoformat()
    })

@health_app.get("/metrics")
def metrics():
    """Métricas para monitorização."""
    return {
        "balance": bot_status['balance'],
        "positions": bot_status['positions'],
        "uptime": (datetime.now() - bot_status['start_time']).total_seconds()
    }

def run_health_api():
    """Roda FastAPI em thread separada."""
    port = int(os.environ.get("PORT", 8765))
    uvicorn.run(
        health_app,
        host="0.0.0.0",
        port=port,
        log_level="warning"
    )

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.portfolio_allocator import PortfolioAllocator
import config.settings as cfg
import src.mt5_connector as mt5c
from src.strategy_manager import StrategyManager
from src.filters.regime_detector import RegimeDetector
from src.filters.news_filter import NewsFilter
from src.filters.correlation_filter import CorrelationFilter
from src.filters.sentiment_analyzer import SentimentAnalyzer
from src.filters.volume_filter import VolumeFilter
from src.risk.kelly_calculator import KellyCalculator
from src.risk.dynamic_stops import DynamicStops
from src.risk.portfolio_heat import PortfolioHeat
from src.risk.drawdown_protector import DrawdownProtector
from src.risk.position_manager import PositionManager
import src.strategy as strat

# Notifications
try:
    from src.notifications.telegram_bot import TelegramBot
    _TELEGRAM = True
except ImportError:
    _TELEGRAM = False

# Analytics
try:
    from src.analytics.performance_analyzer import PerformanceAnalyzer
    from src.analytics.trade_logger import TradeLogger
    _ANALYTICS = True
except ImportError:
    _ANALYTICS = False

# Data Aggregator
try:
    from src.data_sources.data_aggregator import DataAggregator
    _DATA_AGG = True
except ImportError:
    _DATA_AGG = False

# Multi-API Aggregator
try:
    from src.data_sources.multi_api_aggregator import MultiAPIAggregator
    _MULTI_API = True
except ImportError:
    _MULTI_API = False

# Forex Factory Calendar
try:
    from src.data_sources.forex_factory import ForexFactoryAggregator
    _FF_CALENDAR = True
except ImportError:
    _FF_CALENDAR = False

# Data Health Monitor
try:
    from src.monitoring.data_health_monitor import DataHealthMonitor
    from src.monitoring.data_quality_scorer import DataQualityScorer
    _HEALTH_MON = True
except ImportError:
    _HEALTH_MON = False

# Filters
regime_detector = RegimeDetector()
news_filter = NewsFilter()
correlation_filter = CorrelationFilter()
sentiment_analyzer = SentimentAnalyzer()
volume_filter = VolumeFilter()

# Risk Management
kelly = KellyCalculator(fractional_kelly=0.25)
dynamic_stops = DynamicStops()
portfolio_heat = PortfolioHeat(max_heat_pct=15.0)
dd_protector = DrawdownProtector()
position_mgr = PositionManager()
import src.logger as log
import src.dashboard_server as dash
import src.arb_runner as arb_runner

# Módulos opcionais — não bloqueiam se falharem
try:
    import src.macro_engine as macro
    _MACRO = True
except ImportError:
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

# ─── Estado global ───────────────────────────────────────────
last_bar_time: dict = {}
daily_states:  dict = {}
entry_z:       dict = {}
entry_atr:     dict = {}
_bars_cache:   dict = {}
PAPER_MODE = False
telegram = None
perf_analyzer = None
trade_logger = None
_trade_id_map: dict = {}  # ticket → trade_logger id
data_agg = None
multi_api = None
ff_calendar = None
health_monitor = None
quality_scorer = None


def _get_all_bars():   return _bars_cache
def _get_all_prices():
    prices = {}
    syms = cfg.ALL_AVAILABLE_SYMBOLS if getattr(cfg, "USE_DYNAMIC_ALLOCATION", False) else cfg.SYMBOLS
    for sym in syms + cfg.ARB_EXTRA_SYMBOLS:
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
    positions = mt5c.get_open_positions(symbol, cfg.MAGIC_NUMBER)
    return positions[0] if positions else None


def get_daily_closed_pnl(symbol):
    deals = mt5c.get_today_deals(symbol, cfg.MAGIC_NUMBER)
    return sum(d.profit for d in deals)


# ─── Processar símbolo ────────────────────────────────────────

def process_symbol(symbol: str, account_balance: float, allocator: PortfolioAllocator = None, strategy_manager: StrategyManager = None, sentiment: dict = None, dd_check: dict = None, risk_multiplier: float = 1.0) -> dict:
    status = {"symbol": symbol, "z": float("nan"), "close": "–",
              "ma": "–", "spread": "–", "signal": None, "position": "–", "pnl": None}

    # Data Quality Check
    symbol_risk_mult = 1.0
    if quality_scorer:
        quality = quality_scorer.calculate_quality_score(symbol)
        dash.update_symbol_quality(symbol, quality) # Enviar para o dashboard
        
        if quality['total_score'] < 50:
            log.warning(f"Data quality {quality['grade']} - SKIPPING", symbol)
            return status
        elif quality['total_score'] < 70:
            symbol_risk_mult = 0.75
            log.info(f"Data quality {quality['grade']} - reducing size 25%", symbol)
        
        log.info(f"Quality {quality['grade']} ({quality['total_score']:.0f}/100)", symbol)

    params = optimizer.apply_best_params(symbol) if _OPT else {
        "MA_PERIOD": cfg.MA_PERIOD, "STDDEV_PERIOD": cfg.STDDEV_PERIOD,
        "Z_ENTER": cfg.Z_ENTER, "Z_EXIT": cfg.Z_EXIT, "Z_STOP": cfg.Z_STOP,
    }

    df = get_bars_safe(symbol, params)
    if df is None:
        return status

    _bars_cache[symbol] = df

    # Indicadores
    close   = df["close"]
    ma_s    = strat.compute_ma(close, params.get("MA_PERIOD", cfg.MA_PERIOD), cfg.MA_TYPE)
    sd_s    = strat.compute_stddev(close, params.get("STDDEV_PERIOD", cfg.STDDEV_PERIOD))
    atr_s   = strat.compute_atr(df, cfg.ATR_PERIOD)
    atr_b_s = strat.compute_atr(df, cfg.ATR_BASE_PERIOD)
    
    # Adicionar ATR ao DF para o RegimeDetector
    df = df.copy()
    df['atr'] = atr_s

    # Volume check
    vol_check = volume_filter.check_volume(df)
    if not vol_check['volume_ok']:
        log.info(f"Skip - Volume baixo ({vol_check['volume_ratio']:.2f}x)", symbol)
        return status

    # Detectar regime
    regime = regime_detector.detect_regime(df)
    if regime['regime'] == 'VOLATILE_RANGE':
        log.info(f"Skip - regime {regime['regime']} (ADX={regime['adx']:.1f}, VolZ={regime['volatility_z']:.1f})", symbol)
        return status
        
    # News filter
    news_check = news_filter.is_blocked(symbol, datetime.now())
    if news_check['blocked']:
        log.info(f"Bloqueado - {news_check['event_name']} em {news_check['minutes_until']}min", symbol)
        return status

    if not is_new_bar(symbol, df):
        pos = get_position_obj(symbol)
        if pos:
            status["position"] = "BUY" if pos.type == 0 else "SELL"
            status["pnl"]      = pos.profit
            
            # Position Management: Scale Out (mesmo se não for barra nova)
            tick = mt5c.get_tick(symbol)
            if tick:
                current_price = tick.bid if pos.type == 0 else tick.ask
                scale_result = position_mgr.scale_out_on_profit(symbol, current_price)
                if scale_result['action'] == 'SCALE_OUT':
                    log.info(f"Scale out: fechando {scale_result['closed_pct']:.1f}% em lucro target {scale_result['profit_target']}%", symbol)
                    if not PAPER_MODE:
                        mt5c.close_position_partial(pos, scale_result['closed_lots'], cfg.MAGIC_NUMBER)
        return status

    # Indicadores (re-calculados para garantir atualização)
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

    # Multi-API Consensus (prioridade) ou Data Aggregator (fallback)
    _api = multi_api or data_agg
    if _api:
        min_conf = getattr(cfg, 'CONSENSUS_MIN_CONFIDENCE', 0.85)
        min_src = getattr(cfg, 'CONSENSUS_MIN_SOURCES', 2)

        consensus = _api.get_consensus_price(symbol)
        n_sources = consensus.get('sources_count', len(consensus.get('sources', {})))
        if (consensus.get('price') and
                consensus.get('confidence', 0) >= min_conf and
                n_sources >= min_src):
            close_last = consensus['price']
            status["close"] = round(close_last, 5)

        # News sentiment como filtro adicional
        agg_sentiment = _api.get_news_sentiment(symbol, hours=12)
        if agg_sentiment.get('sources_count', agg_sentiment.get('article_count', 0)) > 0:
            if sentiment is None:
                sentiment = {}
            sentiment['data_agg_score'] = agg_sentiment['score']
            sentiment['data_agg_recommendation'] = agg_sentiment['recommendation']

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
    mtf_signal, mtf_confidence = None, 0.0
    if _MTF and cfg.USE_MULTI_TIMEFRAME:
        mtf_result  = mtf.get_mtf_signal(symbol)
        mtf_signal  = mtf_result.get("signal")
        mtf_confidence = mtf_result.get("confidence", 0.0)
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

        tick = mt5c.get_tick(symbol)
        current_price = tick.bid if pos_type == "BUY" else tick.ask

        # Position Management: Scale Out
        scale_result = position_mgr.scale_out_on_profit(symbol, current_price)
        if scale_result['action'] == 'SCALE_OUT':
            log.info(f"Scale out: fechando {scale_result['closed_pct']:.1f}% em lucro target {scale_result['profit_target']}%", symbol)
            if not PAPER_MODE:
                mt5c.close_position_partial(pos, scale_result['closed_lots'], cfg.MAGIC_NUMBER)

        do_exit, reason = False, ""

        # Exit via Strategy Manager
        if cfg.USE_MULTI_STRATEGY and strategy_manager:
            multi_signal = strategy_manager.get_combined_signal(symbol, df, datetime.now())
            if multi_signal['signal'] == 'EXIT':
                do_exit = True
                reason = f"Multi-strategy EXIT ({multi_signal['strategy']})"

        # Exit MTF
        if not do_exit and _MTF and cfg.USE_MULTI_TIMEFRAME:
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
                
                # Atualizar performance no Strategy Manager
                if cfg.USE_MULTI_STRATEGY and strategy_manager:
                    # Tentar recuperar nome da estratégia via comment se possível (ou usar default)
                    strategy_name = "unknown"
                    strategy_manager.update_strategy_performance(strategy_name, {"pnl": pos.profit})

                # Telegram close alert
                if telegram and cfg.TELEGRAM_ALERTS.get('trade_closed'):
                    telegram.send_trade_close_alert({
                        'symbol': symbol, 'direction': pos_type,
                        'entry_price': pos.price_open, 'exit_price': current_price,
                        'pnl': pos.profit, 'reason': reason,
                    })

                # Trade Logger + Performance Analyzer
                if trade_logger and pos.ticket in _trade_id_map:
                    trade_logger.log_trade_close(_trade_id_map.pop(pos.ticket), {
                        'exit_price': current_price,
                        'pnl': pos.profit,
                        'exit_reason': reason,
                    })
                if perf_analyzer:
                    perf_analyzer.add_trade({
                        'pnl': pos.profit,
                        'symbol': symbol,
                        'strategy': strategy_name if strategy_name != "unknown" else "Mean Reversion",
                    })

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

    # ============================================================
    #  SIGNAL GENERATION
    # ============================================================
    signal = None
    strategy_name = "Mean Reversion"
    confidence = 1.0

    if cfg.USE_MULTI_STRATEGY and strategy_manager:
        # Multi-strategy signals
        multi_result = strategy_manager.get_combined_signal(symbol, df, datetime.now())
        
        if multi_result['signal'] in ['BUY', 'SELL']:
            signal = multi_result['signal']
            strategy_name = multi_result['strategy']
            confidence = multi_result['confidence']
            
            # Ajuste por sentimento
            if sentiment:
                adj = sentiment_analyzer.adjust_strategy(sentiment['sentiment'], strategy_name.lower().replace(" ", "_"))
                if not adj['use_strategy']:
                    log.info(f"Skip - Sentimento {sentiment['sentiment']} bloqueia {strategy_name}", symbol)
                    return status
                confidence *= adj['adjust_size']
                
            print(f"{symbol}: {signal} via {strategy_name} (conf={confidence:.2f})")
    else:
        # Usar estratégia mean reversion existente
        z_signal = None
        if not np.isnan(z_last):
            if z_last <= -z_enter and close_last < ma_last:
                z_signal = "BUY"
            elif z_last >= z_enter and close_last > ma_last:
                z_signal = "SELL"

        # MTF confirma ou gera sinal independente
        if _MTF and cfg.USE_MULTI_TIMEFRAME and mtf_signal:
            if z_signal == mtf_signal:
                signal     = z_signal
                lot_mult  *= (1.0 + mtf_confidence * 0.3)
                log.info(f"MTF+Z concordam: {signal} (conf={mtf_confidence:.2f})", symbol)
            elif z_signal and mtf_signal and z_signal != mtf_signal:
                log.info(f"[dim]MTF({mtf_signal}) ≠ Z({z_signal}) → skip[/]", symbol)
                return status
            else:
                signal = z_signal
        else:
            signal = z_signal
            
        # Ajuste por sentimento para Mean Reversion
        if signal and sentiment:
            adj = sentiment_analyzer.adjust_strategy(sentiment['sentiment'], 'mean_reversion')
            if not adj['use_strategy']:
                log.info(f"Skip - Sentimento {sentiment['sentiment']} bloqueia Mean Reversion", symbol)
                return status
            confidence *= adj['adjust_size']

    status["signal"] = signal
    if signal is None:
        return status
        
    # Correlation check
    open_pos = mt5c.get_open_positions(None, cfg.MAGIC_NUMBER)
    open_symbols = [p.symbol for p in open_pos]
    corr_check = correlation_filter.check_exposure(symbol, open_symbols)
    if not corr_check['allowed']:
        log.info(f"{symbol}: {corr_check['reason']}", symbol)
        return status

    # Forex Factory: High-impact event block
    if ff_calendar and getattr(cfg, 'USE_FOREX_FACTORY_SCRAPING', False):
        event_check = ff_calendar.is_high_impact_event_soon(
            symbol,
            minutes_before=getattr(cfg, 'FF_BLOCK_MINUTES_BEFORE', 30),
            minutes_after=getattr(cfg, 'FF_BLOCK_MINUTES_AFTER', 15),
        )
        if event_check['blocked']:
            log.info(
                f"FF Block: {event_check['event']} ({event_check['currency']}) "
                f"em {event_check['minutes_until']}min [{event_check.get('source','')}]",
                symbol,
            )
            return status

    # Multi-API: News sentiment filter
    if _api and sentiment:
        rec = sentiment.get('data_agg_recommendation')
        if rec == 'BEARISH' and signal == 'BUY':
            log.info(f"Skip BUY - sentiment bearish (score={sentiment.get('data_agg_score', 0):.2f})", symbol)
            return status
        elif rec == 'BULLISH' and signal == 'SELL':
            log.info(f"Skip SELL - sentiment bullish (score={sentiment.get('data_agg_score', 0):.2f})", symbol)
            return status

    # Multi-API: Order book filter (crypto)
    if multi_api and getattr(cfg, 'USE_ORDER_BOOK_FILTER', False) and multi_api._is_crypto(symbol):
        orderbook = multi_api.get_order_book(symbol)
        if orderbook:
            if signal == 'BUY' and orderbook['imbalance'] < -0.3:
                log.info(f"Skip BUY - order book bearish (imb={orderbook['imbalance']:.2f})", symbol)
                return status
            elif signal == 'SELL' and orderbook['imbalance'] > 0.3:
                log.info(f"Skip SELL - order book bullish (imb={orderbook['imbalance']:.2f})", symbol)
                return status

    # Abrir posição
    sl = strat.compute_stop_loss(signal, close_last, ma_last, sd_last, atr_last)
    if sl <= 0:
        log.warning("SL inválido", symbol)
        return status

    sl_dist = abs(close_last - sl)
    
    if cfg.USE_DYNAMIC_ALLOCATION and allocator:
        base_lots, risk_money = allocator.get_position_size(symbol, sl_dist, close_last)
    else:
        risk_money = account_balance * cfg.RISK_PER_TRADE_PCT / 100.0
        base_lots  = mt5c.calculate_lot_size(symbol, risk_money, sl_dist)

    if base_lots <= 0:
        log.warning("Lots = 0 (sem alocação)", symbol)
        return status

    # Aplicar multiplicadores (incluindo Drawdown Protection e Data Quality)
    risk_mult = (dd_check['risk_multiplier'] if dd_check else 1.0) * risk_multiplier * symbol_risk_mult
    lots = round(base_lots * risk_mult * min(lot_mult * confidence, cfg.MACRO_LOT_MAX_MULT), 2)
    info = mt5c.get_symbol_info(symbol)
    if info:
        lots = max(lots, info.volume_min)
        lots = min(lots, info.volume_max)

    if lots <= 0:
        log.warning(f"Lots = 0 (Risk Mult: {risk_mult:.2f}), skip", symbol)
        return status

    log.trade_open(symbol, signal, lots, close_last, sl, z_last, atr_last)
    if strategy_name != "Mean Reversion":
        log.info(f"Estratégia: {strategy_name} | Confiança: {confidence:.2f} | Risk Mult: {risk_mult:.2f}", symbol)

    if not PAPER_MODE:
        comment = f"MR_{strategy_name[:5]}"
        result = mt5c.send_order(symbol, signal, lots, sl, 0.0, cfg.MAGIC_NUMBER, comment)
        if result["success"]:
            ticket = result["ticket"]
            entry_z[ticket]   = z_last
            entry_atr[ticket] = atr_last
            state.trades_today += 1
            status["position"] = signal

            # Registrar no PositionManager
            position_mgr.open_position(symbol, lots, result['price'], signal)

            # Telegram alert
            if telegram and cfg.TELEGRAM_ALERTS.get('trade_opened'):
                telegram.send_trade_alert({
                    'symbol': symbol, 'direction': signal,
                    'size': lots, 'entry_price': result['price'],
                    'stop_loss': sl, 'strategy': strategy_name,
                    'risk_money': risk_money,
                })

            # Trade Logger
            if trade_logger:
                db_id = trade_logger.log_trade_open({
                    'symbol': symbol, 'strategy': strategy_name,
                    'direction': signal, 'lot_size': lots,
                    'entry_price': result['price'], 'stop_loss': sl,
                })
                _trade_id_map[ticket] = db_id
        else:
            log.error(f"Ordem falhou: {result.get('error')} ({result.get('retcode')})", symbol)
    else:
        log.info("[italic]PAPER: ordem simulada[/]", symbol)
        state.trades_today += 1
        status["position"] = signal
        # Simular registro no PositionManager
        position_mgr.open_position(symbol, lots, close_last, signal)

    return status


# ─── Loop principal ───────────────────────────────────────────

def run(mode: str):
    global PAPER_MODE
    PAPER_MODE = (mode == "paper")

    # Iniciar health API em background
    health_thread = threading.Thread(target=run_health_api, daemon=True)
    health_thread.start()
    
    # Atualizar status
    bot_status['status'] = 'initializing'

    log.setup()
    log.info("A ligar ao MetaTrader 5...")
    if not mt5c.connect():
        log.error("Não foi possível ligar ao MT5.")
        sys.exit(1)

    account = mt5c.get_account_info()
    balance = account.get("balance", 0.0)

    # ============================================================
    #  INICIALIZAR PORTFOLIO ALLOCATOR
    # ============================================================
    symbols_to_trade = cfg.SYMBOLS
    allocator = None

    if getattr(cfg, "USE_DYNAMIC_ALLOCATION", False):
        log.info("🚀 SISTEMA DE PORTFOLIO ALLOCATION DINÂMICO")
        allocator = PortfolioAllocator(
            total_capital=balance,
            max_total_risk_pct=cfg.MAX_TOTAL_RISK_PCT,
            min_sharpe_threshold=cfg.MIN_SHARPE_THRESHOLD,
            rebalance_interval_hours=cfg.REBALANCE_INTERVAL_HOURS
        )
        allocator.register_backtest_results(cfg.ASSET_METRICS)
        allocator.rebalance(force=True)
        
        log.info("📊 ALOCAÇÃO INICIAL:")
        print(allocator.get_allocation_report().to_string(index=False))
        
        symbols_to_trade = cfg.ALL_AVAILABLE_SYMBOLS
    
    # ============================================================
    #  STRATEGY MANAGER
    # ============================================================
    if cfg.USE_MULTI_STRATEGY:
        print("\n🎯 Carregando estratégias...")
        strategy_manager = StrategyManager()
        
        # Mostrar alocação
        allocation = strategy_manager.get_strategy_allocation(balance)
        log.info("💰 ALOCAÇÃO POR ESTRATÉGIA:", "STRAT")
        for name, amount in allocation.items():
            weight = (amount / balance) * 100
            print(f"  {name:20s}: €{amount:8.2f} ({weight:5.1f}%)")
    else:
        strategy_manager = None

    log.print_header(symbols_to_trade, account)

    if PAPER_MODE:
        log.warning("⚠ MODO PAPER: sem ordens reais")

    log.info(f"Loop a cada {cfg.LOOP_INTERVAL_SECONDS}s | TF: {cfg.TIMEFRAME}")
    log.info("─" * 60)

    dash_url = dash.start_server(port=8765, open_browser=True)
    dash.set_trading_allowed(True)
    dash.set_system_state("RUNNING")
    
    # Tick stream com todos os símbolos ativos
    all_syms = list(set(symbols_to_trade + cfg.ARB_EXTRA_SYMBOLS))
    dash.start_tick_stream(all_syms)
    
    log.success(f"Dashboard: {dash_url}", "DASH")
    log.success("Fast tick stream activo (200ms)", "DASH")

    # Telegram
    global telegram
    if _TELEGRAM and getattr(cfg, 'TELEGRAM_ENABLED', False):
        telegram = TelegramBot(cfg.TELEGRAM_BOT_TOKEN, cfg.TELEGRAM_CHAT_ID)
        telegram.send_message("🤖 *Bot Started*\nMode: " + mode.upper())
        log.success("Telegram notifications activas", "TG")
    else:
        telegram = None

    # Analytics
    global perf_analyzer, trade_logger
    if _ANALYTICS:
        perf_analyzer = PerformanceAnalyzer()
        trade_logger = TradeLogger('data/trades.db')
        log.success("Analytics + Trade Logger activos", "ANALYTICS")

    # Data Aggregator
    global data_agg
    if _DATA_AGG and getattr(cfg, 'USE_DATA_AGGREGATOR', False):
        data_agg = DataAggregator({
            'alpha_vantage_key': getattr(cfg, 'ALPHA_VANTAGE_KEY', ''),
            'polygon_key': getattr(cfg, 'POLYGON_KEY', ''),
            'newsapi_key': getattr(cfg, 'NEWSAPI_KEY', ''),
            'finnhub_key': getattr(cfg, 'FINNHUB_KEY', ''),
            'fmp_key': getattr(cfg, 'FMP_KEY', ''),
        })
        log.success("Data Aggregator activo (multi-source)", "DATA")

    # Multi-API Aggregator
    global multi_api
    if _MULTI_API and getattr(cfg, 'USE_MULTI_API_CONSENSUS', False):
        multi_api = MultiAPIAggregator({
            'fred_key': getattr(cfg, 'FRED_API_KEY', ''),
            'polygon_key': getattr(cfg, 'POLYGON_KEY', ''),
            'alpha_vantage_key': getattr(cfg, 'ALPHA_VANTAGE_KEY', ''),
            'twelve_data_key': getattr(cfg, 'TWELVE_DATA_KEY', ''),
            'fixer_key': getattr(cfg, 'FIXER_KEY', ''),
            'eodhd_key': getattr(cfg, 'EODHD_KEY', ''),
            'newsapi_key': getattr(cfg, 'NEWSAPI_KEY', ''),
            'finnhub_key': getattr(cfg, 'FINNHUB_KEY', ''),
            'marketaux_key': getattr(cfg, 'MARKETAUX_KEY', ''),
            'currents_key': getattr(cfg, 'CURRENTS_KEY', ''),
            'mediastack_key': getattr(cfg, 'MEDIASTACK_KEY', ''),
            'cryptopanic_key': getattr(cfg, 'CRYPTOPANIC_KEY', ''),
            'binance_key': getattr(cfg, 'BINANCE_API_KEY', ''),
            'coingecko_key': getattr(cfg, 'COINGECKO_KEY', ''),
            'etherscan_key': getattr(cfg, 'ETHERSCAN_KEY', ''),
        })
        log.success("Multi-API Consensus activo (15 APIs)", "MAPI")

    # Forex Factory Calendar
    global ff_calendar
    if _FF_CALENDAR and getattr(cfg, 'USE_FOREX_FACTORY_SCRAPING', False):
        ff_calendar = ForexFactoryAggregator({
            'finnhub_key': getattr(cfg, 'FINNHUB_KEY', ''),
            'trading_economics_key': getattr(cfg, 'TRADING_ECONOMICS_KEY', ''),
        })
        log.success("Forex Factory Calendar activo (FF + Finnhub + TE)", "FF")

    # Data Health Monitor
    global health_monitor, quality_scorer
    if _HEALTH_MON and multi_api:
        health_monitor = DataHealthMonitor(multi_api)
        quality_scorer = DataQualityScorer(multi_api, health_monitor)
        log.success("Data Quality Scorer activo", "HEALTH")
    elif _HEALTH_MON and data_agg:
        # Fallback para DataAggregator se multi_api não disponível
        health_monitor = DataHealthMonitor(data_agg)
        quality_scorer = DataQualityScorer(data_agg, health_monitor)
        log.success("Data Quality Scorer activo (Aggregator fallback)", "HEALTH")

    if _OPT and cfg.OPTIMIZER_ENABLED:
        optimizer.start_optimizer_thread(symbols_to_trade)

    if _MACRO and cfg.USE_MACRO_ENGINE:
        macro.start_macro_engine(symbols_to_trade, _get_all_bars, _get_all_prices)
        log.success("Macro Engine iniciado (7 camadas)", "MACRO")

    if _MTF and cfg.USE_MULTI_TIMEFRAME:
        log.success("Multi-Timeframe activo (M5+H1+D1)", "MTF")

    if _PM and cfg.USE_PORTFOLIO_MANAGER:
        log.success("Portfolio Manager activo", "PM")

    if _TRI and cfg.TRIANGULAR_ARB_ENABLED:
        log.success("Triangular ARB activo", "TRI")

    try:
        while True:
            account = mt5c.get_account_info()
            balance = account.get("balance", 0.0)
            equity = account.get("equity", balance)
            dash.update_account(account)

            # Railway Health Status Update
            open_pos = mt5c.get_open_positions(None, cfg.MAGIC_NUMBER)
            bot_status['balance'] = balance
            bot_status['positions'] = len(open_pos) if open_pos else 0
            bot_status['last_update'] = datetime.now()
            bot_status['status'] = 'running'

            # Data Quality Scorer - Global Health
            risk_multiplier = 1.0
            if quality_scorer:
                system_health = quality_scorer.get_overall_system_health()
                dash.update_system_health(system_health) # Enviar para o dashboard
                
                if system_health['status'] == 'CRITICAL':
                    log.error(f"⚠️  SYSTEM CRITICAL - Data quality {system_health['overall_score']:.1f}")
                    risk_multiplier *= 0.5
                elif system_health['status'] == 'DEGRADED':
                    log.warning(f"⚠️  SYSTEM DEGRADED - Data quality {system_health['overall_score']:.1f}")
                    risk_multiplier *= 0.75

            # Analytics: equity tracking
            if perf_analyzer:
                perf_analyzer.add_equity_point(equity)
            if trade_logger:
                trade_logger.log_equity_snapshot({
                    'balance': balance,
                    'equity': equity,
                    'margin_used': account.get('margin'),
                    'free_margin': account.get('margin_free'),
                    'drawdown_pct': 0,
                })

            # Atualizar allocator se necessário
            if allocator:
                allocator.update_capital(balance)
                if allocator.rebalance():
                    log.info("🔄 Portfolio rebalanceado!", "ALLOC")
                    print(allocator.get_allocation_report()[["Symbol", "Sharpe", "Risk %", "Risk €"]].to_string(index=False))

            # Drawdown Protection
            dd_check = dd_protector.check_drawdown(balance)
            if dd_check['action'] == 'STOP':
                log.warning(f"⚠️  TRADING STOPPED - Modo: {dd_check['mode']} | DD Diário: {dd_check['daily_dd_pct']:.2f}%")
                if telegram and cfg.TELEGRAM_ALERTS.get('drawdown_warning'):
                    telegram.send_drawdown_warning(dd_check.get('peak_dd_pct', dd_check['daily_dd_pct']))
                time.sleep(60)
                continue
            elif dd_check.get('mode') == 'REDUCED':
                if telegram and cfg.TELEGRAM_ALERTS.get('drawdown_warning'):
                    telegram.send_drawdown_warning(dd_check.get('peak_dd_pct', dd_check.get('daily_dd_pct', 0)))

            rows = []

            # Mean Reversion + MTF + Multi-Strategy
            for symbol in symbols_to_trade:
                try:
                    row = process_symbol(symbol, balance, allocator, strategy_manager, dd_check=dd_check, risk_multiplier=risk_multiplier)
                    rows.append(row)
                except Exception as e:
                    log.error(f"Erro: {e}", symbol)

            log.print_status_table(rows)

            # Macro summary
            if _MACRO and cfg.USE_MACRO_ENGINE:
                for sym in symbols_to_trade:
                    ctx = macro.get_macro_context(sym)
                    sc  = ctx.get("score", 0.0)
                    reg = ctx.get("regime", "?")
                    mul = ctx.get("lot_multiplier", 1.0)
                    c   = "green" if sc > 0.2 else ("red" if sc < -0.2 else "dim")
                    log.info(f"[{c}]{sc:+.3f} {reg} lot×{mul:.2f}[/]", f"MACRO/{sym}")

            # Arbitragem Stat
            try:
                arb_results = arb_runner.run_arb_cycle(symbols_to_trade, balance)
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

            # Data Health Monitor (a cada 5 min)
            if health_monitor:
                import time as _t
                if not hasattr(run, '_last_health_check'):
                    run._last_health_check = 0
                if _t.time() - run._last_health_check > 300:
                    try:
                        health = health_monitor.check_all_sources()
                        log.info(
                            f"Health: {health['healthy']} OK | "
                            f"{health['degraded']} degraded | "
                            f"{health['down']} down",
                            "HEALTH",
                        )
                        run._last_health_check = _t.time()
                    except Exception as e:
                        log.error(f"Health check erro: {e}", "HEALTH")

            log.info(f"[dim]Próxima verificação em {cfg.LOOP_INTERVAL_SECONDS}s[/]")
            time.sleep(cfg.LOOP_INTERVAL_SECONDS)

    except KeyboardInterrupt:
        log.warning("Bot parado (Ctrl+C)")
    finally:
        if strategy_manager:
            print("\n📊 PERFORMANCE POR ESTRATÉGIA:")
            report = strategy_manager.get_performance_report()
            print(report.to_string(index=False))

        # Analytics final report
        if perf_analyzer:
            print("\n📊 PERFORMANCE FINAL:")
            report = perf_analyzer.generate_report()
            for metric, value in report.items():
                print(f"  {metric:20s}: {value:.2f}")

            breakdown = perf_analyzer.get_strategy_breakdown()
            if not breakdown.empty:
                print("\n📈 BREAKDOWN POR ESTRATÉGIA:")
                print(breakdown.to_string(index=False))

        if trade_logger:
            csv_file = trade_logger.export_to_csv('data/trades_export.csv')
            print(f"\n💾 Trades exportados: {csv_file}")
            stats = trade_logger.get_summary_stats()
            print(f"   Total: {stats['total_trades']} | Win Rate: {stats['win_rate']:.1f}% | P&L: €{stats['total_pnl']:.2f}")

        mt5c.disconnect()
        log.info("MT5 desligado.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["live", "paper"], default="paper")
    args = parser.parse_args()
    run(args.mode)
