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

    return {
        "status": bot_status['status'],
        "uptime_seconds": uptime_seconds,
        "uptime_hours": round(uptime_seconds / 3600, 2),
        "balance": bot_status['balance'],
        "open_positions": bot_status['positions'],
        "last_update": bot_status['last_update'].isoformat() if bot_status.get('last_update') else None,
        "timestamp": datetime.now().isoformat()
    }

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
from src.automation import DailyReporter, AutoRestarter, ConfigBackup
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
from src.risk.compounding_manager import CompoundingManager
from src.risk.anti_martingale import AntiMartingaleScaler
from src.risk.volatility_scaler import VolatilityScaler
from src.strategies.supply_demand import SupplyDemandStrategy
from src.strategies.pin_bar import PinBarStrategy
from src.strategies.inside_bar import InsideBarStrategy
from src.strategies.engulfing import EngulfingStrategy
from src.strategies.fibonacci import FibonacciStrategy
import src.strategy as strat
from src.capital_scaling import get_retail_lot_size, get_retail_milestone

# Compounding, Anti-Martingale e Volatility Scaler (globais)
compounding_mgr = None
anti_martingale = None
vol_scaler = None

# Price Action Strategies (globais)
supply_demand = None
pin_bar = None
inside_bar = None
engulfing = None
fibonacci = None

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
dd_protector = DrawdownProtector(
    max_daily_loss_pct=getattr(cfg, 'MAX_DAILY_LOSS_PCT', 3.0),
    max_weekly_loss_pct=getattr(cfg, 'MAX_WEEKLY_LOSS_PCT', 8.0),
)
position_mgr = PositionManager()

# Instâncias globais (serão inicializadas no main)
compounding_mgr = None
anti_martingale = None
vol_scaler = None
supply_demand = None
pin_bar = None

import src.logger as log
import src.dashboard_server as dash
import src.arb_runner as arb_runner
from src.monitoring.alert_manager import AlertManager

# Live state writer for Flask dashboard
try:
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from live_state_writer import LiveStateWriter
    _writer = LiveStateWriter()
    _WRITER_OK = True
except Exception as _we:
    _WRITER_OK = False
    print(f"[WARN] LiveStateWriter not available: {_we}")

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
# Detect mode
import argparse
parser = argparse.ArgumentParser()
parser.add_argument('--mode', choices=['paper', 'live'], default='paper')
args = parser.parse_args()

# Check environment variable too
trading_mode = os.getenv('TRADING_MODE', args.mode)
PAPER_TRADING = (trading_mode == 'paper')

if PAPER_TRADING:
    print("    ⚠ ⚠ MODO PAPER: sem ordens reais")
else:
    print("    ⚠ ⚠ MODO LIVE (DEMO): ordens reais na conta demo")

PAPER_MODE = PAPER_TRADING
alert_manager: AlertManager = None  # initialised in main()
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

