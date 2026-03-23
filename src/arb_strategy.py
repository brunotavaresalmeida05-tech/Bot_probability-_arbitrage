"""
src/arb_strategy.py
Motor de Probability Arbitrage com teste de cointegração ADF.

Melhorias vs versão anterior:
- Teste ADF para verificar estacionariedade do spread antes de negociar
- Half-life da reversão: filtra pares com reversão demasiado lenta
- Hedge ratio re-estimado com janela rolante
- Score de qualidade por par (ADF p-value + half-life + correlação)
"""

import pandas as pd
import numpy as np
from typing import Optional, Tuple
from itertools import combinations
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import config.settings as cfg
import src.external_data as ext

ARB_Z_ENTER  = cfg.ARB_Z_ENTER
ARB_Z_EXIT   = cfg.ARB_Z_EXIT
ARB_Z_STOP   = cfg.ARB_Z_STOP
MIN_CORR     = cfg.ARB_MIN_CORRELATION
SPREAD_WIN   = 50
CORR_WIN     = 60

# Máximo half-life aceitável (barras) — spread demora muito → não é stat arb
MAX_HALF_LIFE_BARS = 30

# p-value máximo ADF para aceitar estacionariedade
ADF_PVALUE_THRESHOLD = 0.10


# ═══════════════════════════════════════════════════════════════
#  TESTE ADF (Augmented Dickey-Fuller)
#  Testa se o spread é estacionário (volta à média)
#  H0: série tem raiz unitária (não estacionária)
#  Queremos rejeitar H0 → p-value baixo → spread é estacionário
# ═══════════════════════════════════════════════════════════════

def adf_test(series: pd.Series, max_lags: int = 5) -> dict:
    """
    ADF test implementado sem scipy (apenas numpy).
    Versão simplificada mas funcional.

    Retorna:
        adf_stat:  estatística do teste (mais negativo = mais estacionário)
        p_value:   p-value aproximado
        is_stationary: True se p_value < ADF_PVALUE_THRESHOLD
    """
    series = series.dropna()
    n = len(series)

    if n < 20:
        return {"adf_stat": 0.0, "p_value": 1.0, "is_stationary": False}

    # Diferença e lag
    y   = series.diff().dropna().values
    x   = series.shift(1).dropna().values[:len(y)]

    # Adicionar lags de dy (ADF vs DF simples)
    lags = min(max_lags, int(np.floor(12 * (n / 100) ** 0.25)))
    X    = [x]
    for lag in range(1, lags + 1):
        dy_lag = series.diff().shift(lag).dropna().values
        min_len = min(len(y), len(dy_lag))
        X.append(dy_lag[:min_len])
    y   = y[:min(len(yi) for yi in X)]
    X   = np.column_stack([xi[:len(y)] for xi in X])

    # OLS
    try:
        beta = np.linalg.lstsq(X, y, rcond=None)[0]
        y_hat = X @ beta
        resid = y - y_hat
        se_sq = resid.var() / (len(y) - X.shape[1])
        cov   = se_sq * np.linalg.inv(X.T @ X)
        se_beta0 = np.sqrt(abs(cov[0, 0]))
        adf_stat = beta[0] / se_beta0 if se_beta0 > 0 else 0.0
    except Exception:
        return {"adf_stat": 0.0, "p_value": 1.0, "is_stationary": False}

    # Aproximação do p-value baseada em valores críticos de MacKinnon
    # (tabela simplificada para n >= 25)
    # Valores críticos aproximados: 1%=-3.43, 5%=-2.86, 10%=-2.57
    critical_values = {
        0.01: -3.43,
        0.05: -2.86,
        0.10: -2.57,
    }

    if adf_stat < critical_values[0.01]:
        p_value = 0.01
    elif adf_stat < critical_values[0.05]:
        p_value = 0.05
    elif adf_stat < critical_values[0.10]:
        p_value = 0.10
    else:
        # Interpolação linear aproximada
        p_value = min(1.0, 0.10 + (adf_stat - critical_values[0.10]) * 0.05)
        p_value = max(0.10, p_value)

    return {
        "adf_stat":      round(float(adf_stat), 4),
        "p_value":       round(float(p_value), 4),
        "is_stationary": p_value <= ADF_PVALUE_THRESHOLD,
        "n_obs":         n,
        "n_lags":        lags,
    }


