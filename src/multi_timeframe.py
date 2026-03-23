"""
src/multi_timeframe.py
Análise multi-timeframe: M5 + H1 + D1 em simultâneo.

Lógica:
- D1 define o regime macro (tendência dominante)
- H1 define a direcção táctica
- M5 é o timeframe de entrada (precisão)

Só entra em trade quando os 3 timeframes concordam.
Sinal mais forte = confirmação em todos os TFs.
"""

import pandas as pd
import numpy as np
from typing import Optional, Tuple
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import config.settings as cfg
import src.mt5_connector as mt5c
import src.strategy as strat


# Configuração dos timeframes
TF_CONFIG = {
    "D1": {"weight": 0.40, "ma_period": 50,  "sd_period": 20, "role": "regime"},
    "H1": {"weight": 0.35, "ma_period": 100, "sd_period": 50, "role": "direction"},
    "M5": {"weight": 0.25, "ma_period": 100, "sd_period": 50, "role": "entry"},
}

# Quantas barras pedir por timeframe
TF_BARS = {"D1": 300, "H1": 500, "M5": 300}


def _get_tf_signal(symbol: str, timeframe: str, tf_cfg: dict) -> dict:
    """Calcula sinal para um timeframe específico."""
    bars = TF_BARS.get(timeframe, 300)
    df   = mt5c.get_bars(symbol, timeframe, bars)

    result = {
        "timeframe": timeframe,
        "signal":    None,
        "z":         float("nan"),
        "ma":        None,
        "close":     None,
        "trend":     "neutral",
        "weight":    tf_cfg["weight"],
    }

    if df is None or len(df) < tf_cfg["ma_period"] + 10:
        return result

    close = df["close"]
    ma    = strat.compute_ma(close, tf_cfg["ma_period"], cfg.MA_TYPE)
    sd    = strat.compute_stddev(close, tf_cfg["sd_period"])
    atr   = strat.compute_atr(df, cfg.ATR_PERIOD)

    z_last     = float(((close - ma) / sd.replace(0, np.nan)).iloc[-1])
    ma_last    = float(ma.iloc[-1])
    close_last = float(close.iloc[-1])
    atr_last   = float(atr.iloc[-1])

    result["z"]     = round(z_last, 4) if not np.isnan(z_last) else float("nan")
    result["ma"]    = round(ma_last, 5)
    result["close"] = round(close_last, 5)

    # Tendência no timeframe
    # Usa a posição do close vs MA como proxy de tendência
    if not np.isnan(z_last):
        if z_last > 0.5:
            result["trend"] = "up"
        elif z_last < -0.5:
            result["trend"] = "down"
        else:
            result["trend"] = "neutral"

    # Sinal mean-reversion neste timeframe
    z_enter = cfg.Z_ENTER
    if not np.isnan(z_last):
        if z_last <= -z_enter and close_last < ma_last:
            result["signal"] = "BUY"
        elif z_last >= z_enter and close_last > ma_last:
            result["signal"] = "SELL"

    return result


