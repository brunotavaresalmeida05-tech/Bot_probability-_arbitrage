from __future__ import annotations
"""
Market Families — V9.1

Organiza os activos em grupos funcionais e analisa relacoes
spot-futuro dentro de cada familia.

Grupos:
  TRADABLE          - geram sinal e execucao real
  FUTURES_MIRROR    - confirmam direcao e spread, nao geram trade
  CONTEXT_BENCHMARK - contexto macro, nao geram trade

Para cada familia spot-futuro, calcula:
  - alinhamento direcional (ambos apontam para o mesmo lado?)
  - desvio de spread (premium do futuro fora do normal?)
  - boost ou penalizacao na confluencia do sinal
"""
from dataclasses import dataclass, field


# ── Roles funcionais ─────────────────────────────────────────────────────────

TRADABLE          = "tradable"
FUTURES_MIRROR    = "futures_mirror"
CONTEXT_BENCHMARK = "context_benchmark"


# ── Definicao de familias spot-futuro ────────────────────────────────────────

@dataclass
class MarketFamily:
    name: str
    spot: str
    futures: str | None = None

    def members(self) -> list[str]:
        m = [self.spot]
        if self.futures:
            m.append(self.futures)
        return m


FAMILIES: list[MarketFamily] = [
    MarketFamily("S&P500",  spot="Usa500",  futures="Usa500Jun26"),
    MarketFamily("Nasdaq",  spot="UsaTec",  futures="UsaTecJun26"),
    MarketFamily("FTSE100", spot="UK100",   futures="UK100Jun26"),
    MarketFamily("DAX",     spot="Ger40",   futures="Ger40Jun26"),
    MarketFamily("GOLD",    spot="GOLD",    futures=None),
    MarketFamily("SILVER",  spot="SILVER",  futures=None),
    MarketFamily("BRENT",   spot="Brent",   futures=None),
    MarketFamily("WTI",     spot="LCrude",  futures=None),
    MarketFamily("NGAS",    spot="NGas",    futures=None),
    MarketFamily("BTC",     spot="BTCUSD",  futures=None),
    MarketFamily("COFFEE",  spot="Coffee",  futures=None),
    MarketFamily("EURUSD",  spot="EURUSD",  futures=None),
    MarketFamily("GBPUSD",  spot="GBPUSD",  futures=None),
    MarketFamily("USDJPY",  spot="USDJPY",  futures=None),
    MarketFamily("AUDUSD",  spot="AUDUSD",  futures=None),
    MarketFamily("USDCAD",  spot="USDCAD",  futures=None),
]

# Mapa rapido: symbol -> familia
_SYMBOL_TO_FAMILY: dict[str, MarketFamily] = {}
for _f in FAMILIES:
    for _s in _f.members():
        _SYMBOL_TO_FAMILY[_s] = _f


def get_family(symbol: str) -> MarketFamily | None:
    return _SYMBOL_TO_FAMILY.get(symbol)


def get_spot_for_futures(futures_symbol: str) -> str | None:
    f = _SYMBOL_TO_FAMILY.get(futures_symbol)
    if f and f.futures == futures_symbol:
        return f.spot
    return None


# ── Analise spot-futuro ───────────────────────────────────────────────────────

@dataclass
class FamilyAnalysis:
    family_name: str
    spot_symbol: str
    futures_symbol: str | None
    direction_aligned: bool = True
    spread_normal: bool = True
    confluence_delta: float = 0.0   # positivo = boost, negativo = penalizacao
    notes: list[str] = field(default_factory=list)


def analyze_family(
    family: MarketFamily,
    spot_bundle,
    futures_bundle,
) -> FamilyAnalysis:
    """
    Compara spot vs futuro da mesma familia.

    spot_bundle / futures_bundle: IndicatorBundle (pode ser None se dados indisponiveis)

    Retorna FamilyAnalysis com:
      confluence_delta:  +0.10 se alinhados, -0.15 se divergentes
      direction_aligned: True se MACD spot e futuro apontam para o mesmo lado
    """
    result = FamilyAnalysis(
        family_name=family.name,
        spot_symbol=family.spot,
        futures_symbol=family.futures,
    )

    if spot_bundle is None or futures_bundle is None:
        result.notes.append("dados incompletos — sem analise spot-futuro")
        return result

    # 1. Alinhamento direcional via MACD
    spot_dir    = getattr(spot_bundle.macd,    "direction", None) if spot_bundle.macd    else None
    futures_dir = getattr(futures_bundle.macd, "direction", None) if futures_bundle.macd else None

    if spot_dir and futures_dir:
        if spot_dir == futures_dir:
            result.direction_aligned = True
            result.confluence_delta += 0.10
            result.notes.append(f"MACD alinhados: {spot_dir}")
        else:
            result.direction_aligned = False
            result.confluence_delta -= 0.15
            result.notes.append(f"MACD divergentes: spot={spot_dir} fut={futures_dir}")

    # 2. Spread relativo entre close de spot e futuro
    spot_close    = getattr(spot_bundle,    "close", 0.0)
    futures_close = getattr(futures_bundle, "close", 0.0)

    if spot_close > 0 and futures_close > 0:
        premium_pct = (futures_close - spot_close) / spot_close
        # Premium > 1% ou < -1% e incomum para acoes/commodities de curto prazo
        if abs(premium_pct) > 0.01:
            result.spread_normal = False
            result.confluence_delta -= 0.05
            result.notes.append(f"spread anormal: {premium_pct:+.2%}")
        else:
            result.notes.append(f"spread normal: {premium_pct:+.3%}")

    result.confluence_delta = round(max(-0.30, min(0.20, result.confluence_delta)), 3)
    return result


# ── Exposicao duplicada ───────────────────────────────────────────────────────

def check_duplicate_exposure(signals: list) -> list:
    """
    Filtra sinais para evitar exposicao duplicada ao mesmo motor de mercado.
    Quando dois activos da mesma familia estao ambos em TRADABLE e ambos geram
    sinal na mesma direcao, mantemos apenas o de maior score.

    signals: lista de FinalSignal com atributo .symbol e .total_score
    """
    seen_families: dict[str, object] = {}
    filtered = []

    for sig in signals:
        fam = get_family(sig.symbol)
        if fam is None:
            filtered.append(sig)
            continue

        key = fam.name
        existing = seen_families.get(key)
        if existing is None:
            seen_families[key] = sig
            filtered.append(sig)
        else:
            # Manter o sinal com maior total_score
            if sig.total_score > existing.total_score:
                filtered.remove(existing)
                filtered.append(sig)
                seen_families[key] = sig
            # se scores iguais, manter o primeiro

    return filtered