# ═══════════════════════════════════════════════════════════════
#  HALF-LIFE DA REVERSÃO
#  Estima quantas barras o spread demora a voltar a metade do desvio
#  Fórmula: spread_t = α + β * spread_{t-1} + ε
#  half_life = -ln(2) / ln(β)
# ═══════════════════════════════════════════════════════════════

def compute_half_life(spread: pd.Series) -> Optional[float]:
    """
    Estima o half-life da reversão à média do spread.
    Valores típicos aceitáveis: 2–30 barras (M5/M15).
    """
    spread = spread.dropna()
    if len(spread) < 20:
        return None

    y      = spread.diff().dropna().values
    x      = spread.shift(1).dropna().values[:len(y)]
    x_mat  = np.column_stack([np.ones(len(x)), x])

    try:
        beta = np.linalg.lstsq(x_mat, y, rcond=None)[0]
        beta_1 = beta[1]  # coeficiente do lag
        if beta_1 >= 0 or beta_1 <= -1:
            return None  # não é mean-reverting
        half_life = -np.log(2) / np.log(1 + beta_1)
        return round(float(half_life), 2) if half_life > 0 else None
    except Exception:
        return None


# ═══════════════════════════════════════════════════════════════
#  HEDGE RATIO (OLS rolling)
# ═══════════════════════════════════════════════════════════════

def compute_hedge_ratio(series_a: pd.Series, series_b: pd.Series,
                         window: int = SPREAD_WIN) -> float:
    """Hedge ratio β via OLS: Price_A = α + β * Price_B."""
    y = series_a.iloc[-window:].values
    x = series_b.iloc[-window:].values
    if len(x) < 10 or np.var(x) == 0:
        return 1.0
    beta = np.cov(y, x)[0, 1] / np.var(x)
    return float(beta)


# ═══════════════════════════════════════════════════════════════
#  SPREAD Z-SCORE
# ═══════════════════════════════════════════════════════════════

def compute_spread_zscore(series_a: pd.Series, series_b: pd.Series,
                           window: int = SPREAD_WIN,
                           beta: float = None) -> Tuple[float, float, pd.Series]:
    """
    Calcula Z-score do spread entre dois activos.
    Retorna (z_score, beta, spread_series).
    """
    if len(series_a) < window + 10 or len(series_b) < window + 10:
        return float("nan"), 1.0, pd.Series(dtype=float)

    if beta is None:
        beta = compute_hedge_ratio(series_a, series_b, window)

    spread      = series_a - beta * series_b
    spread_win  = spread.iloc[-window:]
    mean        = spread_win.mean()
    std         = spread_win.std()

    if std < 1e-10:
        return float("nan"), beta, spread

    z = (spread.iloc[-1] - mean) / std
    return float(z), float(beta), spread


# ═══════════════════════════════════════════════════════════════
#  CORRELAÇÃO
# ═══════════════════════════════════════════════════════════════

def compute_correlation(series_a: pd.Series, series_b: pd.Series,
                         window: int = CORR_WIN) -> float:
    ret_a = series_a.pct_change().dropna()
    ret_b = series_b.pct_change().dropna()
    aligned = pd.concat([ret_a, ret_b], axis=1).dropna()
    if len(aligned) < window:
        return 0.0
    corr = aligned.iloc[-window:].corr().iloc[0, 1]
    return float(corr) if not np.isnan(corr) else 0.0


# ═══════════════════════════════════════════════════════════════
#  QUALIFICAÇÃO DO PAR (cointegração + half-life + correlação)
# ═══════════════════════════════════════════════════════════════

