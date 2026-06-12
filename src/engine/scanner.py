from __future__ import annotations
"""
Scanner — Opportunity-Permission Engine com calibração dinâmica.

Pipeline:
  get_thresholds()    → thresholds calibrados por TF + classe + volatilidade
  compute_opportunity_score() → score + label (usa threshold calibrado)
  compute_permission_score()  → BLOCK | REDUCE | CONFIRM | EXECUTE
  scan()              → lista ordenada, filtrada por threshold individual

Calibração:
  Threshold_opp(asset,tf)  = BaseOpp_tf  + AdjOpp_class  + AdjOpp_vol
  Threshold_perm(asset,tf) = BasePerm_tf + AdjPerm_class + AdjPerm_risk
"""

from dataclasses import dataclass, field

import numpy as np

from src.technical.indicators import IndicatorBundle


# ── Pesos (fixos) ─────────────────────────────────────────────────────────────

# OpportunityScore = a1*MCS + a2*BCS + a3*VES - a4*ES
# Max teórico ≈ 0.60 (soma pesos positivos)
_OPP_WEIGHTS = (0.30, 0.25, 0.25, 0.20)

# PermissionScore = b1*CS - b2*RS - b3*ES + b4*ATRFit
# Max teórico ≈ 0.55 (soma pesos positivos)
_PERM_WEIGHTS = (0.45, 0.30, 0.15, 0.10)


# ── Thresholds base por timeframe ─────────────────────────────────────────────
# Opp: TF curto → threshold mais baixo (reconhece cedo), TF longo → mais alto (precisa estrutura)
# Perm: TF curto → mais apertado (ruído), TF longo → mais estável

_OPP_BASE_TF: dict[str, float] = {
    "M1":  0.26,
    "M3":  0.30,
    "M5":  0.34,
    "M10": 0.37,
    "M15": 0.39,
    "M30": 0.43,
    "H1":  0.47,
}

_PERM_BASE_TF: dict[str, float] = {
    "M1":  0.18,
    "M3":  0.21,
    "M5":  0.24,
    "M10": 0.26,
    "M15": 0.27,
    "M30": 0.31,
    "H1":  0.33,
}

# ── Ajuste por classe de activo [opp_adj, perm_adj] ──────────────────────────
# perm_adj negativo = threshold mais baixo = mais fácil executar.
# forex: reduzido -0.04 (era 0.00) — watchlist nunca convertia em EXECUTE
# gold:  reduzido -0.04 (era +0.03) — idem; gold tem ES=0 e RS baixo; bloqueio era excessivo
# indices/oil/crypto: conservadores — mantidos

_CLASS_ADJ: dict[str, tuple[float, float]] = {
    "forex":      ( 0.00, -0.04),   # era 0.00
    "indices":    ( 0.03, -0.02),   # inalterado
    "gold":       ( 0.02, -0.01),   # era +0.03
    "oil":        ( 0.00,  0.04),   # inalterado
    "treasuries": ( 0.04,  0.04),   # inalterado
    "crypto":     (-0.04,  0.05),   # inalterado
    "unknown":    ( 0.00,  0.00),   # inalterado
}

# ── Ajuste por sessão de mercado (aplicado ao perm_threshold) ─────────────────
# London/NY overlap: threshold mais permissivo — maior liquidez, sinal mais limpo
# Asia/Sydney:       threshold mais apertado — baixa liquidez, ruído estrutural
_SESSION_PERM_ADJ: dict[str, float] = {
    "london_ny_overlap": -0.02,   # melhor sessão
    "london":            -0.01,   # boa sessão
    "new_york":           0.00,   # base
    "asia":              +0.05,   # baixa liquidez
    "sydney":            +0.06,   # muito baixa liquidez
}

# ── Vetos de risco (independentes dos thresholds) ────────────────────────────
RISK_BLOCK_THRESHOLD       = 0.80
EXHAUSTION_BLOCK_THRESHOLD = 0.70

# ── RSI zones ─────────────────────────────────────────────────────────────────
# Momentum zone: RSI 55-75 (longs em tendência) ou 25-45 (shorts em tendência)
# Extremo forte:  RSI >80 ou <20 — exaustão iminente
# Extremo moderado: RSI >75 ou <25
# Neutro: RSI 45-55 — default 50.0 = sem efeito
_RSI_EXTREME_STRONG  = (80.0, 20.0)
_RSI_EXTREME_MOD     = (75.0, 25.0)
_RSI_MOMENTUM_HIGH   = (55.0, 70.0)   # zona momentum longs
_RSI_MOMENTUM_LOW    = (30.0, 45.0)   # zona momentum shorts

