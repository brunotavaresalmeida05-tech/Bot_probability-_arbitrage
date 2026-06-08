from __future__ import annotations
"""
ScannerMetrics — Observabilidade do Opportunity-Permission Engine.

Recolhe eventos por ciclo (janela rolante de N ciclos) e agrega:
  - contagens por classe de activo e por timeframe
  - taxas de conversão (watchlist → execute)
  - scores médios (opp, perm, rs, es, atr_fit)
  - razões de bloqueio
  - top oportunidades e top rejeições actuais

Uso no orchestrator:
  metrics.record(opp, perm)   ← chamado para cada símbolo por ciclo
  metrics.end_cycle()         ← chamado no fim de cada ciclo
  metrics.snapshot()          ← chamado por _build_state() para serializar
"""
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Deque


# ── Janela rolante ────────────────────────────────────────────────────────────
WINDOW_CYCLES = 50   # últimos N ciclos para agregação


# ── Event por símbolo/ciclo ───────────────────────────────────────────────────

@dataclass
class ScanEvent:
    symbol:       str
    asset_class:  str
    timeframe:    str
    opp_score:    float
    opp_label:    str       # weak | watchlist | strong
    opp_threshold:float
    perm_score:   float
    perm_decision:str       # BLOCK | REDUCE | CONFIRM | EXECUTE
    perm_threshold:float
    cs:           float
    rs:           float
    es:           float
    atr_fit:      float
    blocked_reason: str


# ── Agregado por classe ou TF ─────────────────────────────────────────────────

@dataclass
class GroupStats:
    key:      str
    total:    int = 0
    watchlist:int = 0
    strong:   int = 0
    execute:  int = 0
    confirm:  int = 0
    reduce:   int = 0
    block:    int = 0
    _opp:   list = field(default_factory=list)
    _perm:  list = field(default_factory=list)
    _rs:    list = field(default_factory=list)
    _es:    list = field(default_factory=list)
    _atr:   list = field(default_factory=list)
    _reasons: dict = field(default_factory=dict)

    def add(self, ev: ScanEvent) -> None:
        self.total += 1
        if ev.opp_label in ("watchlist", "strong"):
            self.watchlist += 1
        if ev.opp_label == "strong":
            self.strong += 1
        if ev.perm_decision == "EXECUTE":
            self.execute += 1
        elif ev.perm_decision == "CONFIRM":
            self.confirm += 1
        elif ev.perm_decision == "REDUCE":
            self.reduce += 1
        else:
            self.block += 1
            if ev.blocked_reason:
                self._reasons[ev.blocked_reason] = self._reasons.get(ev.blocked_reason, 0) + 1

        self._opp.append(ev.opp_score)
        if ev.opp_label in ("watchlist", "strong"):
            self._perm.append(ev.perm_score)
            self._rs.append(ev.rs)
            self._es.append(ev.es)
            self._atr.append(ev.atr_fit)

    def _avg(self, lst: list) -> float:
        return round(sum(lst) / len(lst), 3) if lst else 0.0

    def to_dict(self) -> dict:
        return {
            "key":          self.key,
            "total":        self.total,
            "watchlist":    self.watchlist,
            "strong":       self.strong,
            "execute":      self.execute,
            "confirm":      self.confirm,
            "reduce":       self.reduce,
            "block":        self.block,
            "watchlist_rate": round(self.watchlist / self.total, 3) if self.total else 0.0,
            "execute_rate": round(self.execute / self.watchlist, 3) if self.watchlist else 0.0,
            "avg_opp_score":  self._avg(self._opp),
            "avg_perm_score": self._avg(self._perm),
            "avg_rs":  self._avg(self._rs),
            "avg_es":  self._avg(self._es),
            "avg_atr": self._avg(self._atr),
            "block_reasons": dict(sorted(self._reasons.items(), key=lambda x: -x[1])),
        }


# ── ScannerMetrics ────────────────────────────────────────────────────────────

