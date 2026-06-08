from __future__ import annotations
"""
6-Step Market Preparation Workflow — V9

Runs at each session open (London 08:00 UTC, NY 13:00 UTC).
Also runs on significant news events.

Steps:
  1. News reading       — classify macro news: BOM / NEUTRO / MAU
  2. Index analysis     — key indices current state
  3. Economic agenda    — upcoming events and their expected impact
  4. Calculations       — fair price + delta volatility per asset
  5. Scenario evaluation — Alta / Baixa / Indefinido / Sem volatilidade
  6. Chart projection   — project calculations onto price chart (logged)
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from src.macro.macro_context import MacroContext
from src.analysis.fair_price import FairPriceResult

logger = logging.getLogger(__name__)


@dataclass
class PrepReport:
    session: str
    timestamp: str = ""

    # Step 1
    news_classification: str = "neutral"    # bullish | neutral | bearish
    news_summary: list[str] = field(default_factory=list)

    # Step 2
    indices_state: dict = field(default_factory=dict)

    # Step 3
    agenda_events: list[dict] = field(default_factory=list)
    high_impact_today: bool = False

    # Step 4
    fair_prices: dict[str, Any] = field(default_factory=dict)   # symbol -> FairPriceResult.to_dict()

    # Step 5
    scenario: str = "indefinido"            # alta | baixa | indefinido | sem_volatilidade
    scenario_rationale: list[str] = field(default_factory=list)

    # Step 6
    chart_projections: dict = field(default_factory=dict)       # symbol -> key levels

    def to_dict(self) -> dict:
        return {
            "session": self.session,
            "timestamp": self.timestamp,
            "step1_news": self.news_classification,
            "step2_indices": self.indices_state,
            "step3_agenda": {
                "high_impact_today": self.high_impact_today,
                "events_count": len(self.agenda_events),
            },
            "step4_fair_prices": self.fair_prices,
            "step5_scenario": {
                "verdict": self.scenario,
                "rationale": self.scenario_rationale,
            },
            "step6_key_levels": self.chart_projections,
        }


class PrepWorkflow:
    """Executes the 6-step market preparation for a session."""

    def __init__(self, macro: MacroContext):
        self._macro = macro

    def run(
        self,
        session_name: str,
        fair_price_results: dict[str, FairPriceResult],
        agenda_events: list[dict] | None = None,
    ) -> PrepReport:
        report = PrepReport(
            session=session_name,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        self._step1_news(report)
        self._step2_indices(report)
        self._step3_agenda(report, agenda_events or [])
        self._step4_calculations(report, fair_price_results)
        self._step5_scenario(report)
        self._step6_chart_projection(report, fair_price_results)

        logger.info(
            f"[PREP {session_name}] scenario={report.scenario} "
            f"news={report.news_classification} "
            f"vix={self._macro.vix:.1f} dxy_regime={self._macro.dxy_regime}"
        )
        return report

    def _step1_news(self, report: PrepReport):
        report.news_classification = self._macro.news_score
        report.news_summary = [
            f"VIX={self._macro.vix:.1f} ({self._macro.vix_regime})",
            f"DXY regime={self._macro.dxy_regime} chg={self._macro.dxy_change_pct*100:.2f}%",
            f"Yield curve={self._macro.curve_regime} spread={self._macro.spread_10y_2y:.2f}pp",
            f"Global regime={self._macro.global_regime}",
        ]

    def _step2_indices(self, report: PrepReport):
        report.indices_state = {
            "vix": {"value": self._macro.vix, "regime": self._macro.vix_regime},
            "dxy": {
                "value": self._macro.dxy,
                "change_pct": round(self._macro.dxy_change_pct * 100, 3),
                "regime": self._macro.dxy_regime,
            },
            "gold": {"price": self._macro.gold_price, "change_pct": round(self._macro.gold_change_pct * 100, 3)},
            "wti": {"price": self._macro.wti_price, "change_pct": round(self._macro.wti_change_pct * 100, 3)},
            "brent": {"price": self._macro.brent_price, "change_pct": round(self._macro.brent_change_pct * 100, 3)},
            "yield_curve": {
                "us10y": self._macro.us10y,
                "us2y": self._macro.us2y,
                "spread": self._macro.spread_10y_2y,
                "regime": self._macro.curve_regime,
            },
        }

    def _step3_agenda(self, report: PrepReport, events: list[dict]):
        report.agenda_events = events
        report.high_impact_today = any(e.get("impact") == "high" for e in events)
        report.high_impact_today = report.high_impact_today or self._macro.high_impact_next_30m

    def _step4_calculations(self, report: PrepReport, fair_prices: dict[str, FairPriceResult]):
        for sym, fp in fair_prices.items():
            report.fair_prices[sym] = fp.to_dict()

    def _step5_scenario(self, report: PrepReport):
        rationale = []

        # Collect directional signals
        signals = []

        if self._macro.vix_regime in ("kill", "panic"):
            report.scenario = "sem_volatilidade"
            report.scenario_rationale = ["VIX kill/panic: sem operacoes"]
            return

        if self._macro.dxy_regime == "risk_off":
            signals.append(-1)
            rationale.append("DXY risk_off: USD forte, pressao baixista em activos de risco")
        elif self._macro.dxy_regime == "risk_on":
            signals.append(1)
            rationale.append("DXY risk_on: USD fraco, fluxo para activos de risco")

        if self._macro.curve_regime == "inverted":
            signals.append(-1)
            rationale.append("Yield curve invertida: sinal de recessao")
        elif self._macro.curve_regime == "steep":
            signals.append(1)
            rationale.append("Yield curve steep: expansao economica")

        if self._macro.news_score == "bearish":
            signals.append(-1)
            rationale.append("Noticias negativas: pressao baixista")
        elif self._macro.news_score == "bullish":
            signals.append(1)
            rationale.append("Noticias positivas: pressao altista")

        if self._macro.vix_regime == "alert":
            signals.append(-1)
            rationale.append("VIX elevado: mercado em alerta, cautela maxima")
        elif self._macro.vix_regime == "normal":
            signals.append(1)
            rationale.append("VIX normal: condicoes de mercado estaveis")

        if self._macro.high_impact_next_30m:
            rationale.append("ATENCAO: evento de alto impacto nos proximos 30min")

        total = sum(signals)
        if total >= 2:
            report.scenario = "alta"
        elif total <= -2:
            report.scenario = "baixa"
        elif abs(total) <= 1:
            report.scenario = "indefinido"

        # No volatility if BB all contracting and VIX low
        if self._macro.vix < 12:
            report.scenario = "sem_volatilidade"
            rationale.append("VIX muito baixo: mercado sem volatilidade significativa")

        report.scenario_rationale = rationale

    def _step6_chart_projection(self, report: PrepReport, fair_prices: dict[str, FairPriceResult]):
        for sym, fp in fair_prices.items():
            report.chart_projections[sym] = {
                "fair_price": round(fp.fair_price, 5),
                "delta": round(fp.delta, 5),
                "resistance_1": round(fp.channels_up[2], 5) if len(fp.channels_up) > 2 else 0,
                "resistance_2": round(fp.channels_up[4], 5) if len(fp.channels_up) > 4 else 0,
                "support_1": round(fp.channels_down[2], 5) if len(fp.channels_down) > 2 else 0,
                "support_2": round(fp.channels_down[4], 5) if len(fp.channels_down) > 4 else 0,
                "bb_max": round(fp.bb_max, 5),
                "bb_min": round(fp.bb_min, 5),
            }