# ── Labels por oportunidade ───────────────────────────────────────────────────
# "strong"   = score >= opp_threshold * 1.30  (30% acima do threshold calibrado)
# "watchlist"= score >= opp_threshold
# "weak"     = abaixo do threshold
_STRONG_MULTIPLIER = 1.30


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class CalibrationResult:
    """Thresholds calibrados para um asset/TF específico."""
    asset_class:    str
    timeframe:      str
    opp_threshold:  float   # score mínimo para entrar na watchlist
    perm_threshold: float   # score mínimo para EXECUTE
    opp_base:       float
    perm_base:      float
    adj_class_opp:  float
    adj_class_perm: float
    adj_vol:        float
    adj_risk:       float
    adj_session:    float = 0.0   # ajuste por sessão de mercado


@dataclass
class OpportunityResult:
    symbol:            str
    timeframe:         str
    asset_class:       str
    opportunity_score: float
    opportunity_label: str          # "weak" | "watchlist" | "strong"
    opp_threshold:     float        # threshold usado para este ativo/TF
    perm_threshold:    float        # threshold de permissão para este ativo/TF
    mcs:  float = 0.0
    bcs:  float = 0.0
    ves:  float = 0.0
    es:   float = 0.0
    notes: list[str] = field(default_factory=list)


@dataclass
class PermissionResult:
    symbol:           str
    timeframe:        str
    decision:         str           # "BLOCK" | "REDUCE" | "CONFIRM" | "EXECUTE"
    permission_score: float
    perm_threshold:   float         # threshold calibrado usado
    cs:       float = 0.0
    rs:       float = 0.0
    es:       float = 0.0
    atr_fit:  float = 0.0
    blocked_reason: str = ""


# ── Calibração ────────────────────────────────────────────────────────────────

def get_thresholds(
    asset_class: str,
    timeframe:   str,
    vix:         float = 20.0,
    rs:          float = 0.0,
    session:     str   = "new_york",
) -> CalibrationResult:
    """
    Calcula thresholds calibrados para um asset/TF/sessão.

    Opp_threshold  = BaseOpp_tf  + AdjOpp_class  + AdjOpp_vol
    Perm_threshold = BasePerm_tf + AdjPerm_class + AdjPerm_risk + AdjPerm_session

    VIX alto   → sobe opp threshold (mais ruído = precisa mais qualidade)
    RS alto    → sobe perm threshold (mais risco = permissão mais apertada)
    Session    → London/NY abre; Asia fecha (liquidez estrutural)
    """
    opp_base  = _OPP_BASE_TF.get(timeframe,  _OPP_BASE_TF["M15"])
    perm_base = _PERM_BASE_TF.get(timeframe, _PERM_BASE_TF["M15"])

    adj_opp_class, adj_perm_class = _CLASS_ADJ.get(asset_class, (0.0, 0.0))

    # Adj_vol: VIX elevado → mais ruído → threshold opp sobe
    if vix >= 35:
        adj_vol = 0.06
    elif vix >= 30:
        adj_vol = 0.04
    elif vix >= 25:
        adj_vol = 0.02
    elif vix >= 20:
        adj_vol = 0.01
    else:
        adj_vol = 0.0

    # Adj_risk: RS elevado → entrada mais apertada
    if rs >= 0.7:
        adj_risk = 0.07
    elif rs >= 0.5:
        adj_risk = 0.04
    elif rs >= 0.3:
        adj_risk = 0.02
    else:
        adj_risk = 0.0

    # Adj_session: liquidez estrutural por sessão
    adj_session = _SESSION_PERM_ADJ.get(session, 0.0)

    opp_threshold  = round(opp_base  + adj_opp_class  + adj_vol,                       3)
    perm_threshold = round(perm_base + adj_perm_class + adj_risk + adj_session,         3)

    return CalibrationResult(
        asset_class=asset_class,
        timeframe=timeframe,
        opp_threshold=opp_threshold,
        perm_threshold=perm_threshold,
        opp_base=opp_base,
        perm_base=perm_base,
        adj_class_opp=adj_opp_class,
        adj_class_perm=adj_perm_class,
        adj_vol=adj_vol,
        adj_risk=adj_risk,
        adj_session=adj_session,
    )


# ── RSI helpers ───────────────────────────────────────────────────────────────