def qualify_pair(
    df_a: pd.DataFrame,
    df_b: pd.DataFrame,
    symbol_a: str,
    symbol_b: str,
) -> dict:
    """
    Avalia se um par é elegível para stat arb.
    Retorna resultado com score de qualidade e razões de rejeição.

    Critérios (todos devem passar):
    1. Correlação >= MIN_CORR
    2. Spread estacionário (ADF p-value < 0.10)
    3. Half-life <= MAX_HALF_LIFE_BARS
    4. Dados suficientes
    """
    result = {
        "eligible":    False,
        "symbol_a":    symbol_a,
        "symbol_b":    symbol_b,
        "correlation": 0.0,
        "adf":         {},
        "half_life":   None,
        "beta":        1.0,
        "quality":     0.0,
        "reasons":     [],
    }

    if df_a is None or df_b is None:
        result["reasons"].append("dados em falta")
        return result

    # Alinhar séries
    close_a = df_a["close"]
    close_b = df_b["close"]
    aligned = pd.concat([close_a, close_b], axis=1, join="inner").dropna()

    if len(aligned) < SPREAD_WIN + 20:
        result["reasons"].append(f"dados insuficientes ({len(aligned)} barras)")
        return result

    ca = aligned.iloc[:, 0]
    cb = aligned.iloc[:, 1]

    # 1. Correlação
    corr = compute_correlation(ca, cb)
    result["correlation"] = round(corr, 4)
    if abs(corr) < MIN_CORR:
        result["reasons"].append(f"correlação baixa ({corr:.3f} < {MIN_CORR})")
        return result

    # 2. Hedge ratio e spread
    beta   = compute_hedge_ratio(ca, cb)
    spread = ca - beta * cb
    result["beta"] = round(beta, 6)

    # 3. Teste ADF no spread
    adf = adf_test(spread)
    result["adf"] = adf
    if not adf["is_stationary"]:
        result["reasons"].append(
            f"spread não estacionário (ADF p={adf['p_value']:.3f} > {ADF_PVALUE_THRESHOLD})"
        )
        return result

    # 4. Half-life
    hl = compute_half_life(spread)
    result["half_life"] = hl
    if hl is None:
        result["reasons"].append("half-life indefinido (spread não reverte)")
        return result
    if hl > MAX_HALF_LIFE_BARS:
        result["reasons"].append(f"half-life demasiado longo ({hl:.1f} barras > {MAX_HALF_LIFE_BARS})")
        return result
    if hl < 1.0:
        result["reasons"].append(f"half-life demasiado curto ({hl:.1f} barras)")
        return result

    # ── PAR ELEGÍVEL ──────────────────────────────────────────
    result["eligible"] = True

    # Score de qualidade: 0 a 1
    # Componentes: correlação + ADF força + half-life óptimo
    corr_score   = (abs(corr) - MIN_CORR) / (1.0 - MIN_CORR)
    adf_score    = 1.0 - adf["p_value"] / ADF_PVALUE_THRESHOLD
    # Half-life óptimo: penaliza extremos (muito curto ou muito longo)
    hl_optimal   = 5.0
    hl_score     = max(0, 1.0 - abs(hl - hl_optimal) / MAX_HALF_LIFE_BARS)

    quality = 0.4 * corr_score + 0.4 * adf_score + 0.2 * hl_score
    result["quality"] = round(float(quality), 4)

    return result


# ═══════════════════════════════════════════════════════════════
#  TIPO 1 — CORRELATION ARB (com ADF)
# ═══════════════════════════════════════════════════════════════

