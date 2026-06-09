from __future__ import annotations
"""
Orchestrator — V9 (Fully Integrated)

Coordinates all layers of the AlphaSystem V9 macro-driven engine:

  Background daemons (always running):
    - VixMonitor        (60s)  → macro.vix / regime
    - DXYBasket         (60s)  → macro.dxy / regime
    - YieldMonitor      (1h)   → macro.yield_curve
    - CommodityMonitor  (60s)  → macro.gold/wti/brent
    - NewsInterpreter   (5min) → macro.news_score
    - EconomicCalendar  (30min)→ macro.high_impact_next_30m
    - BenchmarkMonitor  (5min) → global risk-on/risk-off context

  Per-cycle (session-driven):
    1. Sync macro state from all daemons
    2. At session open: 6-step PrepWorkflow
    3. Per symbol, per timeframe: compute indicators
    4. MACD + BB deep analysis
    5. MTF confluence check
    6. ScenarioEvaluator (fast-fail veto tree)
    7. SignalGenerator (final 4/6 confirmations)
    8. Risk gate → OrderManager
    9. Write state.json + history.jsonl
"""
import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from src.macro.macro_context import MacroContext
from src.macro.vix_monitor import VixMonitor
from src.macro.dxy_basket import DXYBasket
from src.macro.yield_monitor import YieldMonitor
from src.macro.commodity_monitor import CommodityMonitor
from src.macro.news_interpreter import NewsInterpreter
from src.macro.economic_calendar import EconomicCalendar
from src.analysis.fair_price import calculate as calc_fair_price, FairPriceResult
from src.analysis.correlation import CorrelationMatrix
from src.analysis.scenario_evaluator import evaluate as eval_scenario, ASSET_DXY_BETA
from src.technical.indicators import compute_bundle, IndicatorBundle
from src.technical.macd_analyzer import analyze as analyze_macd
from src.technical.bollinger_analyzer import analyze as analyze_bb
from src.technical.multi_timeframe import analyze as analyze_mtf
from src.technical.signal_generator import (
    generate as gen_signal, FinalSignal, SIGNAL_BUY, SIGNAL_SELL, SIGNAL_HOLD, SIGNAL_BLOCK
)
from src.session.market_sessions import current_sessions, is_tradeable_for
from src.session.prep_workflow import PrepWorkflow
from src.execution.order_manager import OrderManager
from src.risk.professional_risk import ProfessionalRiskManager
from src.benchmark.portfolio_monitor import BenchmarkPortfolioMonitor
from src.engine.scanner import (
    build_opportunity, scan,
    compute_permission_score, calc_atr_fit,
    OpportunityResult, PermissionResult,
)
from src.engine.scanner_metrics import ScannerMetrics

logger = logging.getLogger(__name__)

TIMEFRAMES   = ["M5", "M15", "M30", "H1"]
PRIMARY_TF   = "M5"
STATE_PATH   = Path("state/state.json")
HISTORY_PATH = Path("state/state_history.jsonl")


