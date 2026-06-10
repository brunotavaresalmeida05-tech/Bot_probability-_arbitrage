from __future__ import annotations
"""
Technical Indicators — V9

Hierarquia de 4 camadas (conforme metodologia de trading):

  Camada 1 — Principal (base da decisão técnica → MCS, BCS, HCS no TotalScore)
    MACD           — direção, momentum e cumprimento de movimento
    Bollinger Bands (10 períodos) — compressão, expansão e extremos de volatilidade
    Hi-Lo Activator — range da sessão e pontos por cumprir
    ATR Stop (Chandelier Exit) — stop dinâmico e leitura numérica de volatilidade → RS

  Camada 2 — Confirmação intradiária (filtros binários → gate de confirmações)
    VWAP           — preço justo intradiário e equilíbrio de fluxo
    EMA 8          — timing e pullback curto
    SMA 50 / SMA 100 — estrutura e tendência de preço
    Parabolic SAR  — mudança curta de direção e apoio a stop técnico

  Camada 3 — Participação (reforço de CS / filtros binários)
    Weis Wave / Volume — confirmação de força real do movimento
    Pivot Points   — zonas do dia e projeções de reação
    Fair Price (macro) — referência de trabalho do ativo na sessão

  Camada 4 — Contexto superior (→ CS e RS no TotalScore)
    Macro          — CPI, PIB, payroll, PMI, juros, DXY, VIX, ouro, petróleo
    Benchmark      — S&P futuro, DXY, VIX, yields, ouro, petróleo por símbolo
    Risco          — size, stop, drawdown, exposição, blackout de eventos
"""
from dataclasses import dataclass, field

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------

@dataclass
class MACDResult:
    macd_line: float        # fast_ema - slow_ema
    signal_line: float      # EMA of macd_line
    # No histogram by design
    direction: str = ""     # "bullish" | "bearish" | "flat"
    teeth: list[float] = field(default_factory=list)  # unfulfilled volatility points


@dataclass
class BollingerResult:
    upper: float
    middle: float
    lower: float
    width: float            # upper - lower
    width_pct: float        # width / middle (normalized)
    state: str = ""         # "expanding" | "contracting" | "neutral"
    prev_width: float = 0.0


@dataclass
class SARResult:
    value: float
    direction: str          # "bullish" (SAR below price) | "bearish" (SAR above price)
    reversal: bool = False  # True if direction changed vs previous bar


@dataclass
class HiLoResult:
    value: float      # current hi-lo line level
    direction: str    # "bullish" (price above line) | "bearish" (price below line)


@dataclass
class ATRStopResult:
    value: float      # stop level (Chandelier Exit)
    direction: str    # "bullish" (price above stop) | "bearish" (price below stop)


@dataclass
class PivotResult:
    pp: float               # pivot point
    r1: float
    r2: float
    r3: float
    s1: float
    s2: float
    s3: float


@dataclass
class IndicatorBundle:
    """All indicators for one symbol on one timeframe."""
    symbol: str
    timeframe: str
    timestamp: str = ""
    close: float = 0.0
    volume: float = 0.0
    macd: MACDResult | None = None
    bollinger: BollingerResult | None = None
    sar: SARResult | None = None
    hi_lo: HiLoResult | None = None
    atr_stop: ATRStopResult | None = None
    ema8: float = 0.0
    vwap: float = 0.0
    ma50: float = 0.0
    ma100: float = 0.0
    pivot: PivotResult | None = None
    weis_wave: float = 0.0  # cumulative volume delta (Weis Wave proxy)
    atr: float = 0.0
    rsi: float = 50.0       # RSI(14); 50.0 = neutro por defeito
    adx: float = 20.0       # ADX(14); 20.0 = neutro por defeito


# ---------------------------------------------------------------------------
# Calculation functions
# ---------------------------------------------------------------------------

