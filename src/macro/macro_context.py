from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class MacroContext:
    """
    Estado macro consolidado. Unica fonte de verdade para decisoes de mercado.
    Actualizado por threads daemon independentes; lido em zero latencia pelo engine.
    """
    # --- VIX ---
    vix: float = 20.0
    vix_regime: str = "normal"          # normal | caution | alert | kill | panic
    vix_lot_mult: float = 1.0           # multiplicador de lote baseado em VIX

    # --- DXY ---
    dxy: float = 101.0
    dxy_prev: float = 101.0
    dxy_change_pct: float = 0.0
    dxy_regime: str = "neutral"         # risk_off | neutral | risk_on
    dxy_zscore: float = 0.0

    # --- Yield Curve ---
    us10y: float = 4.5
    us2y: float = 4.0
    us3m: float = 5.2
    spread_10y_2y: float = 0.5
    curve_regime: str = "flat"          # steep | flat | inverted
    yield_risk_mult: float = 1.0        # steep=1.0, flat=0.75, inverted=0.5

    # --- Commodities ---
    gold_price: float = 0.0             # XAU/USD spot
    gold_change_pct: float = 0.0
    wti_price: float = 0.0
    wti_change_pct: float = 0.0
    brent_price: float = 0.0
    brent_change_pct: float = 0.0

    # --- Fair Price (calculado por ativo) ---
    # chave: symbol, valor: dict com fair_price, delta_up, delta_down, channels
    fair_prices: dict = field(default_factory=dict)

    # --- News ---
    news_score: str = "neutral"         # bullish | neutral | bearish
    news_events_today: list = field(default_factory=list)
    high_impact_next_30m: bool = False  # evento alto impacto nos proximos 30min

    # --- Economic Indicators (ultimo valor publicado) ---
    cpi_yoy: float | None = None        # CPI year-over-year %
    gdp_qoq: float | None = None        # PIB quarter-over-quarter %
    payroll: int | None = None          # NFP (nonfarm payrolls)
    adp: int | None = None              # ADP employment
    pmi_manufacturing: float | None = None
    pmi_services: float | None = None

    # --- Carry Trade ---
    carry_trade_active: bool = False    # ADRs emergentes em alta + DXY fraco

    # --- Regime Global ---
    global_regime: str = "undefined"   # risk_on | risk_off | neutral | undefined
    tradeable: bool = True             # False se VIX kill ou panic

    # --- Timestamps ---
    updated_at: str = ""

    def refresh_timestamp(self):
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def recompute_global(self):
        """Calcula regime global e tradeable a partir das camadas macro."""
        # Kill imediato
        if self.vix_regime in ("kill", "panic"):
            self.tradeable = False
            self.global_regime = "risk_off"
            return

        self.tradeable = True
        scores = []
        # DXY
        if self.dxy_regime == "risk_off":
            scores.append(-1)
        elif self.dxy_regime == "risk_on":
            scores.append(1)
        else:
            scores.append(0)
        # Yield curve
        if self.curve_regime == "inverted":
            scores.append(-1)
        elif self.curve_regime == "steep":
            scores.append(1)
        else:
            scores.append(0)
        # VIX
        if self.vix_regime == "alert":
            scores.append(-1)
        elif self.vix_regime == "normal":
            scores.append(1)
        else:
            scores.append(0)
        # News
        if self.news_score == "bearish":
            scores.append(-1)
        elif self.news_score == "bullish":
            scores.append(1)
        else:
            scores.append(0)

        total = sum(scores)
        if total >= 2:
            self.global_regime = "risk_on"
        elif total <= -2:
            self.global_regime = "risk_off"
        else:
            self.global_regime = "neutral"

    def lot_multiplier(self) -> float:
        """Multiplicador final de lote: produto de VIX × yield curve."""
        return round(self.vix_lot_mult * self.yield_risk_mult, 4)

    def to_dict(self) -> dict:
        return {
            "vix": self.vix,
            "vix_regime": self.vix_regime,
            "dxy": self.dxy,
            "dxy_change_pct": round(self.dxy_change_pct, 4),
            "dxy_regime": self.dxy_regime,
            "curve_regime": self.curve_regime,
            "spread_10y_2y": self.spread_10y_2y,
            "gold": self.gold_price,
            "wti": self.wti_price,
            "news_score": self.news_score,
            "high_impact_next_30m": self.high_impact_next_30m,
            "global_regime": self.global_regime,
            "tradeable": self.tradeable,
            "lot_multiplier": self.lot_multiplier(),
            "updated_at": self.updated_at,
        }