def get_strategy_stats(symbol: str) -> dict:
    """
    Obtém estatísticas reais do histórico de trades para o símbolo.
    Se não houver histórico suficiente, retorna defaults conservadores.
    """
    global trade_logger
    if not trade_logger:
        return {'win_rate': 0.65, 'avg_win': 15.0, 'avg_loss': 10.0}

    try:
        # Buscar trades do banco de dados (últimos 100 trades para dinamismo)
        trades = trade_logger.get_trades(symbol=symbol)
        
        # Filtrar apenas trades fechados (com PnL definido)
        closed_trades = trades[trades['pnl'].notna()]

        if len(closed_trades) < 10:
            # Histórico insuficiente - usar métricas do settings.py ou defaults
            metrics = cfg.ASSET_METRICS.get(symbol, {})
            return {
                'win_rate': metrics.get('win_rate', 0.65),
                'avg_win': metrics.get('avg_return', 15.0),
                'avg_loss': metrics.get('avg_return', 15.0) * 0.8
            }

        winners = closed_trades[closed_trades['pnl'] > 0]
        losers = closed_trades[closed_trades['pnl'] < 0]

        win_rate = len(winners) / len(closed_trades)
        avg_win = winners['pnl'].mean() if len(winners) > 0 else 1.0
        avg_loss = abs(losers['pnl'].mean()) if len(losers) > 0 else 1.0

        return {
            'win_rate': round(win_rate, 2),
            'avg_win': round(float(avg_win), 2),
            'avg_loss': round(float(avg_loss), 2)
        }
    except Exception as e:
        log.error(f"Erro ao calcular stats: {str(e)}", symbol)
        return {'win_rate': 0.65, 'avg_win': 15.0, 'avg_loss': 10.0}

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

    # Detectar regime (DESATIVADO TEMPORARIAMENTE para debug)
    # regime = regime_detector.detect_regime(df)
    # if regime['regime'] == 'VOLATILE_RANGE':
    #     log.info(f"Skip - regime {regime['regime']} (ADX={regime['adx']:.1f}, VolZ={regime['volatility_z']:.1f})", symbol)
    #     return status
        
    # News filter
    if cfg.USE_NEWS_FILTER:
        news_check = news_filter.is_blocked(symbol, datetime.now())
        if news_check['blocked']:
            log.info(
                f"[NEWS] Bloqueado {news_check['event_name']} | "
                f"{news_check['minutes_until']}min | janela 30min antes / 15min após",
                symbol,
            )
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

        # 1. Trailing Stop Dinâmico (ATR)
        # Se lucro > 1% do preço de entrada, mover SL baseado em 2x ATR
        profit_pct = (pos.profit / (pos.volume * pos.price_open * 100)) # Estimativa simples
        if pos.profit > (account_balance * 0.01): # Usar 1% do balance como gatilho de lucro
            atr_val = atr_last
            if pos_type == "BUY":
                new_sl = current_price - (2 * atr_val)
                if new_sl > pos.sl:
                    log.info(f"Trailing Stop: movendo SL para {new_sl:.5f}", symbol)
                    if not PAPER_MODE:
                        mt5c.modify_position_sl_tp(pos.ticket, new_sl, pos.tp)
            else:
                new_sl = current_price + (2 * atr_val)
                if pos.sl == 0 or new_sl < pos.sl:
                    log.info(f"Trailing Stop: movendo SL para {new_sl:.5f}", symbol)
                    if not PAPER_MODE:
                        mt5c.modify_position_sl_tp(pos.ticket, new_sl, pos.tp)

        # 2. Pirâmide Automática (Adicionar a posições vencedoras)
        if getattr(cfg, 'PYRAMIDING_ENABLED', True):
            current_adds = position_mgr.get_position_adds(symbol)
            max_adds = getattr(cfg, 'PYRAMIDING_MAX_ADDS', 2)

            # Calculate pips profit (works for forex/metals/crypto)
            _sym_info = mt5c.get_symbol_info(symbol)
            _point = getattr(_sym_info, 'point', 0.00001) if _sym_info else 0.00001
            _pip = _point * 10 if _point < 0.01 else _point  # 5/3-digit brokers
            _price_diff = abs(current_price - pos.price_open)
            profit_pips = _price_diff / _pip if _pip > 0 else 0

            # Z-score condition: signal still valid (not yet reverting)
            z_still_valid = (not np.isnan(z_last) and
                             abs(z_last) >= z_enter * 0.8)

            if (profit_pips >= 20
                    and z_still_valid
                    and current_adds < max_adds
                    and pos.profit > 0):
                add_lot = round(
                    pos.volume * getattr(cfg, 'PYRAMIDING_SIZE_MULTIPLIER', 0.5), 2
                )
                add_lot = max(add_lot, _sym_info.volume_min if _sym_info else 0.01)
                log.info(
                    f"Pyramiding add #{current_adds+1}: {add_lot} lots "
                    f"({profit_pips:.0f} pips profit, Z={z_last:.2f})", symbol
                )
                if not PAPER_MODE:
                    res = mt5c.send_order(
                        symbol, pos_type, add_lot, pos.price_open, 0.0,
                        cfg.MAGIC_NUMBER, f"PYR_{current_adds+1}"
                    )
                    if res['success']:
                        position_mgr.register_add(symbol)
                        mt5c.modify_position_sl_tp(pos.ticket, pos.price_open, pos.tp)
                else:
                    position_mgr.register_add(symbol)

        # 3. Position Management: Scale Out
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
    strategy_name = "Consensus"
    confidence = 1.0

    # 1. Supply/Demand Check
    sd_signal = None
    if cfg.USE_SUPPLY_DEMAND:
        sd_signal = supply_demand.check_zone_retest(
            current_price=close_last,
            current_bar=len(df),
            df=df
        )
        if sd_signal:
            log.info(f"🎯 Supply/Demand Signal: {sd_signal}", symbol)

    # 2. Pin Bar Check
    pb_signal = None
    if cfg.USE_PIN_BAR:
        pb_signal = pin_bar.check_signal(
            df=df,
            z_score=z_last
        )
        if pb_signal:
            log.info(f"📌 Pin Bar Signal: {pb_signal}", symbol)

    # 3. Inside Bar Check
    ib_signal = None
    if cfg.USE_INSIDE_BAR:
        ib_signal = inside_bar.check_breakout(df=df, current_price=close_last)
        if ib_signal:
            log.info(f"📊 Inside Bar Signal: {ib_signal}", symbol)

    # 4. Engulfing Check
    eng_signal = None
    if cfg.USE_ENGULFING:
        eng_signal = engulfing.check_signal(df=df, z_score=z_last)
        if eng_signal:
            log.info(f"🔄 Engulfing Signal: {eng_signal}", symbol)

    # 5. Fibonacci Check
    fib_signal = None
    if cfg.USE_FIBONACCI:
        fib_signal = fibonacci.check_signal(df=df, current_price=close_last, z_score=z_last)
        if fib_signal:
            log.info(f"📐 Fibonacci Signal: {fib_signal}", symbol)

    # 6. Mean Reversion Signal
    z_signal = None
    if not np.isnan(z_last):
        if z_last <= -z_enter and close_last < ma_last:
            z_signal = "BUY"
        elif z_last >= z_enter and close_last > ma_last:
            z_signal = "SELL"

    # COMBINAR TODOS OS SINAIS (CONSENSO)
    signals = []
    if sd_signal: signals.append(sd_signal)
    if pb_signal: signals.append(pb_signal)
    if ib_signal: signals.append(ib_signal)
    if eng_signal: signals.append(eng_signal)
    if fib_signal: signals.append(fib_signal)
    if z_signal:  signals.append(z_signal)

    # CONSENSO (mínimo 2 estratégias)
    if len(signals) >= 2:
        if signals.count('BUY') >= 2:
            signal = 'BUY'
            confidence = signals.count('BUY') / len(signals)
            log.info(f"✅ CONSENSO BUY | {confidence:.0%} | {signals}", symbol)
        elif signals.count('SELL') >= 2:
            signal = 'SELL'
            confidence = signals.count('SELL') / len(signals)
            log.info(f"✅ CONSENSO SELL | {confidence:.0%} | {signals}", symbol)
        else:
            signal = None # Sinais conflitantes
    elif len(signals) == 1:
        # Só 1 estratégia, usar se for sinal forte (Z extremo ou Price Action clara)
        if z_signal and abs(z_last) > z_enter * 1.5:
            signal = z_signal
            strategy_name = "Extreme Mean Reversion"
        elif sd_signal or pb_signal or ib_signal or eng_signal or fib_signal:
            signal = signals[0]
            strategy_name = "Price Action"
            confidence = 0.7

    # Multi-strategy override (se habilitado)
    if cfg.USE_MULTI_STRATEGY and strategy_manager and not signal:
        multi_result = strategy_manager.get_combined_signal(symbol, df, datetime.now())
        if multi_result['signal'] in ['BUY', 'SELL']:
            signal = multi_result['signal']
            strategy_name = multi_result['strategy']
            confidence = multi_result['confidence']
            log.info(f"🚀 Multi-Strategy Override: {signal} via {strategy_name}", symbol)

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
    
    # ─── Cálculo de Lote Dinâmico Profissional ───
    stats = get_strategy_stats(symbol)
    
    lots = calculate_dynamic_lot_size(
        symbol=symbol,
        account_balance=account_balance,
        win_rate=stats['win_rate'],
        avg_win=stats['avg_win'],
        avg_loss=stats['avg_loss']
    )
    risk_money = account_balance * (lots * sl_dist / close_last) if close_last > 0 else 0

    if lots <= 0:
        log.warning("Lots = 0 (Kelly/Volatility adjustment), skip", symbol)
        return status

    # Aplicar multiplicadores adicionais (Drawdown e Macro)
    risk_mult = (dd_check['risk_multiplier'] if dd_check else 1.0) * risk_multiplier * symbol_risk_mult
    lots = round(lots * risk_mult * min(lot_mult * confidence, cfg.MACRO_LOT_MAX_MULT), 2)
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
            # Notify alert manager (resets 48h idle timer)
            alert_manager.record_trade()
            
    return status