def _ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def macd(
    closes: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
    history: int = 50,
) -> MACDResult:
    """
    MACD with lines only (no histogram).
    'teeth' = local extremes of the MACD line that represent
              unfulfilled volatility points the market may return to.
    """
    fast_ema = _ema(closes, fast)
    slow_ema = _ema(closes, slow)
    macd_line = fast_ema - slow_ema
    signal_line = _ema(macd_line, signal)

    last_macd = macd_line.iloc[-1]
    last_signal = signal_line.iloc[-1]

    if last_macd > last_signal:
        direction = "bullish"
    elif last_macd < last_signal:
        direction = "bearish"
    else:
        direction = "flat"

    # Detect "teeth" — local min/max of MACD line that price hasn't revisited
    teeth = _find_macd_teeth(macd_line.iloc[-history:])

    return MACDResult(
        macd_line=round(float(last_macd), 6),
        signal_line=round(float(last_signal), 6),
        direction=direction,
        teeth=teeth,
    )


def _find_macd_teeth(macd_series: pd.Series, n: int = 3) -> list[float]:
    """
    Find local extrema (peaks and troughs) in the MACD line.
    These represent resistance/support levels of volatility.
    Returns the last N unfulfilled teeth as price levels.
    """
    values = macd_series.values
    teeth = []
    for i in range(1, len(values) - 1):
        prev, curr, nxt = values[i - 1], values[i], values[i + 1]
        if curr > prev and curr > nxt:  # local peak
            teeth.append(round(float(curr), 6))
        elif curr < prev and curr < nxt:  # local trough
            teeth.append(round(float(curr), 6))
    return teeth[-n:] if len(teeth) > n else teeth


def bollinger(
    closes: pd.Series,
    period: int = 10,
    std_mult: float = 2.0,
    prev_width: float = 0.0,
) -> BollingerResult:
    """
    Bollinger Bands (10 periods by default — per trading methodology).
    State: expanding = volatility increasing, contracting = volatility decreasing.
    """
    middle = closes.rolling(period).mean().iloc[-1]
    std = closes.rolling(period).std().iloc[-1]
    upper = middle + std_mult * std
    lower = middle - std_mult * std
    width = upper - lower
    width_pct = (width / middle) if middle != 0 else 0.0

    if prev_width > 0:
        if width > prev_width * 1.02:
            state = "expanding"
        elif width < prev_width * 0.98:
            state = "contracting"
        else:
            state = "neutral"
    else:
        state = "neutral"

    return BollingerResult(
        upper=round(float(upper), 5),
        middle=round(float(middle), 5),
        lower=round(float(lower), 5),
        width=round(float(width), 5),
        width_pct=round(float(width_pct), 6),
        state=state,
        prev_width=prev_width,
    )


def hi_lo_activator(
    highs: pd.Series,
    lows: pd.Series,
    closes: pd.Series,
    period: int = 8,
) -> HiLoResult:
    """
    Hi-Lo Activator: SMA of lows in uptrend, SMA of highs in downtrend.
    Bullish when price > SMA(highs); bearish when price < SMA(lows).
    Between the two lines, direction follows price vs midpoint.
    """
    sma_lows  = lows.rolling(period).mean()
    sma_highs = highs.rolling(period).mean()

    last_close     = float(closes.iloc[-1])
    last_sma_low   = float(sma_lows.iloc[-1])
    last_sma_high  = float(sma_highs.iloc[-1])

    if last_close > last_sma_high:
        direction = "bullish"
        value     = last_sma_low
    elif last_close < last_sma_low:
        direction = "bearish"
        value     = last_sma_high
    else:
        midpoint  = (last_sma_low + last_sma_high) / 2
        direction = "bullish" if last_close >= midpoint else "bearish"
        value     = last_sma_low if direction == "bullish" else last_sma_high

    return HiLoResult(value=round(value, 5), direction=direction)


def atr_stop_indicator(
    highs: pd.Series,
    lows: pd.Series,
    closes: pd.Series,
    period: int = 14,
    mult: float = 2.0,
) -> ATRStopResult:
    """
    ATR Stop (Chandelier Exit).
    Long stop  = highest_close(period) - mult * ATR
    Short stop = lowest_close(period)  + mult * ATR
    Bullish when price >= long stop; bearish otherwise.
    """
    atr_val  = atr(highs, lows, closes, period)
    last_close = float(closes.iloc[-1])
    highest  = float(closes.rolling(period).max().iloc[-1])
    lowest   = float(closes.rolling(period).min().iloc[-1])

    long_stop  = highest - mult * atr_val
    short_stop = lowest  + mult * atr_val

    if last_close >= long_stop:
        return ATRStopResult(value=round(long_stop, 5),  direction="bullish")
    return ATRStopResult(value=round(short_stop, 5), direction="bearish")


