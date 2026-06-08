"""
checks/rsi_report.py --RSI edge validation report.

Mede o impacto do RSI no Opportunity-Permission Engine:
  1) RSI-aligned entries   --sinal gerado com RSI a favor do lado
  2) RSI-blocked entries   --ciclos em que RSI extremo reduziu score ou bloqueou
  3) Net edge by RSI band  --distribuição de scores por faixa de RSI

Lê state_history.jsonl (um JSON por linha) e filtra por janela temporal.

Uso:
  python checks/rsi_report.py [--hours 24]
  python checks/rsi_report.py --hours 168   # 7 dias
  python checks/rsi_report.py --hours 48 --symbol EURUSD
"""
from __future__ import annotations

import json
import argparse
import sys
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT    = Path(__file__).resolve().parent.parent
HISTORY = ROOT / "state" / "state_history.jsonl"

# RSI bands para análise
RSI_BANDS = [
    (0,   30,  "0-30   [extremo short]"),
    (30,  45,  "30-45  [momentum short]"),
    (45,  55,  "45-55  [neutro]"),
    (55,  70,  "55-70  [momentum long]"),
    (70,  100, "70-100 [extremo long]"),
]


def _bucket(rsi: float) -> str:
    for lo, hi, label in RSI_BANDS:
        if lo <= rsi < hi:
            return label
    return "70-100 [extremo long]"


def _parse_ts(s: str) -> datetime | None:
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
    except Exception:
        return None