def calculate_dynamic_lot_size(
    symbol: str,
    account_balance: float,
    win_rate: float = 0.65,
    avg_win: float = 15.0,
    avg_loss: float = 10.0
) -> float:
    """
    Calcula lot size dinâmico usando:
    1. Compounding Manager (milestones)
    2. Kelly Criterion
    3. Anti-Martingale (win streaks)
    4. Volatility Scaling (ATR)
    
    Returns:
        float: Lot size ajustado
    """
    # 1. Atualizar capital no Compounding Manager
    compounding_mgr.update_capital(account_balance)
    
    # 2. Obter parâmetros do milestone atual
    if cfg.USE_COMPOUNDING:
        position_params = compounding_mgr.calculate_position_size(
            win_rate=win_rate,
            avg_win=avg_win,
            avg_loss=avg_loss,
            account_balance=account_balance
        )
        
        risk_amount = position_params['risk_amount']
        max_positions = position_params['max_positions']
        
        log.info(
            f"💰 Milestone {compounding_mgr.get_current_milestone_name()} | "
            f"Risk: {position_params['effective_risk_pct']*100:.2f}% | "
            f"Amount: €{risk_amount:.2f}", symbol
        )
    else:
        # Fallback: risk fixo
        risk_amount = account_balance * cfg.MAX_RISK_PER_TRADE
        max_positions = cfg.MAX_POSITIONS
    
    # 3. Calcular lot base (baseado no risk amount e ATR)
    df = _bars_cache.get(symbol)
    if df is not None and 'atr' in df.columns:
        current_atr = df['atr'].iloc[-1]
        historical_atr_median = df['atr'].median()
    else:
        # Tentar obter ATR se não estiver no cache
        needed = cfg.ATR_PERIOD + 10
        df_atr = mt5c.get_bars(symbol, cfg.TIMEFRAME, needed)
        if df_atr is not None and len(df_atr) >= cfg.ATR_PERIOD:
            import pandas_ta as ta
            df_atr['atr'] = ta.atr(df_atr['high'], df_atr['low'], df_atr['close'], length=cfg.ATR_PERIOD)
            current_atr = df_atr['atr'].iloc[-1]
            historical_atr_median = df_atr['atr'].median()
        else:
            current_atr = 0.0001
            historical_atr_median = 0.0001
    
    # Lot base = risk_amount / (atr * point_value)
    symbol_info = mt5c.get_symbol_info(symbol)
    if symbol_info is None:
        return cfg.POSITION_SIZE
    
    point_value = symbol_info.trade_contract_size * symbol_info.point
    
    if current_atr > 0 and point_value > 0:
        base_lot = risk_amount / (current_atr * point_value)
    else:
        base_lot = cfg.POSITION_SIZE
    
    # 4. Anti-Martingale (ajustar por win streak)
    if cfg.USE_ANTI_MARTINGALE:
        anti_mart_multiplier = anti_martingale.get_multiplier()
        base_lot *= anti_mart_multiplier
        
        if anti_mart_multiplier > 1.0:
            log.info(f"📈 Anti-Martingale: {anti_mart_multiplier:.1f}x (streak: {anti_martingale.consecutive_wins})", symbol)
    
    # 5. Volatility Scaling
    if cfg.USE_VOLATILITY_SCALING:
        base_lot = vol_scaler.calculate_scaled_lot(
            current_atr=current_atr,
            historical_atr_median=historical_atr_median,
            base_lot=base_lot
        )
    
    # 6. Normalizar lot (mín/máx do símbolo)
    min_lot = symbol_info.volume_min
    max_lot = symbol_info.volume_max
    lot_step = symbol_info.volume_step
    
    # Arredondar para step
    if lot_step > 0:
        base_lot = round(base_lot / lot_step) * lot_step
    
    # Aplicar limites
    final_lot = max(min_lot, min(base_lot, max_lot))

    # ── Per-pair lot multiplier (reduce for new/unproven pairs) ──
    pair_mult = getattr(cfg, 'LOT_MULTIPLIER_BY_PAIR', {}).get(symbol, 1.0)
    if pair_mult != 1.0:
        final_lot = round(final_lot * pair_mult, 2)
        final_lot = max(min_lot, final_lot)
        log.info(f"[PAIR MULT] {symbol}: {pair_mult}x → {final_lot:.2f} lots", symbol)

    # ── Retail milestone cap: não exceder o lot máximo do tier ──
    retail_max = get_retail_lot_size(account_balance)
    if final_lot > retail_max:
        log.info(
            f"[SCALE] Lot {final_lot:.2f} → {retail_max:.2f} (retail cap "
            f"milestone={get_retail_milestone(account_balance)['name']})", symbol
        )
        final_lot = retail_max

    log.info(
        f"🎯 {symbol} LOT: €{risk_amount:.2f} risk → {final_lot:.2f} lots "
        f"(ATR: {current_atr:.5f})", symbol
    )

    return final_lot