class Orchestrator:
    def __init__(self, mt5, config: dict, api_keys: dict, dry_run: bool = True):
        self._mt5 = mt5
        self._cfg = config
        self._dry_run = dry_run
        self._shutdown = False
        self._cycle = 0
        self._lock = threading.Lock()

        self._symbols: list[str] = config.get("symbols", ["EURUSD", "GOLD"])

        # ── Central macro state ────────────────────────────────────────
        self.macro = MacroContext()

        # ── Background daemons ─────────────────────────────────────────
        finnhub_key = api_keys.get("FINNHUB_KEY", "")
        fred_key    = api_keys.get("FRED_KEY", "")

        self._vix       = VixMonitor(self.macro, finnhub_key=finnhub_key)
        self._dxy       = DXYBasket(finnhub_key=finnhub_key)
        self._yield     = YieldMonitor(fred_key=fred_key)
        self._commodity = CommodityMonitor(self.macro)
        self._news      = NewsInterpreter(self.macro, finnhub_key=finnhub_key)
        self._calendar  = EconomicCalendar(self.macro)
        self._benchmark = BenchmarkPortfolioMonitor()

        # ── Core components ────────────────────────────────────────────
        self._risk       = ProfessionalRiskManager(self.macro)
        self._orders     = OrderManager(mt5, self._risk, dry_run=dry_run)
        self._prep       = PrepWorkflow(self.macro)
        self._corr       = CorrelationMatrix(window=20)

        # ── State caches ───────────────────────────────────────────────
        self._bundles: dict[str, dict[str, IndicatorBundle]] = {}
        self._prev_bb_width: dict[str, float] = {}
        self._prev_ohlc: dict[str, dict] = {}
        self._fair_prices: dict[str, FairPriceResult] = {}
        self._last_prep: dict | None = None
        self._scenario: str = "indefinido"
        self._last_prep_session: str = ""
        # ── Scanner state ──────────────────────────────────────────────
        self._watchlist: list[dict] = []
        self._perm_results: dict[str, str] = {}
        self._metrics = ScannerMetrics()

    # ── Lifecycle ──────────────────────────────────────────────────────

    def start_daemons(self):
        self._vix.start()
        self._dxy.start()
        self._yield.start()
        self._commodity.start()
        self._news.start()
        self._calendar.start()
        self._benchmark.start()
        logger.info("All daemons started: VIX, DXY, Yield, Commodity, News, Calendar, Benchmark")

    def stop(self):
        self._shutdown = True
        for d in [self._vix, self._dxy, self._yield, self._commodity, self._news,
                  self._calendar, self._benchmark]:
            try:
                d.stop()
            except Exception:
                pass
        logger.info("Orchestrator stopped")

    def update_account(self, info):
        try:
            self._risk.update_account(float(info.balance), float(info.equity))
        except Exception:
            pass

    # ── Main cycle ─────────────────────────────────────────────────────

    def run_cycle(self) -> dict:
        self._cycle += 1
        ts = datetime.now(timezone.utc).isoformat()
        session = current_sessions()

        # Sync all macro daemons into MacroContext
        self._sync_macro()

        # Session prep at each new session open
        if self._should_prep(session.primary):
            self._run_prep(session.primary)

        # ── Phase 1: scan — compute indicators + opportunity for all symbols ──
        all_sigs: dict[str, FinalSignal] = {}
        opportunities: list[OpportunityResult] = []

        vix_now = self.macro.vix or 20.0
        for sym in self._symbols:
            sig = self._process_symbol(sym, session)
            if sig is None:
                continue
            all_sigs[sym] = sig
            fp = self._fair_prices.get(sym)
            fp_val = fp.fair_price if fp else 0.0
            bundle = self._bundles.get(sym, {}).get(PRIMARY_TF)
            atr_fit_val = calc_atr_fit(bundle, fp_val) if bundle else 0.5

            from src.analysis.asset_profiler import get_profile
            asset_class = get_profile(sym).asset_class.value

            opp = build_opportunity(
                symbol=sym,
                timeframe=sig.timeframe,
                bundle=bundle,
                mcs=sig.mcs_n,
                bcs=sig.bcs_n,
                hcs=sig.hcs_n,
                ves=sig.ves,
                es=sig.es,
                asset_class=asset_class,
                vix=vix_now,
                rs=sig.rs,
                session=session.primary if hasattr(session, "primary") else "new_york",
            )
            opp.notes.append(f"atr_fit={atr_fit_val:.3f}")
            opportunities.append(opp)

        # ── Phase 2: scan — sort watchlist by opportunity score ─────────────
        watchlist = scan(opportunities)
        self._watchlist = [
            {
                "symbol":         o.symbol,
                "asset_class":    o.asset_class,
                "score":          o.opportunity_score,
                "label":          o.opportunity_label,
                "opp_threshold":  o.opp_threshold,
                "perm_threshold": o.perm_threshold,
            }
            for o in watchlist
        ]
        if watchlist:
            logger.info(f"[SCAN] watchlist={[(o.symbol, o.opportunity_label, round(o.opportunity_score,2)) for o in watchlist]}")

        # ── Phase 3: permission — check each watchlist item ─────────────────
        signals: list[FinalSignal] = []
        self._perm_results = {}

        blackout = self._calendar.is_blackout("USD")

        for opp in watchlist:
            sig = all_sigs.get(opp.symbol)
            if sig is None:
                continue

            atr_fit_val = 0.5
            for note in opp.notes:
                if note.startswith("atr_fit="):
                    try:
                        atr_fit_val = float(note.split("=")[1])
                    except ValueError:
                        pass

            perm = compute_permission_score(
                cs=sig.cs,
                rs=sig.rs,
                es=sig.es,
                atr_fit=atr_fit_val,
                blackout=blackout,
                perm_threshold=opp.perm_threshold,   # threshold calibrado para este ativo/TF
            )
            perm.symbol    = opp.symbol
            perm.timeframe = sig.timeframe

            self._perm_results[opp.symbol] = perm.decision
            self._metrics.record(
                symbol=opp.symbol,
                asset_class=opp.asset_class,
                timeframe=sig.timeframe,
                opp_score=opp.opportunity_score,
                opp_label=opp.opportunity_label,
                opp_threshold=opp.opp_threshold,
                perm_score=perm.permission_score,
                perm_decision=perm.decision,
                perm_threshold=opp.perm_threshold,
                cs=perm.cs, rs=perm.rs, es=perm.es, atr_fit=atr_fit_val,
                blocked_reason=perm.blocked_reason,
            )
            logger.debug(
                f"[PERM] {opp.symbol}({opp.asset_class}/{sig.timeframe})"
                f" opp={opp.opportunity_score:.2f}/{opp.opp_threshold:.2f}({opp.opportunity_label})"
                f" perm={perm.permission_score:.2f}/{opp.perm_threshold:.2f}({perm.decision})"
                f" cs={perm.cs:.2f} rs={perm.rs:.2f} es={perm.es:.2f} atr={atr_fit_val:.2f}"
            )

            if perm.decision == "EXECUTE" and sig.signal in (SIGNAL_BUY, SIGNAL_SELL):
                signals.append(sig)
            elif perm.decision in ("CONFIRM", "REDUCE") and sig.signal in (SIGNAL_BUY, SIGNAL_SELL):
                # Sinal válido mas permissão parcial — reduce lot_multiplier
                if perm.decision == "REDUCE":
                    sig.lot_multiplier *= 0.5
                signals.append(sig)

        # Registar símbolos abaixo do threshold (weak — nunca chegam à fase de permissão)
        watchlist_syms = {o.symbol for o in watchlist}
        for opp in opportunities:
            if opp.symbol not in watchlist_syms:
                sig = all_sigs.get(opp.symbol)
                self._metrics.record(
                    symbol=opp.symbol, asset_class=opp.asset_class,
                    timeframe=sig.timeframe if sig else "M15",
                    opp_score=opp.opportunity_score, opp_label="weak",
                    opp_threshold=opp.opp_threshold,
                    perm_score=0.0, perm_decision="BLOCK",
                    perm_threshold=opp.perm_threshold,
                    cs=0.0, rs=sig.rs if sig else 0.0,
                    es=sig.es if sig else 0.0, atr_fit=0.5,
                    blocked_reason="below_opp_threshold",
                )

        self._metrics.end_cycle(self._cycle)

        # ── Phase 4: execute — risk gate → order manager ─────────────────────
        for sig in signals:
            can_open, reason = self._risk.can_open(sig.symbol, sig.signal.lower())
            if can_open:
                self._orders.open_position(
                    symbol=sig.symbol,
                    direction=sig.signal.lower(),
                    sl_distance=sig.sl_distance,
                    tp_distance=sig.tp_distance,
                )

        state = self._build_state(ts, session, signals)
        self._write_state(state)
        return state

    # ── Internal ───────────────────────────────────────────────────────

    def _sync_macro(self):
        try:
            d = self._dxy.state
            self.macro.dxy = d.index_value
            self.macro.dxy_prev = d.prev_value
            self.macro.dxy_change_pct = d.daily_change_pct / 100.0
            self.macro.dxy_regime = d.regime
            self.macro.dxy_zscore = d.zscore
        except Exception:
            pass
        try:
            y = self._yield.state
            self.macro.us10y = y.us10y
            self.macro.us2y  = y.us2y
            self.macro.us3m  = y.us3m
            self.macro.spread_10y_2y = y.spread_10y_2y
            self.macro.curve_regime  = y.curve_regime
            self.macro.yield_risk_mult = {"steep": 1.0, "flat": 0.75, "inverted": 0.50}.get(y.curve_regime, 0.75)
        except Exception:
            pass
        self.macro.recompute_global()

    def _should_prep(self, session_name: str) -> bool:
        return session_name not in ("closed", "asia") and session_name != self._last_prep_session

    def _run_prep(self, session_name: str):
        self._last_prep_session = session_name
        for sym in self._symbols:
            prev_close = self._get_prev_close(sym)
            if prev_close > 0:
                fp = calc_fair_price(
                    symbol=sym,
                    prev_close=prev_close,
                    dxy_change_pct=self.macro.dxy_change_pct,
                    vix_change_pct=(self.macro.vix - 20.0) / 100.0,
                )
                bundle = self._bundles.get(sym, {}).get(PRIMARY_TF)
                if bundle and bundle.bollinger:
                    fp.bb_max = bundle.bollinger.upper
                    fp.bb_min = bundle.bollinger.lower
                self._fair_prices[sym] = fp
                self.macro.fair_prices[sym] = fp.to_dict()

        report = self._prep.run(session_name, self._fair_prices)
        self._scenario = report.scenario
        self._last_prep = report.to_dict()
        logger.info(f"[PREP] session={session_name} scenario={self._scenario}")

    def _process_symbol(self, symbol: str, session) -> FinalSignal | None:
        if not is_tradeable_for(symbol, session):
            return None
        if not self._mt5 or not getattr(self._mt5, "connected", False):
            return None

        # Fetch bars and compute indicator bundles for all timeframes
        new_bundles: dict[str, IndicatorBundle] = {}
        for tf in TIMEFRAMES:
            df = self._fetch_bars(symbol, tf)
            if df is None:
                continue
            prev_ohlc = self._prev_ohlc.get(symbol, {})
            bundle = compute_bundle(
                symbol=symbol,
                timeframe=tf,
                df=df,
                prev_session_high=prev_ohlc.get("high", 0.0),
                prev_session_low=prev_ohlc.get("low", 0.0),
                prev_session_close=prev_ohlc.get("close", 0.0),
                prev_bb_width=self._prev_bb_width.get(f"{symbol}_{tf}", 0.0),
            )
            if bundle:
                new_bundles[tf] = bundle
                if bundle.bollinger:
                    self._prev_bb_width[f"{symbol}_{tf}"] = bundle.bollinger.width
                # Update correlation matrix
                if bundle.close > 0 and self._bundles.get(symbol, {}).get(tf):
                    prev_close = self._bundles[symbol][tf].close
                    if prev_close > 0:
                        pct_chg = (bundle.close - prev_close) / prev_close
                        self._corr.update(symbol, pct_chg)

        if not new_bundles:
            return None

        self._bundles.setdefault(symbol, {}).update(new_bundles)
        primary = new_bundles.get(PRIMARY_TF) or next(iter(new_bundles.values()))

        # Deep analysis on primary timeframe
        closes_series = self._get_close_series(symbol, PRIMARY_TF)
        highs_series  = self._get_high_series(symbol, PRIMARY_TF)
        lows_series   = self._get_low_series(symbol, PRIMARY_TF)

        macd_analysis = analyze_macd(closes_series, macro_scenario=self._scenario) if closes_series is not None else None
        bb_analysis   = analyze_bb(closes_series, highs_series, lows_series) if all(
            x is not None for x in [closes_series, highs_series, lows_series]
        ) else None

        # MTF confluence
        mtf_result = analyze_mtf(symbol, new_bundles, macro_scenario=self._scenario)

        # Scenario evaluation
        open_syms = list(self._risk.state.open_positions.keys())
        scenario_result = eval_scenario(
            symbol=symbol,
            macro=self.macro,
            calendar_blackout=self._calendar.is_blackout("USD"),
            spread_ok=True,     # TODO: check live spread from MT5
            indicator_direction=primary.macd.direction if primary.macd else "flat",
            volume_confirms=primary.weis_wave > 0 if hasattr(primary, "weis_wave") else True,
            open_position_symbols=open_syms,
            correlation_matrix=self._corr,
        )

        # Fair price
        fp = self._fair_prices.get(symbol)
        fair_price_val = fp.fair_price if fp else 0.0

        # Final signal
        return gen_signal(
            bundle=primary,
            macro=self.macro,
            scenario_result=scenario_result,
            mtf_result=mtf_result,
            macd_analysis=macd_analysis,
            bb_analysis=bb_analysis,
            calendar_blackout=self._calendar.is_blackout("USD"),
            spread_ok=True,
            fair_price=fair_price_val,
        )

    def _fetch_bars(self, symbol: str, tf: str):
        try:
            from src.mt5_bridge import TIMEFRAME_MAP
            import MetaTrader5 as mt5lib
            import pandas as pd
            tf_val = TIMEFRAME_MAP.get(tf, mt5lib.TIMEFRAME_M5)
            rates = mt5lib.copy_rates_from_pos(symbol, tf_val, 0, 200)
            if rates is None or len(rates) == 0:
                return None
            df = pd.DataFrame(rates)
            df.rename(columns={"tick_volume": "volume"}, inplace=True)
            return df
        except Exception as e:
            logger.debug(f"Fetch bars {symbol} {tf}: {e}")
            return None

    def _get_close_series(self, symbol: str, tf: str):
        import pandas as pd
        try:
            from src.mt5_bridge import TIMEFRAME_MAP
            import MetaTrader5 as mt5lib
            rates = mt5lib.copy_rates_from_pos(symbol, TIMEFRAME_MAP.get(tf, mt5lib.TIMEFRAME_M5), 0, 150)
            if rates is not None and len(rates) > 0:
                return pd.DataFrame(rates)["close"]
        except Exception:
            pass
        return None

    def _get_high_series(self, symbol: str, tf: str):
        import pandas as pd
        try:
            from src.mt5_bridge import TIMEFRAME_MAP
            import MetaTrader5 as mt5lib
            rates = mt5lib.copy_rates_from_pos(symbol, TIMEFRAME_MAP.get(tf, mt5lib.TIMEFRAME_M5), 0, 150)
            if rates is not None:
                return pd.DataFrame(rates)["high"]
        except Exception:
            pass
        return None

    def _get_low_series(self, symbol: str, tf: str):
        import pandas as pd
        try:
            from src.mt5_bridge import TIMEFRAME_MAP
            import MetaTrader5 as mt5lib
            rates = mt5lib.copy_rates_from_pos(symbol, TIMEFRAME_MAP.get(tf, mt5lib.TIMEFRAME_M5), 0, 150)
            if rates is not None:
                return pd.DataFrame(rates)["low"]
        except Exception:
            pass
        return None

    def _get_prev_close(self, symbol: str) -> float:
        try:
            from src.mt5_bridge import TIMEFRAME_MAP
            import MetaTrader5 as mt5lib
            rates = mt5lib.copy_rates_from_pos(symbol, TIMEFRAME_MAP["D1"], 1, 2)
            if rates and len(rates) >= 1:
                return float(rates[-1]["close"])
        except Exception:
            pass
        return 0.0

    def _build_state(self, ts: str, session, signals: list) -> dict:
        bench = self._benchmark.snapshot.to_summary() if self._benchmark else {}
        return {
            "ts": ts,
            "cycle_count": self._cycle,
            "session": session.primary,
            "tradeable": session.tradeable,
            "scenario": self._scenario,
            "macro": self.macro.to_dict(),
            "watchlist": self._watchlist,    # [{symbol, score, label, opp_threshold, perm_threshold, asset_class}]
            "perm_results": self._perm_results,
            "signals": [
                {
                    "symbol": s.symbol,
                    "timeframe": s.timeframe,
                    "signal": s.signal,
                    "confidence": s.confidence,
                    "lot_multiplier": s.lot_multiplier,
                    "entry": s.entry,
                    "sl_distance": s.sl_distance,
                    "tp_distance": s.tp_distance,
                    "mtf_confluence": s.mtf_confluence,
                    "bb_day_max": s.bb_day_max,
                    "bb_day_min": s.bb_day_min,
                    "total_score": s.total_score,
                    "decision": s.total_score_decision,
                    "mcs_n": s.mcs_n,
                    "bcs_n": s.bcs_n,
                    "hcs_n": s.hcs_n,
                    "ves": s.ves,
                    "es": s.es,
                    "cs": s.cs,
                    "rs": s.rs,
                    "rsi": getattr(s, "rsi", 50.0),
                    "rationale": s.rationale,
                }
                for s in signals
            ],
            "risk": {
                "blocked": self._risk.state.blocked,
                "blocked_reason": self._risk.state.blocked_reason,
                "open_positions": len(self._risk.state.open_positions),
                "daily_trades": self._risk.state.daily_trades,
                "daily_pnl": round(self._risk.state.daily_pnl, 2),
                "tier": self._risk.state.tier,
                "lot_multiplier": self.macro.lot_multiplier(),
            },
            "benchmark": bench,
            "scanner_metrics": self._metrics.snapshot(),
            "last_prep": self._last_prep,
            "dry_run": self._dry_run,
            "n_results": len(signals),
        }

    def _write_state(self, state: dict):
        try:
            STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
            STATE_PATH.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
            with open(HISTORY_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(state, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.error(f"State write error: {e}")