class ScannerMetrics:
    """
    Janela rolante de WINDOW_CYCLES ciclos.
    Agrega eventos por classe e por timeframe.
    """

    def __init__(self) -> None:
        # Cada entrada da deque é uma lista de ScanEvents de um ciclo
        self._window: Deque[list[ScanEvent]] = deque(maxlen=WINDOW_CYCLES)
        self._current_cycle: list[ScanEvent] = []
        self._cycle_count: int = 0
        self._last_update: str = ""
        # Oportunidades e rejeições actuais (último ciclo)
        self._current_top_opps: list[dict] = []
        self._current_top_rejects: list[dict] = []

    def record(
        self,
        symbol:        str,
        asset_class:   str,
        timeframe:     str,
        opp_score:     float,
        opp_label:     str,
        opp_threshold: float,
        perm_score:    float,
        perm_decision: str,
        perm_threshold:float,
        cs:    float,
        rs:    float,
        es:    float,
        atr_fit: float,
        blocked_reason: str = "",
    ) -> None:
        ev = ScanEvent(
            symbol=symbol, asset_class=asset_class, timeframe=timeframe,
            opp_score=opp_score, opp_label=opp_label, opp_threshold=opp_threshold,
            perm_score=perm_score, perm_decision=perm_decision, perm_threshold=perm_threshold,
            cs=cs, rs=rs, es=es, atr_fit=atr_fit, blocked_reason=blocked_reason,
        )
        self._current_cycle.append(ev)

    def end_cycle(self, cycle_count: int = 0) -> None:
        self._window.append(self._current_cycle)
        self._cycle_count = cycle_count
        self._last_update = datetime.now(timezone.utc).isoformat()

        # Top oportunidades e rejeições do ciclo actual
        cur = self._current_cycle
        self._current_top_opps = sorted(
            [{"symbol": e.symbol, "class": e.asset_class, "tf": e.timeframe,
              "score": e.opp_score, "label": e.opp_label, "thr": e.opp_threshold}
             for e in cur if e.opp_label in ("watchlist", "strong")],
            key=lambda x: -x["score"]
        )[:8]

        self._current_top_rejects = sorted(
            [{"symbol": e.symbol, "class": e.asset_class, "tf": e.timeframe,
              "opp": e.opp_score, "perm": e.perm_score, "decision": e.perm_decision,
              "reason": e.blocked_reason or e.perm_decision,
              "rs": e.rs, "es": e.es, "atr": e.atr_fit}
             for e in cur if e.opp_label in ("watchlist", "strong") and e.perm_decision == "BLOCK"],
            key=lambda x: -x["opp"]
        )[:8]

        self._current_cycle = []

    def snapshot(self) -> dict:
        """Agrega todos os eventos na janela e devolve dict serializável."""
        all_events: list[ScanEvent] = [ev for cycle in self._window for ev in cycle]

        if not all_events:
            return {
                "cycles_observed": 0,
                "window_size": WINDOW_CYCLES,
                "by_class": {},
                "by_timeframe": {},
                "totals": {},
                "top_opportunities": [],
                "top_rejections": [],
                "last_update": self._last_update,
                "alerts": [],
            }

        # Agregar por classe
        by_class: dict[str, GroupStats] = defaultdict(lambda: GroupStats(key=""))
        for ev in all_events:
            if not by_class[ev.asset_class].key:
                by_class[ev.asset_class].key = ev.asset_class
            by_class[ev.asset_class].add(ev)

        # Agregar por TF
        by_tf: dict[str, GroupStats] = defaultdict(lambda: GroupStats(key=""))
        for ev in all_events:
            if not by_tf[ev.timeframe].key:
                by_tf[ev.timeframe].key = ev.timeframe
            by_tf[ev.timeframe].add(ev)

        # Totais globais
        total_ev   = len(all_events)
        watchlist  = sum(1 for e in all_events if e.opp_label in ("watchlist", "strong"))
        strong     = sum(1 for e in all_events if e.opp_label == "strong")
        execute    = sum(1 for e in all_events if e.perm_decision == "EXECUTE")
        block      = sum(1 for e in all_events if e.perm_decision == "BLOCK")

        opp_scores  = [e.opp_score  for e in all_events]
        perm_scores = [e.perm_score for e in all_events if e.opp_label in ("watchlist","strong")]
        rs_vals     = [e.rs         for e in all_events if e.opp_label in ("watchlist","strong")]
        es_vals     = [e.es         for e in all_events if e.opp_label in ("watchlist","strong")]

        def avg(lst: list) -> float:
            return round(sum(lst)/len(lst), 3) if lst else 0.0

        totals = {
            "total_scanned": total_ev,
            "watchlist":     watchlist,
            "strong":        strong,
            "execute":       execute,
            "block":         block,
            "watchlist_rate": round(watchlist / total_ev, 3) if total_ev else 0.0,
            "execute_rate":  round(execute / watchlist, 3) if watchlist else 0.0,
            "avg_opp_score": avg(opp_scores),
            "avg_perm_score":avg(perm_scores),
            "avg_rs":        avg(rs_vals),
            "avg_es":        avg(es_vals),
        }

        # Alertas automáticos
        alerts = _generate_alerts(totals, by_class)

        return {
            "cycles_observed": len(self._window),
            "window_size":     WINDOW_CYCLES,
            "by_class":     {k: v.to_dict() for k, v in sorted(by_class.items())},
            "by_timeframe": {k: v.to_dict() for k, v in sorted(by_tf.items())},
            "totals":       totals,
            "top_opportunities": self._current_top_opps,
            "top_rejections":   self._current_top_rejects,
            "last_update":  self._last_update,
            "alerts":       alerts,
        }