def _rsi_opp_adj(rsi: float, weight: float = 1.0) -> float:
    """
    Ajuste ao OpportunityScore baseado na zona de RSI × peso de calibração.

    rsi=50.0 (neutro por defeito) → 0.0 (sem efeito, compatibilidade total).
    weight=1.0 → efeito total; weight=0.0 → RSI desligado nesta classe/TF/regime.

    Zona momentum (30-45 ou 55-70): +0.02 × weight
    Extremo moderado (>75 ou <25):  -0.03 × weight
    Extremo forte (>80 ou <20):     -0.06 × weight
    """
    if weight <= 0.0:
        return 0.0
    if rsi >= _RSI_EXTREME_STRONG[0] or rsi <= _RSI_EXTREME_STRONG[1]:
        base = -0.06
    elif rsi >= _RSI_EXTREME_MOD[0] or rsi <= _RSI_EXTREME_MOD[1]:
        base = -0.03
    elif ((_RSI_MOMENTUM_HIGH[0] <= rsi <= _RSI_MOMENTUM_HIGH[1]) or
            (_RSI_MOMENTUM_LOW[0] <= rsi <= _RSI_MOMENTUM_LOW[1])):
        base = +0.02
    else:
        base = 0.0   # zona neutra 45-55
    return base * weight


def _rsi_perm_penalty(rsi: float, weight: float = 1.0) -> float:
    """
    Penalidade adicional ao RS no PermissionScore × peso de calibração.
    weight=0.0 → RSI desligado: sem penalidade independente do valor RSI.
    """
    if weight <= 0.0:
        return 0.0
    if rsi >= _RSI_EXTREME_STRONG[0] or rsi <= _RSI_EXTREME_STRONG[1]:
        base = 0.15
    elif rsi >= _RSI_EXTREME_MOD[0] or rsi <= _RSI_EXTREME_MOD[1]:
        base = 0.07
    else:
        base = 0.0
    return base * weight


# ── OpportunityScore ──────────────────────────────────────────────────────────

def compute_opportunity_score(
    mcs: float,
    bcs: float,
    ves: float,
    es:  float,
    opp_threshold: float = 0.33,
    rsi:        float = 50.0,
    rsi_weight: float = 1.0,
) -> tuple[float, str]:
    """
    OpportunityScore = a1*MCS + a2*BCS + a3*VES - a4*ES + rsi_adj*rsi_weight

    rsi=50.0 → sem efeito (neutro, retrocompatível).
    rsi_weight=0.0 → RSI desligado (política de calibração).
    rsi_weight=1.0 → efeito total (padrão).

    Label calibrado:
      >= opp_threshold * STRONG_MULT → "strong"
      >= opp_threshold               → "watchlist"
      <  opp_threshold               → "weak"
    """
    a1, a2, a3, a4 = _OPP_WEIGHTS
    raw   = a1 * mcs + a2 * bcs + a3 * ves - a4 * es + _rsi_opp_adj(rsi, rsi_weight)
    score = float(np.clip(raw, 0.0, 1.0))

    strong_thr = opp_threshold * _STRONG_MULTIPLIER
    if score >= strong_thr:
        label = "strong"
    elif score >= opp_threshold:
        label = "watchlist"
    else:
        label = "weak"

    return score, label


# ── ATRFit ────────────────────────────────────────────────────────────────────

def calc_atr_fit(bundle: IndicatorBundle, fair_price: float = 0.0) -> float:
    """
    ATRFit: mede se o ATR actual cabe dentro do range esperado.
    1.0 = stop cabe perfeitamente. 0.0 = ATR excessivo para o range.
    """
    atr = bundle.atr
    if atr <= 0 or bundle.close <= 0:
        return 0.5

    if fair_price > 0:
        expected_range = abs(bundle.close - fair_price)
        if expected_range > 0:
            ratio = atr / expected_range
            return float(np.clip(1.0 - (ratio - 1.0) * 0.5, 0.0, 1.0))

    atr_pct = atr / bundle.close
    if atr_pct < 0.003:   return 0.90
    elif atr_pct < 0.010: return 0.70
    elif atr_pct < 0.020: return 0.50
    else:
        return float(np.clip(0.5 - (atr_pct - 0.020) * 10, 0.0, 0.5))


# ── PermissionScore ───────────────────────────────────────────────────────────