def get_mtf_signal(symbol: str) -> dict:
    """
    Analisa os 3 timeframes e devolve sinal combinado.

    Retorna:
        signal:      "BUY" / "SELL" / None
        confidence:  0.0 a 1.0
        agreement:   número de TFs que concordam
        details:     dict por timeframe
        regime:      "bull" / "bear" / "neutral" (baseado em D1)
        reason:      string explicativa
    """
    result = {
        "symbol":     symbol,
        "signal":     None,
        "confidence": 0.0,
        "agreement":  0,
        "regime":     "neutral",
        "details":    {},
        "reason":     "",
        "mtf_score":  0.0,
    }

    tf_signals = {}
    for tf, tf_cfg in TF_CONFIG.items():
        sig = _get_tf_signal(symbol, tf, tf_cfg)
        tf_signals[tf] = sig
        result["details"][tf] = sig

    # Regime macro (D1)
    d1 = tf_signals.get("D1", {})
    d1_trend = d1.get("trend", "neutral")
    result["regime"] = "bull" if d1_trend == "up" else ("bear" if d1_trend == "down" else "neutral")

    # Contar acordos e calcular score ponderado
    buy_score  = 0.0
    sell_score = 0.0
    reasons    = []

    for tf, sig in tf_signals.items():
        tf_cfg = TF_CONFIG[tf]
        w      = tf_cfg["weight"]
        s      = sig.get("signal")
        z      = sig.get("z", float("nan"))
        trend  = sig.get("trend", "neutral")

        if s == "BUY":
            buy_score += w
            reasons.append(f"{tf}:BUY(Z={z:.2f})")
        elif s == "SELL":
            sell_score += w
            reasons.append(f"{tf}:SELL(Z={z:.2f})")
        else:
            reasons.append(f"{tf}:neutral({trend})")

    result["mtf_score"] = round(buy_score - sell_score, 4)

    # Sinal final: só entra se pelo menos 2 TFs concordam
    # E o D1 não contradiz (regime)
    buy_tfs  = [tf for tf, s in tf_signals.items() if s.get("signal") == "BUY"]
    sell_tfs = [tf for tf, s in tf_signals.items() if s.get("signal") == "SELL"]

    if len(buy_tfs) >= 2 and buy_score > sell_score:
        # Verificar que D1 não está em tendência de baixa forte
        if d1_trend != "down" or d1.get("z", 0) > -1.5:
            result["signal"]     = "BUY"
            result["agreement"]  = len(buy_tfs)
            result["confidence"] = round(buy_score, 3)
            result["reason"]     = " | ".join(reasons)

    elif len(sell_tfs) >= 2 and sell_score > buy_score:
        # Verificar que D1 não está em tendência de alta forte
        if d1_trend != "up" or d1.get("z", 0) < 1.5:
            result["signal"]     = "SELL"
            result["agreement"]  = len(sell_tfs)
            result["confidence"] = round(sell_score, 3)
            result["reason"]     = " | ".join(reasons)

    else:
        result["reason"] = "TFs em desacordo: " + " | ".join(reasons)

    return result


def get_mtf_exit_signal(symbol: str, position_type: str) -> Tuple[bool, str]:
    """
    Verifica se deve sair da posição baseado em múltiplos TFs.
    Sai quando pelo menos 2 TFs indicam saída.
    """
    exit_count = 0
    reasons    = []

    for tf, tf_cfg in TF_CONFIG.items():
        sig = _get_tf_signal(symbol, tf, tf_cfg)
        z   = sig.get("z", float("nan"))

        if np.isnan(z):
            continue

        if position_type == "BUY" and z >= -cfg.Z_EXIT:
            exit_count += 1
            reasons.append(f"{tf}:Z={z:.2f}≥-{cfg.Z_EXIT}")
        elif position_type == "SELL" and z <= cfg.Z_EXIT:
            exit_count += 1
            reasons.append(f"{tf}:Z={z:.2f}≤{cfg.Z_EXIT}")

    if exit_count >= 2:
        return True, "MTF exit: " + " | ".join(reasons)
    return False, ""


def format_mtf_summary(mtf: dict) -> str:
    """Formata resumo MTF para o terminal."""
    d = mtf.get("details", {})
    parts = []
    for tf in ["D1", "H1", "M5"]:
        s = d.get(tf, {})
        z = s.get("z", float("nan"))
        sig = s.get("signal", "–") or "–"
        z_str = f"{z:.2f}" if not np.isnan(z) else "n/a"
        parts.append(f"{tf}[Z={z_str},{sig}]")
    regime = mtf.get("regime","?")
    signal = mtf.get("signal","–") or "–"
    conf   = mtf.get("confidence", 0)
    return f"MTF:{' '.join(parts)} → {signal}(conf={conf:.2f}) regime={regime}"