def parabolic_sar(
    highs: pd.Series,
    lows: pd.Series,
    closes: pd.Series,
    af_start: float = 0.02,
    af_max: float = 0.2,
) -> SARResult:
    """Parabolic SAR — stop and reversal method."""
    h = highs.values
    l = lows.values
    c = closes.values

    if len(c) < 2:
        return SARResult(value=c[-1], direction="bullish")

    # Simplified implementation: track trend and SAR
    bull = c[-1] > c[-2]
    sar_val = l[-2] if bull else h[-2]
    af = af_start
    ep = h[-1] if bull else l[-1]

    for i in range(2, len(c)):
        if bull:
            sar_val = sar_val + af * (ep - sar_val)
            sar_val = min(sar_val, l[i - 1], l[i - 2])
            if l[i] < sar_val:
                bull = False
                sar_val = ep
                ep = l[i]
                af = af_start
            else:
                if h[i] > ep:
                    ep = h[i]
                    af = min(af + af_start, af_max)
        else:
            sar_val = sar_val + af * (ep - sar_val)
            sar_val = max(sar_val, h[i - 1], h[i - 2])
            if h[i] > sar_val:
                bull = True
                sar_val = ep
                ep = h[i]
                af = af_start
            else:
                if l[i] < ep:
                    ep = l[i]
                    af = min(af + af_start, af_max)

    direction = "bullish" if bull else "bearish"
    return SARResult(value=round(float(sar_val), 5), direction=direction)


def ema(closes: pd.Series, period: int = 8) -> float:
    return round(float(_ema(closes, period).iloc[-1]), 5)


def vwap(closes: pd.Series, volumes: pd.Series) -> float:
    """
    Session VWAP — uses all bars provided (should be intraday from session open).
    """
    if volumes.sum() == 0:
        return round(float(closes.iloc[-1]), 5)
    return round(float((closes * volumes).sum() / volumes.sum()), 5)


def sma(closes: pd.Series, period: int) -> float:
    return round(float(closes.rolling(period).mean().iloc[-1]), 5)


def pivot_points(high: float, low: float, close: float) -> PivotResult:
    """Standard Pivot Points from previous session H/L/C."""
    pp = (high + low + close) / 3
    r1 = 2 * pp - low
    s1 = 2 * pp - high
    r2 = pp + (high - low)
    s2 = pp - (high - low)
    r3 = high + 2 * (pp - low)
    s3 = low - 2 * (high - pp)
    return PivotResult(
        pp=round(pp, 5),
        r1=round(r1, 5), r2=round(r2, 5), r3=round(r3, 5),
        s1=round(s1, 5), s2=round(s2, 5), s3=round(s3, 5),
    )


def atr(highs: pd.Series, lows: pd.Series, closes: pd.Series, period: int = 14) -> float:
    """Average True Range."""
    prev_close = closes.shift(1)
    tr = pd.concat([
        highs - lows,
        (highs - prev_close).abs(),
        (lows - prev_close).abs(),
    ], axis=1).max(axis=1)
    return round(float(tr.rolling(period).mean().iloc[-1]), 6)


def weis_wave(closes: pd.Series, volumes: pd.Series, period: int = 3) -> float:
    """
    Weis Wave proxy: cumulative volume weighted by price direction.
    Positive = buying pressure, negative = selling pressure.
    """
    direction = closes.diff().apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0))
    wave = (direction * volumes).rolling(period).sum()
    return round(float(wave.iloc[-1]), 2)