def compute_permission_score(
    cs:             float,
    rs:             float,
    es:             float,
    atr_fit:        float,
    blackout:       bool  = False,
    perm_threshold: float = 0.27,
    rsi:            float = 50.0,
    rsi_weight:     float = 1.0,
) -> PermissionResult:
    """
    PermissionScore = b1*CS - b2*RS_eff - b3*ES + b4*ATRFit

    RS_eff = RS + rsi_perm_penalty(rsi) * rsi_weight
    rsi_weight=0.0 → sem penalidade RSI (RSI desligado por política de calibração).

    CONFIRM = perm_threshold * 0.70
    REDUCE  = perm_threshold * 0.40
    """
    b1, b2, b3, b4 = _PERM_WEIGHTS
    rs_eff = min(rs + _rsi_perm_penalty(rsi, rsi_weight), 1.0)
    raw    = b1 * cs - b2 * rs_eff - b3 * es + b4 * atr_fit
    score  = float(np.clip(raw, 0.0, 1.0))

    if blackout:
        return PermissionResult("", "", "BLOCK", score, perm_threshold,
                                cs, rs, es, atr_fit, blocked_reason="blackout_event")

    if rs_eff > RISK_BLOCK_THRESHOLD:
        reason = f"RS_eff={rs_eff:.2f}>veto" + (f" (rsi={rsi:.1f})" if _rsi_perm_penalty(rsi) > 0 else "")
        return PermissionResult("", "", "BLOCK", score, perm_threshold,
                                cs, rs, es, atr_fit, blocked_reason=reason)

    if es > EXHAUSTION_BLOCK_THRESHOLD:
        return PermissionResult("", "", "BLOCK", score, perm_threshold,
                                cs, rs, es, atr_fit, blocked_reason=f"ES={es:.2f}>veto")

    confirm_thr = perm_threshold * 0.70
    reduce_thr  = perm_threshold * 0.40

    if score >= perm_threshold and rs_eff <= 0.50 and es <= EXHAUSTION_BLOCK_THRESHOLD:
        decision = "EXECUTE"
    elif score >= confirm_thr:
        decision = "CONFIRM"
    elif score >= reduce_thr:
        decision = "REDUCE"
    else:
        decision = "BLOCK"

    return PermissionResult("", "", decision, score, perm_threshold,
                            cs, rs, es, atr_fit)


# ── scan() ────────────────────────────────────────────────────────────────────

def scan(opportunities: list[OpportunityResult]) -> list[OpportunityResult]:
    """
    Filtra por threshold individual de cada oportunidade e ordena por score.
    Cada OpportunityResult usa o seu próprio opp_threshold calibrado.
    """
    active = [o for o in opportunities if o.opportunity_score >= o.opp_threshold]
    return sorted(active, key=lambda x: x.opportunity_score, reverse=True)


def build_opportunity(
    symbol:       str,
    timeframe:    str,
    bundle:       IndicatorBundle | None,
    mcs:          float,
    bcs:          float,
    ves:          float,
    es:           float,
    asset_class:  str = "unknown",
    vix:          float = 20.0,
    rs:           float = 0.0,
    rsi:          float = 50.0,
    vol_regime:   str = "normal",
    session:      str = "new_york",
    notes:        list[str] | None = None,
) -> OpportunityResult:
    """
    Constrói OpportunityResult com thresholds calibrados para este asset/TF/sessão.

    rsi=50.0 (neutro por defeito) → sem efeito no score.
    vol_regime determina o peso RSI via RSICalibrationPolicy.
    session determina adj_session no perm_threshold.
    """
    from src.engine.rsi_calibration import get_policy
    rsi_weight = get_policy().get_weight(asset_class, timeframe, vol_regime)

    cal   = get_thresholds(asset_class, timeframe, vix=vix, rs=rs, session=session)
    score, label = compute_opportunity_score(mcs, bcs, ves, es,
                                              opp_threshold=cal.opp_threshold,
                                              rsi=rsi,
                                              rsi_weight=rsi_weight)

    rsi_note = f"rsi={rsi:.1f} w={rsi_weight:.2f}" if rsi != 50.0 else ""
    base_note = f"cal={cal.opp_threshold:.3f}/{cal.perm_threshold:.3f}"
    return OpportunityResult(
        symbol=symbol,
        timeframe=timeframe,
        asset_class=asset_class,
        opportunity_score=round(score, 4),
        opportunity_label=label,
        opp_threshold=cal.opp_threshold,
        perm_threshold=cal.perm_threshold,
        mcs=round(mcs, 4),
        bcs=round(bcs, 4),
        ves=round(ves, 4),
        es=round(es, 4),
        notes=notes or ([base_note, rsi_note] if rsi_note else [base_note]),
    )