def get_correlation_arb_signal(
    df_a: pd.DataFrame,
    df_b: pd.DataFrame,
    symbol_a: str,
    symbol_b: str,
    pair_quality: dict = None,
) -> dict:
    """
    Gera sinal de correlation arbitrage.
    Só actua se o par passou a qualificação ADF.
    """
    result = {
        "type":        "correlation_arb",
        "symbol_a":    symbol_a,
        "symbol_b":    symbol_b,
        "signal_a":    None,
        "signal_b":    None,
        "z":           float("nan"),
        "correlation": 0.0,
        "hedge_ratio": 1.0,
        "half_life":   None,
        "confidence":  0.0,
        "reason":      "",
        "adf_pvalue":  1.0,
    }

    # Usar qualificação pré-calculada ou recalcular
    qual = pair_quality or qualify_pair(df_a, df_b, symbol_a, symbol_b)

    if not qual["eligible"]:
        result["reason"] = " | ".join(qual["reasons"])
        return result

    result["correlation"] = qual["correlation"]
    result["hedge_ratio"] = qual["beta"]
    result["half_life"]   = qual["half_life"]
    result["adf_pvalue"]  = qual["adf"].get("p_value", 1.0)

    # Alinhar e calcular Z-score
    close_a = df_a["close"]
    close_b = df_b["close"]
    aligned = pd.concat([close_a, close_b], axis=1, join="inner").dropna()
    ca = aligned.iloc[:, 0]
    cb = aligned.iloc[:, 1]

    z, beta, _ = compute_spread_zscore(ca, cb, beta=qual["beta"])
    result["z"] = round(z, 4) if not np.isnan(z) else float("nan")

    if np.isnan(z):
        result["reason"] = "Z-score inválido"
        return result

    # Sinal
    if z >= ARB_Z_ENTER:
        result["signal_a"] = "SELL"
        result["signal_b"] = "BUY"
        result["reason"]   = (
            f"spread alto Z={z:.3f} | "
            f"ADF p={qual['adf']['p_value']:.3f} | "
            f"HL={qual['half_life']:.1f}b"
        )
    elif z <= -ARB_Z_ENTER:
        result["signal_a"] = "BUY"
        result["signal_b"] = "SELL"
        result["reason"]   = (
            f"spread baixo Z={z:.3f} | "
            f"ADF p={qual['adf']['p_value']:.3f} | "
            f"HL={qual['half_life']:.1f}b"
        )
    else:
        result["reason"] = f"Z={z:.3f} abaixo do threshold"

    if result["signal_a"]:
        # Confidence: qualidade do par × intensidade do Z
        conf = qual["quality"] * min(abs(z) / ARB_Z_STOP, 1.0)
        result["confidence"] = round(conf, 3)

    return result


# ═══════════════════════════════════════════════════════════════
#  TIPO 2 — SPREAD / SYNTHETIC ARB (inalterado)
# ═══════════════════════════════════════════════════════════════

SYNTHETIC_RELATIONS = [
    ("EURUSD", "USDCHF", "EURCHF", "multiply"),
    ("EURUSD", "USDJPY", "EURJPY", "multiply"),
    ("GBPUSD", "USDCHF", "GBPCHF", "multiply"),
    ("GBPUSD", "USDJPY", "GBPJPY", "multiply"),
    ("AUDUSD", "USDJPY", "AUDJPY", "multiply"),
]


