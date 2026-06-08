"""
src/macro/macro_coordination.py — Macro Universe Gate (coordenador principal).

Agrega todos os daemons macro num único ponto de decisão:
  NewsGate          → blackout de eventos económicos
  YieldMonitor      → curva de yields (FRED)
  DXYBasket         → DXY sintético (Finnhub)
  CrossAssetMonitor → GOLD, Oil, SP500, BTC (Finnhub + MT5 inject)
  MacroRegimeEngine → regime global + multiplicadores por símbolo
  PolicyShockLayer  → choques por banco central

Ordem de prioridade:
  1. NewsGate block       → ciclo inteiro saltado
  2. PolicyShock          → redução/bloqueio por CB event
  3. MacroRegimeEngine    → regime global → mult por símbolo
  4. Yield + DXY          → já incorporados no RegimeEngine
"""
from __future__ import annotations

from dataclasses import dataclass, field

from src.macro.news_gate import NewsGate
from src.macro.yield_monitor import YieldMonitor
from src.macro.dxy_basket import DXYBasket
from src.macro.cross_asset_monitor import CrossAssetMonitor
from src.macro.regime_engine import MacroRegimeEngine, RegimeState
from src.macro.policy_shock import PolicyShockLayer


@dataclass
class MacroRegime:
    # News / calendar
    news_blocked:  bool
    news_event:    str

    # Yield curve
    yield_regime:  str       # "steep" | "flat" | "inverted"
    yield_mult:    float

    # DXY
    dxy_regime:    str       # "risk_off" | "neutral" | "risk_on"
    dxy_mult:      float

    # Legacy combined (yield × dxy) — kept for backwards compatibility
    combined_mult: float

    # Macro regime engine
    regime:              str    # "risk_on" | "risk_off" | "inflation" | "deflation" | "crisis" | "neutral"
    risk_on_score:       float
    risk_off_score:      float
    inflation_score:     float
    liquidity_score:     float
    global_macro_mult:   float  # regime-level global multiplier

    # Per-symbol multipliers (from RegimeEngine × PolicyShock)
    symbol_mults: dict[str, float] = field(default_factory=dict)

    # Cross-asset snapshot
    cross_asset: dict = field(default_factory=dict)

    def symbol_mult(self, symbol: str) -> float:
        """
        Final per-symbol macro multiplier.
        Combines: regime engine + policy shock.
        Minimum of the two (most restrictive wins).
        """
        regime_mult = self.symbol_mults.get(symbol, self.global_macro_mult)
        return round(regime_mult, 3)


class MacroUniverseGate:
    """
    Coordenador de todos os módulos macro.
    Daemons correm em threads separadas.
    evaluate() e symbol_mult() são zero-I/O (lêem da memória).
    """

    def __init__(self, keys: dict):
        finnhub = keys.get("FINNHUB_KEY", "")
        fred    = keys.get("FRED_KEY", "")

        self.news_gate      = NewsGate(finnhub_key=finnhub)
        self.yield_monitor  = YieldMonitor(fred_key=fred)
        self.dxy_basket     = DXYBasket(finnhub_key=finnhub)
        self.cross_asset    = CrossAssetMonitor(finnhub_key=finnhub)
        self.regime_engine  = MacroRegimeEngine()
        self.policy_shock   = PolicyShockLayer()

        self._last_regime: MacroRegime = self.evaluate()

    def start(self) -> None:
        self.news_gate.start()
        self.yield_monitor.start()
        self.dxy_basket.start()
        self.cross_asset.start()

    def stop(self) -> None:
        self.news_gate.stop()
        self.yield_monitor.stop()
        self.dxy_basket.stop()
        self.cross_asset.stop()

    def inject_mt5_prices(self, market: dict) -> None:
        """
        Called by AlphaEngine each cycle with latest MT5 market state.
        Maps instrument names to canonical cross-asset keys.
        """
        def _price(keys: list[str]) -> float:
            for k in keys:
                v = market.get(k, {})
                p = v.get("close", v.get("bid", 0)) if isinstance(v, dict) else 0
                if p and float(p) > 0:
                    return float(p)
            return 0.0

        self.cross_asset.inject_prices(
            gold   = _price(["GOLD"]),
            oil    = _price(["Brent", "LCrude"]),
            sp500  = _price(["Usa500", "USA500Jun26"]),
            nasdaq = _price(["UsaTec", "USAtec", "US100Jun26"]),
            btc    = _price(["BTCUSD"]),
        )

    def evaluate(self, from_vix: float = 15.0) -> MacroRegime:
        """
        Recomputes regime using latest daemon states.
        Called once per cycle by AlphaEngine after inject_mt5_prices().
        """
        # Recompute regime engine with latest data
        regime_state = self.regime_engine.update(
            dxy_zscore   = self.dxy_basket.state.zscore,
            yield_spread = self.yield_monitor.state.spread_10y_2y,
            vix          = from_vix,
            cross_asset  = self.cross_asset.state,
        )

        news   = self.news_gate.state
        yield_ = self.yield_monitor.state
        dxy    = self.dxy_basket.state

        y_mult = self.yield_monitor.risk_multiplier()
        d_mult = self.dxy_basket.risk_multiplier()

        # Apply PolicyShock to per-symbol mults
        symbol_mults = dict(regime_state.symbol_mults)
        if news.is_blocked and news.blocking_event:
            shock = self.policy_shock.get_symbol_mults(news.blocking_event, is_active=True)
            for sym, shock_mult in shock.symbol_mults.items():
                current = symbol_mults.get(sym, regime_state.global_mult())
                symbol_mults[sym] = round(min(current, shock_mult), 3)

        regime = MacroRegime(
            news_blocked       = news.is_blocked,
            news_event         = news.blocking_event,
            yield_regime       = yield_.curve_regime,
            yield_mult         = y_mult,
            dxy_regime         = dxy.regime,
            dxy_mult           = d_mult,
            combined_mult      = round(y_mult * d_mult, 4),
            regime             = regime_state.regime,
            risk_on_score      = regime_state.risk_on_score,
            risk_off_score     = regime_state.risk_off_score,
            inflation_score    = regime_state.inflation_score,
            liquidity_score    = regime_state.liquidity_score,
            global_macro_mult  = round(regime_state.global_mult(), 4),
            symbol_mults       = symbol_mults,
            cross_asset        = self.cross_asset.state.as_dict(),
        )
        self._last_regime = regime
        return regime