# ── Alertas automáticos ───────────────────────────────────────────────────────

def _generate_alerts(totals: dict, by_class: dict) -> list[dict]:
    alerts = []

    wl_rate = totals.get("watchlist_rate", 0)
    ex_rate = totals.get("execute_rate", 0)
    avg_rs  = totals.get("avg_rs", 0)
    avg_es  = totals.get("avg_es", 0)

    # Amarelo: muita watchlist, pouca execução
    if wl_rate > 0.4 and ex_rate < 0.05:
        alerts.append({
            "level": "yellow",
            "msg": f"Alta watchlist_rate={wl_rate:.0%} mas execute_rate={ex_rate:.0%} — PermissionScore demasiado exigente?",
        })

    # Amarelo: oportunidades fortes sem conversão
    strong = totals.get("strong", 0)
    execute = totals.get("execute", 0)
    if strong > 5 and execute == 0:
        alerts.append({
            "level": "yellow",
            "msg": f"{strong} oportunidades 'strong' sem nenhum EXECUTE — verificar CS e ATRFit",
        })

    # Vermelho: RS alto com execuções
    if avg_rs > 0.6 and execute > 0:
        alerts.append({
            "level": "red",
            "msg": f"RS médio={avg_rs:.2f} elevado mas há EXECUTEs — risco não está a bloquear correctamente",
        })

    # Vermelho: ES alto com execuções
    if avg_es > 0.65 and execute > 0:
        alerts.append({
            "level": "red",
            "msg": f"ES médio={avg_es:.2f} elevado — bot pode estar a entrar em movimentos exaustos",
        })

    # Amarelo por classe: alguma classe completamente bloqueada
    for cls, gs_dict in by_class.items():
        if isinstance(gs_dict, GroupStats):
            gs = gs_dict
        else:
            continue
        if gs.watchlist >= 5 and gs.execute == 0:
            alerts.append({
                "level": "yellow",
                "msg": f"Classe '{cls}': {gs.watchlist} watchlist mas 0 execuções — threshold demasiado apertado?",
            })

    return alerts