def get_spread_arb_signal(prices: dict, bars: dict) -> list:
    signals = []
    for sym_a, sym_b, sym_c, op in SYNTHETIC_RELATIONS:
        if sym_a not in prices or sym_b not in prices or sym_c not in prices:
            continue
        pa, pb, pc = prices[sym_a], prices[sym_b], prices[sym_c]
        if not pa or not pb or not pc:
            continue

        synthetic = pa * pb if op == "multiply" else pa / pb
        dev_pct   = (pc - synthetic) / synthetic

        df_a = bars.get(sym_a)
        df_b = bars.get(sym_b)
        df_c = bars.get(sym_c)
        if df_a is None or df_b is None or df_c is None:
            continue

        aligned = pd.concat(
            [df_a["close"], df_b["close"], df_c["close"]],
            axis=1, join="inner"
        ).dropna()
        if len(aligned) < SPREAD_WIN:
            continue

        synth_hist = (aligned.iloc[:,0] * aligned.iloc[:,1] if op == "multiply"
                      else aligned.iloc[:,0] / aligned.iloc[:,1])
        dev_hist   = (aligned.iloc[:,2] - synth_hist) / synth_hist
        dev_mean   = dev_hist.iloc[-SPREAD_WIN:].mean()
        dev_std    = dev_hist.iloc[-SPREAD_WIN:].std()
        if dev_std < 1e-10:
            continue

        z = (dev_pct - dev_mean) / dev_std

        # ADF no desvio histórico
        adf = adf_test(dev_hist.iloc[-SPREAD_WIN:])

        signal = None
        if z >= ARB_Z_ENTER:
            signal = {"sym": sym_c, "direction": "SELL"}
        elif z <= -ARB_Z_ENTER:
            signal = {"sym": sym_c, "direction": "BUY"}

        if signal:
            signals.append({
                "type":       "spread_arb",
                "symbol":     sym_c,
                "direction":  signal["direction"],
                "z":          round(z, 4),
                "dev_pct":    round(dev_pct * 100, 4),
                "adf_pvalue": adf.get("p_value", 1.0),
                "stationary": adf.get("is_stationary", False),
                "synthetic":  round(synthetic, 6),
                "actual":     round(pc, 6),
                "confidence": round(min(abs(z) / ARB_Z_STOP, 1.0) *
                                    (0.8 if adf["is_stationary"] else 0.3), 3),
                "reason":     (f"{sym_c} {'over' if signal['direction']=='SELL' else 'under'}valued "
                               f"vs {sym_a}×{sym_b} Z={z:.3f} "
                               f"ADF_p={adf['p_value']:.3f}"),
            })
    return signals


# ═══════════════════════════════════════════════════════════════
#  TIPO 3 — MACRO ARB (inalterado)
# ═══════════════════════════════════════════════════════════════

def get_macro_arb_signal(symbol: str, current_price: float,
                          df: pd.DataFrame) -> dict:
    result = {"type": "macro_arb", "symbol": symbol,
              "signal": None, "score": 0.0, "macro": {}, "reason": ""}
    try:
        macro = ext.fred_get_macro_context()
        if not macro:
            return result
        result["macro"] = macro
        score, reasons = 0.0, []

        if symbol == "EURUSD":
            rate_diff = ext.fred_get_rate_differential("USD", "EUR")
            if rate_diff is not None:
                if rate_diff > 3.0 and current_price > 1.10:
                    score -= 0.4; reasons.append(f"USD-EUR diff={rate_diff:.2f}%")
                elif rate_diff < 1.5:
                    score += 0.3; reasons.append(f"rate diff estreito={rate_diff:.2f}%")
            vix = macro.get("VIX")
            if vix and vix > 25:
                score -= 0.2; reasons.append(f"VIX={vix:.1f} risk-off")

        elif symbol == "USDJPY":
            us10y = macro.get("US10Y")
            if us10y:
                if us10y < 4.0 and current_price > 150:
                    score -= 0.5; reasons.append(f"US10Y={us10y:.2f}% baixo mas USDJPY alto")
                elif us10y > 4.5 and current_price < 145:
                    score += 0.4; reasons.append(f"US10Y={us10y:.2f}% alto → suporte USDJPY")

        elif symbol == "AUDUSD":
            oil = macro.get("OIL_WTI")
            gold = macro.get("GOLD")
            if oil and oil > 80 and current_price < 0.65:
                score += 0.3; reasons.append(f"Oil=${oil:.1f}")
            if gold and gold > 2000 and current_price < 0.65:
                score += 0.2; reasons.append(f"Gold=${gold:.0f}")

        news = ext.news_get_sentiment(symbol, hours=6)
        score += news.get("score", 0.0) * 0.2
        if abs(news.get("score", 0)) > 0.1:
            reasons.append(f"news={news['score']:.2f}")

        result["score"] = round(score, 3)
        if score >= 0.4:
            result["signal"] = "BUY"; result["reason"] = " | ".join(reasons)
        elif score <= -0.4:
            result["signal"] = "SELL"; result["reason"] = " | ".join(reasons)
    except Exception:
        pass
    return result