def adx_indicator(
    highs: pd.Series,
    lows: pd.Series,
    closes: pd.Series,
    period: int = 14,
) -> float:
    """Average Directional Index (Wilder, 14-period). Returns 20.0 if insufficient data."""
    if len(closes) < period * 2 + 5:
        return 20.0

    prev_high  = highs.shift(1)
    prev_low   = lows.shift(1)
    prev_close = closes.shift(1)

    up_move   = highs - prev_high
    down_move = prev_low - lows

    plus_dm  = pd.Series(
        np.where((up_move > down_move) & (up_move > 0), up_move, 0.0),
        index=closes.index,
    )
    minus_dm = pd.Series(
        np.where((down_move > up_move) & (down_move > 0), down_move, 0.0),
        index=closes.index,
    )

    tr = pd.concat([
        highs - lows,
        (highs - prev_close).abs(),
        (lows  - prev_close).abs(),
    ], axis=1).max(axis=1)

    tr_s       = tr.ewm(com=period - 1, adjust=False).mean()
    plus_dm_s  = plus_dm.ewm(com=period - 1, adjust=False).mean()
    minus_dm_s = minus_dm.ewm(com=period - 1, adjust=False).mean()

    plus_di  = 100.0 * plus_dm_s  / tr_s.replace(0, np.nan)
    minus_di = 100.0 * minus_dm_s / tr_s.replace(0, np.nan)

    dx = 100.0 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    adx_series = dx.ewm(com=period - 1, adjust=False).mean()

    last = adx_series.iloc[-1]
    return round(float(last), 2) if not np.isnan(last) else 20.0


def rsi_14(closes: pd.Series, period: int = 14) -> float:
    """
    RSI(14) via Wilder smoothing (EWM com=period-1).
    Devolve 50.0 se não houver dados suficientes ou resultado NaN.
    """
    if len(closes) < period + 1:
        return 50.0
    delta = closes.diff()
    gain = delta.clip(lower=0).ewm(com=period - 1, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(com=period - 1, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi_series = 100.0 - (100.0 / (1.0 + rs))
    last = rsi_series.iloc[-1]
    return round(float(last), 2) if not np.isnan(last) else 50.0


# ---------------------------------------------------------------------------
# Main bundle builder
# ---------------------------------------------------------------------------

def compute_bundle(
    symbol: str,
    timeframe: str,
    df: pd.DataFrame,
    prev_session_high: float = 0.0,
    prev_session_low: float = 0.0,
    prev_session_close: float = 0.0,
    prev_bb_width: float = 0.0,
) -> IndicatorBundle | None:
    """
    Compute all indicators from an OHLCV DataFrame.
    DataFrame must have columns: open, high, low, close, volume (lowercase).
    Requires at least 100 rows for reliable MA100.
    """
    if df is None or len(df) < 30:
        return None

    closes = df["close"]
    highs = df["high"]
    lows = df["low"]
    volumes = df.get("volume", pd.Series([1.0] * len(df), index=df.index))

    bundle = IndicatorBundle(symbol=symbol, timeframe=timeframe)
    bundle.close = round(float(closes.iloc[-1]), 5)
    bundle.volume = round(float(volumes.iloc[-1]), 2)

    bundle.macd = macd(closes)
    bundle.bollinger = bollinger(closes, period=10, prev_width=prev_bb_width)
    bundle.hi_lo = hi_lo_activator(highs, lows, closes)
    bundle.atr_stop = atr_stop_indicator(highs, lows, closes)
    bundle.sar = parabolic_sar(highs, lows, closes)
    bundle.ema8 = ema(closes, 8)
    bundle.vwap = vwap(closes, volumes)
    bundle.ma50 = sma(closes, 50) if len(closes) >= 50 else 0.0
    bundle.ma100 = sma(closes, 100) if len(closes) >= 100 else 0.0
    bundle.weis_wave = weis_wave(closes, volumes)
    bundle.atr = atr(highs, lows, closes)
    bundle.rsi = rsi_14(closes)
    bundle.adx = adx_indicator(highs, lows, closes)

    if prev_session_high and prev_session_low and prev_session_close:
        bundle.pivot = pivot_points(prev_session_high, prev_session_low, prev_session_close)

    return bundle