def _load_cycles(hours: int, symbol_filter: str | None) -> list[dict]:
    if not HISTORY.exists():
        print(f"[ERRO] {HISTORY} não encontrado.")
        sys.exit(1)

    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    cycles: list[dict] = []

    with open(HISTORY, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts = _parse_ts(entry.get("ts", ""))
            if ts and ts < cutoff:
                continue
            # Expand per-signal if signals list is present
            signals = entry.get("signals", [])
            if signals:
                for sig in signals:
                    if symbol_filter and sig.get("symbol") != symbol_filter:
                        continue
                    cycles.append({
                        "ts": entry.get("ts", ""),
                        "cycle": entry.get("cycle_count", 0),
                        "session": entry.get("session", ""),
                        "symbol": sig.get("symbol", ""),
                        "signal": sig.get("signal", "HOLD"),
                        "rsi": float(sig.get("rsi", 50.0)),
                        "total_score": float(sig.get("total_score", 0.0)),
                        "mcs_n": float(sig.get("mcs_n", 0.0)),
                        "bcs_n": float(sig.get("bcs_n", 0.0)),
                        "hcs_n": float(sig.get("hcs_n", 0.0)),
                        "es": float(sig.get("es", 0.0)),
                        "cs": float(sig.get("cs", 0.0)),
                        "rs": float(sig.get("rs", 0.0)),
                        "decision": sig.get("decision", ""),
                    })
            else:
                # Ciclos sem sinais --registar para contagem de bloqueios
                if symbol_filter:
                    continue
                cycles.append({
                    "ts": entry.get("ts", ""),
                    "cycle": entry.get("cycle_count", 0),
                    "session": entry.get("session", ""),
                    "symbol": "_all_",
                    "signal": "HOLD",
                    "rsi": 50.0,
                    "total_score": 0.0,
                    "mcs_n": 0.0, "bcs_n": 0.0, "hcs_n": 0.0,
                    "es": 0.0, "cs": 0.0, "rs": 0.0,
                    "decision": "",
                })

    return cycles


# ── Análise 1: RSI-aligned entries ────────────────────────────────────────────

def analyse_aligned(cycles: list[dict]) -> dict:
    """
    Conta entradas onde RSI confirma o lado do sinal:
      BUY  com RSI > 55  → alinhado
      SELL com RSI < 45  → alinhado
    """
    aligned = 0
    misaligned = 0
    total_signals = 0

    for c in cycles:
        sig = c["signal"]
        rsi = c["rsi"]
        if sig in ("BUY", "SELL"):
            total_signals += 1
            if (sig == "BUY" and rsi > 55) or (sig == "SELL" and rsi < 45):
                aligned += 1
            else:
                misaligned += 1

    return {
        "total_signals": total_signals,
        "aligned": aligned,
        "misaligned": misaligned,
        "alignment_rate": round(aligned / total_signals * 100, 1) if total_signals else 0.0,
    }


# ── Análise 2: RSI-blocked ─────────────────────────────────────────────────────

def analyse_blocked(cycles: list[dict]) -> dict:
    """
    Ciclos onde RSI extremo provavelmente penalizou o score:
      RSI > 75 ou < 25 → extremo moderado (penalidade aplicada)
      RSI > 80 ou < 20 → extremo forte
    """
    extreme_strong = 0
    extreme_mod = 0
    neutral = 0
    momentum = 0

    for c in cycles:
        rsi = c["rsi"]
        if rsi > 80 or rsi < 20:
            extreme_strong += 1
        elif rsi > 75 or rsi < 25:
            extreme_mod += 1
        elif (55 <= rsi <= 70) or (30 <= rsi <= 45):
            momentum += 1
        else:
            neutral += 1

    total = len(cycles)
    return {
        "total_cycles": total,
        "extreme_strong_pct": round(extreme_strong / total * 100, 1) if total else 0.0,
        "extreme_mod_pct": round(extreme_mod / total * 100, 1) if total else 0.0,
        "momentum_pct": round(momentum / total * 100, 1) if total else 0.0,
        "neutral_pct": round(neutral / total * 100, 1) if total else 0.0,
        "extreme_strong": extreme_strong,
        "extreme_mod": extreme_mod,
        "momentum": momentum,
        "neutral": neutral,
    }


# ── Análise 3: Net edge by RSI band ───────────────────────────────────────────

def analyse_by_band(cycles: list[dict]) -> dict[str, dict]:
    """
    Por faixa de RSI: total de ciclos, sinais activos, score médio, ES médio.
    Como não temos trades reais ainda (dry_run), usa TotalScore como proxy de edge.
    """
    bands: dict[str, dict] = {label: {
        "cycles": 0, "signals": 0,
        "total_score_sum": 0.0, "es_sum": 0.0, "rs_sum": 0.0,
        "buy": 0, "sell": 0, "hold_block": 0,
    } for _, _, label in RSI_BANDS}

    for c in cycles:
        label = _bucket(c["rsi"])
        b = bands[label]
        b["cycles"] += 1
        sig = c["signal"]
        if sig == "BUY":
            b["buy"] += 1
            b["signals"] += 1
        elif sig == "SELL":
            b["sell"] += 1
            b["signals"] += 1
        else:
            b["hold_block"] += 1
        b["total_score_sum"] += c["total_score"]
        b["es_sum"]          += c["es"]
        b["rs_sum"]          += c["rs"]

    # Calcular médias
    result = {}
    for label, b in bands.items():
        n = b["cycles"] or 1
        result[label] = {
            "cycles":     b["cycles"],
            "signals":    b["signals"],
            "buy":        b["buy"],
            "sell":       b["sell"],
            "hold_block": b["hold_block"],
            "avg_score":  round(b["total_score_sum"] / n, 4),
            "avg_es":     round(b["es_sum"] / n, 4),
            "avg_rs":     round(b["rs_sum"] / n, 4),
            "signal_rate": round(b["signals"] / b["cycles"] * 100, 1) if b["cycles"] else 0.0,
        }
    return result


# ── Formatação do relatório ───────────────────────────────────────────────────

def _sep(char: str = "-", width: int = 72) -> str:
    return char * width


def print_report(
    aligned: dict,
    blocked: dict,
    by_band: dict[str, dict],
    hours: int,
    symbol_filter: str | None,
):
    scope = f"simbolo={symbol_filter}" if symbol_filter else "todos os simbolos"
    print()
    print(_sep("="))
    print(f"  RSI EDGE VALIDATION REPORT  |  ultimas {hours}h  |  {scope}")
    print(_sep("="))

    # 1) Aligned entries
    print()
    print("[1] RSI-ALIGNED ENTRIES")
    print(_sep())
    a = aligned
    print(f"  Sinais totais (BUY/SELL) : {a['total_signals']}")
    print(f"  RSI alinhado             : {a['aligned']}  ({a['alignment_rate']}%)")
    print(f"  RSI desalinhado          : {a['misaligned']}")
    if a["total_signals"] == 0:
        print("  [AVISO] Sem sinais activos na janela --regime indefinido ou fora de sessao")

    # 2) Blocked/penalised
    print()
    print("[2] DISTRIBUICAO RSI (todos os ciclos)")
    print(_sep())
    b = blocked
    print(f"  Total ciclos analisados  : {b['total_cycles']}")
    print(f"  Zona neutro  (45-55)     : {b['neutral']}  ({b['neutral_pct']}%)")
    print(f"  Zona momentum (30-45/55-70): {b['momentum']}  ({b['momentum_pct']}%)  [bonus +0.02]")
    print(f"  Extremo moderado (>75/<25): {b['extreme_mod']}  ({b['extreme_mod_pct']}%)  [penalty -0.03]")
    print(f"  Extremo forte   (>80/<20): {b['extreme_strong']}  ({b['extreme_strong_pct']}%)  [penalty -0.06, RS+0.15]")

    # 3) By band
    print()
    print("[3] NET EDGE BY RSI BAND  (proxy: TotalScore medio --sem trades reais ainda)")
    print(_sep())
    header = f"  {'Banda':<26} {'Ciclos':>6} {'Sinais':>7} {'BUY':>5} {'SELL':>5} {'AvgScore':>9} {'AvgES':>7} {'AvgRS':>7} {'SigRate':>8}"
    print(header)
    print("  " + "-" * 68)
    for label, d in by_band.items():
        if d["cycles"] == 0:
            continue
        print(
            f"  {label:<26} {d['cycles']:>6} {d['signals']:>7} "
            f"{d['buy']:>5} {d['sell']:>5} "
            f"{d['avg_score']:>9.4f} {d['avg_es']:>7.4f} {d['avg_rs']:>7.4f} "
            f"{d['signal_rate']:>7.1f}%"
        )

    # Leitura esperada
    print()
    print("[NOTA] Leitura esperada em tendencia:")
    print("  55-70 -> bom para longs (momentum sem exaustao)")
    print("  30-45 -> bom para shorts (momentum sem exaustao)")
    print("  >75 ou <25 -> penalidade activa -- verificar se corta bons trades cedo demais")
    print("  >80 ou <20 -> exaustao forte -- RS+0.15 aplicado ao PermissionScore")
    print()
    neutral_only = all(d["cycles"] == 0 for label, d in by_band.items() if "neutro" not in label)
    if neutral_only:
        print()
        print("[AVISO] Todos os ciclos mostram RSI=50.0 (neutro).")
        print("  Isto e normal para dados anteriores a 2026-06-08 (pre-integracao RSI).")
        print("  Execute o relatorio apos o bot correr com a nova versao para ver RSI real.")

    print()
    print("[PROXIMOS PASSOS]")
    print("  - Se alignment_rate < 40%: RSI pode estar em conflito com o regime")
    print("  - Se extremo_forte > 10%: verificar se PermissionScore esta a bloquear demasiado")
    print("  - Apos 50+ trades reais: adicionar avg_R e net_R por banda")
    print(_sep("="))
    print()


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="RSI edge validation report")
    parser.add_argument("--hours",  type=int, default=24, help="Janela de analise em horas")
    parser.add_argument("--symbol", type=str, default=None, help="Filtrar por simbolo (ex: EURUSD)")
    args = parser.parse_args()

    cycles = _load_cycles(args.hours, args.symbol)

    if not cycles:
        print(f"[AVISO] Nenhum ciclo encontrado nas ultimas {args.hours}h.")
        sys.exit(0)

    aligned = analyse_aligned(cycles)
    blocked = analyse_blocked(cycles)
    by_band = analyse_by_band(cycles)

    print_report(aligned, blocked, by_band, args.hours, args.symbol)


if __name__ == "__main__":
    main()