# ═══════════════════════════════════════════════════════════════
#  DESCOBERTA AUTOMÁTICA COM QUALIFICAÇÃO ADF
# ═══════════════════════════════════════════════════════════════

def discover_qualified_pairs(bars: dict, min_corr: float = MIN_CORR) -> list:
    """
    Descobre pares elegíveis para stat arb com filtro ADF + half-life.
    Devolve lista de dicts ordenada por qualidade.
    """
    symbols = list(bars.keys())
    pairs   = []

    for sym_a, sym_b in combinations(symbols, 2):
        df_a = bars.get(sym_a)
        df_b = bars.get(sym_b)
        if df_a is None or df_b is None:
            continue

        qual = qualify_pair(df_a, df_b, sym_a, sym_b)
        if qual["eligible"]:
            pairs.append({
                "symbol_a":    sym_a,
                "symbol_b":    sym_b,
                "correlation": qual["correlation"],
                "adf_pvalue":  qual["adf"].get("p_value", 1.0),
                "half_life":   qual["half_life"],
                "beta":        qual["beta"],
                "quality":     qual["quality"],
            })

    return sorted(pairs, key=lambda x: x["quality"], reverse=True)


# ═══════════════════════════════════════════════════════════════
#  COMBINADOR
# ═══════════════════════════════════════════════════════════════

def combine_arb_signals(
    corr_signal: dict,
    spread_signals: list,
    macro_signal: dict,
    symbol: str,
) -> dict:
    scores = {"BUY": 0.0, "SELL": 0.0}
    active = []

    if corr_signal.get("signal_a") and corr_signal.get("symbol_a") == symbol:
        sig  = corr_signal["signal_a"]
        conf = corr_signal.get("confidence", 0.0)
        scores[sig] += conf * 0.45
        active.append(f"CorrArb:{sig}(conf={conf:.2f})")

    for ss in spread_signals:
        if ss.get("symbol") == symbol:
            sig  = ss["direction"]
            conf = ss.get("confidence", 0.0)
            scores[sig] += conf * 0.35
            active.append(f"SpreadArb:{sig}(Z={ss['z']:.2f})")

    if macro_signal.get("signal"):
        sig  = macro_signal["signal"]
        conf = min(abs(macro_signal.get("score", 0.0)), 1.0)
        scores[sig] += conf * 0.20
        active.append(f"MacroArb:{sig}(score={macro_signal['score']:.2f})")

    best_sig   = max(scores, key=scores.get)
    best_score = scores[best_sig]

    return {
        "symbol":     symbol,
        "signal":     best_sig if best_score >= 0.25 else None,
        "score":      round(best_score, 3),
        "components": active,
        "reason":     " | ".join(active) if active else "sem sinal",
    }


# ═══════════════════════════════════════════════════════════════
#  EXIT CONDITIONS
# ═══════════════════════════════════════════════════════════════

def arb_should_exit(position_type: str, z: float) -> Tuple[bool, str]:
    if np.isnan(z):
        return False, ""
    if position_type == "BUY" and z >= -ARB_Z_EXIT:
        return True, f"spread reconvergiu (Z={z:.3f})"
    if position_type == "SELL" and z <= ARB_Z_EXIT:
        return True, f"spread reconvergiu (Z={z:.3f})"
    if position_type == "BUY" and z <= -ARB_Z_STOP:
        return True, f"stop loss arb (Z={z:.3f})"
    if position_type == "SELL" and z >= ARB_Z_STOP:
        return True, f"stop loss arb (Z={z:.3f})"
    return False, ""