# ─── Loop principal ───────────────────────────────────────────

def main(mode: str = None):
    global PAPER_MODE, compounding_mgr, anti_martingale, vol_scaler
    global supply_demand, pin_bar, inside_bar, engulfing, fibonacci
    if mode is None:
        mode = trading_mode
    PAPER_MODE = (mode == "paper")

    # Iniciar health API em background
    health_thread = threading.Thread(target=run_health_api, daemon=True)
    health_thread.start()
    
    # Atualizar status
    bot_status['status'] = 'initializing'

    log.setup()
    
    # ============================================================
    #  AUTOMATION & NOTIFICATIONS
    # ============================================================
    
    # Daily reporter
    if cfg.DAILY_REPORT_ENABLED:
        reporter = DailyReporter()
        log.info("📊 Daily Reports: ATIVO")
    else:
        reporter = None

    # Alert Manager (24/7 safety checks)
    global alert_manager
    alert_manager = AlertManager()

    # Auto-restart
    if cfg.AUTO_RESTART_ENABLED:
        restarter = AutoRestarter(
            script_path="run_live.py",
            max_restarts=cfg.MAX_RESTARTS,
            cooldown_minutes=cfg.RESTART_COOLDOWN_MIN
        )
        log.info("🔄 Auto-restart: ATIVO")

    # Config backup
    if cfg.AUTO_BACKUP_ENABLED:
        backup = ConfigBackup()
        backup.auto_backup(interval_hours=cfg.BACKUP_INTERVAL_HOURS)
        log.info("💾 Auto-backup: ATIVO")

    # Compounding Manager
    compounding_mgr = CompoundingManager(
        initial_capital=cfg.INITIAL_CAPITAL,
        target_monthly_return=cfg.TARGET_MONTHLY_RETURN
    )

    # Anti-Martingale Scaler
    anti_martingale = AntiMartingaleScaler(
        base_lot=cfg.POSITION_SIZE,
        max_multiplier=cfg.ANTI_MARTINGALE_MAX_MULTIPLIER
    )

    # Volatility Scaler
    vol_scaler = VolatilityScaler(
        min_scale=cfg.VOLATILITY_SCALING_MIN,
        max_scale=cfg.VOLATILITY_SCALING_MAX
    )

    # Price Action Strategies
    supply_demand = SupplyDemandStrategy(
        zone_strength_min=cfg.SUPPLY_DEMAND_ZONE_STRENGTH,
        zone_age_max=cfg.SUPPLY_DEMAND_ZONE_AGE,
        price_move_min=cfg.SUPPLY_DEMAND_MIN_MOVE
    )

    pin_bar = PinBarStrategy(
        shadow_to_body_ratio=cfg.PIN_BAR_SHADOW_RATIO,
        shadow_to_total_ratio=cfg.PIN_BAR_SHADOW_PCT,
        z_score_threshold=cfg.PIN_BAR_Z_THRESHOLD
    )

    inside_bar = InsideBarStrategy(
        min_mother_size=cfg.INSIDE_BAR_MIN_MOTHER,
        max_inside_ratio=cfg.INSIDE_BAR_MAX_RATIO,
        breakout_buffer=cfg.INSIDE_BAR_BUFFER
    )

    engulfing = EngulfingStrategy(
        min_body_ratio=cfg.ENGULFING_MIN_BODY,
        engulf_margin=cfg.ENGULFING_MARGIN,
        z_score_threshold=cfg.ENGULFING_Z_THRESHOLD
    )

    fibonacci = FibonacciStrategy(
        lookback_swing=cfg.FIB_LOOKBACK_SWING,
        fib_tolerance=cfg.FIB_TOLERANCE,
        key_levels=cfg.FIB_KEY_LEVELS
    )

    log.info("💰 Compounding Manager inicializado")
    log.info(f"📈 Anti-Martingale ativo (max {cfg.ANTI_MARTINGALE_MAX_MULTIPLIER:.1f}x)")
    log.info(f"📊 Volatility Scaling ativo ({cfg.VOLATILITY_SCALING_MIN:.1f}x - {cfg.VOLATILITY_SCALING_MAX:.1f}x)")
    log.info(f"📊 Supply/Demand: {'ATIVO' if cfg.USE_SUPPLY_DEMAND else 'DESATIVADO'}")
    log.info(f"📌 Pin Bar: {'ATIVO' if cfg.USE_PIN_BAR else 'DESATIVADO'}")
    log.info(f"📊 Inside Bar: {'ATIVO' if cfg.USE_INSIDE_BAR else 'DESATIVADO'}")
    log.info(f"🔄 Engulfing: {'ATIVO' if cfg.USE_ENGULFING else 'DESATIVADO'}")
    log.info(f"📐 Fibonacci: {'ATIVO' if cfg.USE_FIBONACCI else 'DESATIVADO'}")
    
    log.info("A ligar ao MetaTrader 5...")
    if not mt5c.connect():
        log.error("Não foi possível ligar ao MT5.")
        sys.exit(1)

    account = mt5c.get_account_info()
    balance = account.get("balance", 0.0)

    # ============================================================
    #  INICIALIZAR PORTFOLIO ALLOCATOR
    # ============================================================
    symbols_to_trade = getattr(cfg, 'ACTIVE_SYMBOLS', cfg.ALL_AVAILABLE_SYMBOLS)
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
        
        symbols_to_trade = getattr(cfg, 'ACTIVE_SYMBOLS', cfg.ALL_AVAILABLE_SYMBOLS)
    
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

    loop_count = 0
    try:
        while True:
            account = mt5c.get_account_info()
            balance = account.get("balance", 0.0)
            equity = account.get("equity", balance)
            dash.update_account(account)
            dash.update_scaling(balance)

            # Atualizar e logar milestone
            if account:
                compounding_mgr.update_capital(balance)
                stats = compounding_mgr.get_stats()
                
                # Log a cada 5 minutos (30 loops de 10s)
                if loop_count % 30 == 0:
                    log.info(
                        f"💰 CAPITAL SCALING | "
                        f"Milestone: {stats['current_milestone']} | "
                        f"Capital: €{stats['current_capital']:.2f} | "
                        f"Growth: {stats['total_growth_pct']:.1f}% | "
                        f"Next: €{stats['next_milestone']['target']} "
                        f"({stats['next_milestone']['progress_pct']:.1f}%)"
                    )

            # Railway Health Status Update
            open_pos = mt5c.get_open_positions(None, cfg.MAGIC_NUMBER)
            bot_status['balance'] = balance
            bot_status['positions'] = len(open_pos) if open_pos else 0
            bot_status['last_update'] = datetime.now()
            bot_status['status'] = 'running'

            # ============================================================
            #  PROCESSO DE EXECUÇÃO
            # ============================================================
            sentiment = sentiment_analyzer.get_market_sentiment() if getattr(cfg, 'USE_SENTIMENT_ANALYSIS', False) else None
            dd_check = dd_protector.check_drawdown(balance)

            # ── Alert Manager: 24/7 safety checks ──────────────
            _margin_level = account.get('margin_level', 0.0) if account else 0.0
            _spreads_now  = {s: mt5c.get_spread_points(s) for s in cfg.ACTIVE_SYMBOLS
                             if getattr(cfg, 'ACTIVE_SYMBOLS', None)}
            alert_check = alert_manager.check_all(
                balance=balance,
                positions=open_pos or [],
                spreads=_spreads_now,
                margin_level=float(_margin_level),
            )
            alert_manager.set_mt5_connected(bool(account))

            # Close oldest position if margin is low
            if 'CLOSE_OLDEST' in alert_check['actions'] and open_pos:
                oldest = min(open_pos, key=lambda p: getattr(p, 'time', 0))
                log.warning(f"[ALERT] Closing oldest position: {oldest.symbol} #{oldest.ticket}")
                if not PAPER_MODE:
                    mt5c.close_position(oldest, cfg.MAGIC_NUMBER)

            # Reconnect MT5 if needed
            if 'RECONNECT_MT5' in alert_check['actions']:
                log.warning("[ALERT] Attempting MT5 reconnect...")
                if mt5c.connect():
                    log.success("MT5 reconnected", "ALERT")
                    alert_manager.set_mt5_connected(True)

            # STOP_TRADING from alert_manager (daily loss >2%)
            if 'STOP_TRADING' in alert_check['actions']:
                log.warning("[ALERT] STOP_TRADING — daily loss threshold hit")
                time.sleep(cfg.LOOP_INTERVAL_SECONDS)
                loop_count += 1
                continue

            # ── Limite de perda diária — parar TODAS as novas posições ──
            if dd_check['action'] == 'STOP':
                log.warning(
                    f"[DD] LIMITE DIÁRIO ATINGIDO | "
                    f"Daily DD: {dd_check['daily_dd_pct']:.2f}% / {cfg.MAX_DAILY_LOSS_PCT}% | "
                    f"Sem novas posições até amanhã"
                )
                time.sleep(cfg.LOOP_INTERVAL_SECONDS)
                loop_count += 1
                continue

            # ── Máximo de posições abertas ──
            max_open = getattr(cfg, 'MAX_OPEN_POSITIONS', 3)
            n_open = len(open_pos) if open_pos else 0
            if n_open >= max_open:
                log.info(f"[RISK] Max posições abertas ({n_open}/{max_open}) — sem novas entradas")
                time.sleep(cfg.LOOP_INTERVAL_SECONDS)
                loop_count += 1
                continue

            _skip_symbols = alert_check.get('skip_symbols', set())

            for symbol in symbols_to_trade:
                if symbol in _skip_symbols:
                    log.info(f"[ALERT] {symbol} skipped — spread spike", symbol)
                    continue
                try:
                    # Processar símbolo com toda a lógica de filtros e sinais
                    status = process_symbol(
                        symbol, balance, allocator, strategy_manager, 
                        sentiment, dd_check
                    )
                    
                except Exception as e:
                    log.error(f"Erro ao processar {symbol}: {str(e)}")
                    continue

            # Triangular Arbitrage
            if _TRI and cfg.TRIANGULAR_ARB_ENABLED:
                tri_arb.run_triangular_arb_check(balance)

            # Arb Runner (Statistical Arbitrage)
            if cfg.USE_ARBITRAGE:
                arb_runner.run_arb_cycle(balance)

            # Verificar relatório diário (a cada loop):
            if reporter:
                reporter.send_report()

            # schedule.run_pending() para tarefas agendadas (email 18:00, etc.)
            try:
                import schedule
                schedule.run_pending()
            except ImportError:
                pass

            # ── Write live state for Flask dashboard ──
            if _WRITER_OK:
                try:
                    _writer.update(
                        account=mt5c.get_account_info(),
                        positions=mt5c.get_open_positions(None, cfg.MAGIC_NUMBER) or [],
                        signals=getattr(strategy_manager, 'last_signals', []),
                        spreads={s: mt5c.get_spread_points(s) for s in cfg.SYMBOLS},
                        prices={s: mt5c.get_tick(s).ask
                                for s in cfg.SYMBOLS if mt5c.get_tick(s)},
                    )
                except Exception as _wex:
                    log.warning(f"LiveStateWriter error: {_wex}")

            log.info(f"[dim]Próxima verificação em {cfg.LOOP_INTERVAL_SECONDS}s[/]")
            loop_count += 1
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
    main(args.mode)
