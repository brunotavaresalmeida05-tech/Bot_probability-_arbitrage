# src/technical/smc/order_blocks.py
# OrderBlockDetector — detecta Order Blocks institucionais.
#
# Definição: a última vela bearish antes de um impulso bullish forte
#            (ou última vela bullish antes de um impulso bearish forte).
# Representa zonas onde institucionais colocaram ordens de grande volume.

from __future__ import annotations

import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import Optional


# ---------------------------------------------------------------------------
# Data Class
# ---------------------------------------------------------------------------

@dataclass
class OrderBlock:
    """
    Uma zona de Order Block identificada no gráfico.

    A zona é definida pelo high e low da vela que formou o OB.
    O preço tende a reagir quando regressa a esta zona.
    """
    direction:   str    # 'bullish' | 'bearish'
    high:        float  # topo da zona OB
    low:         float  # fundo da zona OB
    midpoint:    float  # meio da zona (high + low) / 2
    strength:    float  # 0.0–1.0 — força institucional do bloco
    timeframe:   str    # timeframe onde foi detectado ('M15', 'H1', etc.)
    candles_ago: int    # há quantas barras foi formado
    mitigated:   bool   # True se preço já regressou à zona
    index:       int    # posição no DataFrame

    @property
    def size(self) -> float:
        return self.high - self.low

    def contains(self, price: float, margin: float = 0.0) -> bool:
        """True se o preço está dentro da zona OB (com margem opcional)."""
        return (self.low - margin) <= price <= (self.high + margin)

    def __repr__(self) -> str:
        return (
            f"OrderBlock({self.direction} "
            f"[{self.low:.5f}–{self.high:.5f}] "
            f"str={self.strength:.2f} "
            f"ago={self.candles_ago} "
            f"mit={self.mitigated})"
        )


# ---------------------------------------------------------------------------
# OrderBlockDetector
# ---------------------------------------------------------------------------

class OrderBlockDetector:
    """
    Detecta Order Blocks institucionais em dados OHLCV.

    Algoritmo:
    1. Percorre as últimas `lookback_bars` barras
    2. Identifica movimentos impulsivos: corpo > min_impulse_atr × ATR
    3. A vela imediatamente anterior ao impulso = Order Block
    4. Valida: o impulso deve ter quebrado estrutura (BOS confirmado)
    5. Calcula força = f(volume relativo, tamanho do impulso, ATR)
    6. Verifica se já foi mitigado (preço regressou à zona)

    Parâmetros (do smc_config.yaml → order_blocks):
        lookback_bars:        barras para trás a analisar
        min_impulse_atr:      impulso mínimo em múltiplos de ATR
        max_age_bars:         OBs mais antigos são ignorados
        mitigation_threshold: % do OB que pode ser tocada antes de mitigation
        min_strength:         força mínima para considerar o OB válido
        proximity_atr_mult:   margem de proximidade em múltiplos de ATR
    """

    MIN_BARS_REQUIRED = 10

    def __init__(self, config: dict | None = None, timeframe: str = "M15"):
        cfg = config or {}
        self.lookback_bars        = int(cfg.get("lookback_bars", 50))
        self.min_impulse_atr      = float(cfg.get("min_impulse_atr", 1.5))
        self.max_age_bars         = int(cfg.get("max_age_bars", 30))
        self.mitigation_threshold = float(cfg.get("mitigation_threshold", 0.50))
        self.min_strength         = float(cfg.get("min_strength", 0.40))
        self.proximity_atr_mult   = float(cfg.get("proximity_atr_mult", 0.30))
        self.timeframe            = timeframe

    # ------------------------------------------------------------------
    # Interface pública
    # ------------------------------------------------------------------

    def detect(
        self,
        df: pd.DataFrame,
        atr: float,
        current_price: float,
    ) -> tuple[Optional[OrderBlock], Optional[OrderBlock]]:
        """
        Detecta o Order Block bullish e bearish mais próximos do preço actual.

        Args:
            df:            DataFrame com colunas open, high, low, close, volume
            atr:           ATR actual (usado para filtros de impulso e proximidade)
            current_price: preço actual (close da última barra)

        Returns:
            (nearest_bullish_ob, nearest_bearish_ob)
            Qualquer um pode ser None se não encontrado.
        """
        if df is None or len(df) < self.MIN_BARS_REQUIRED or atr <= 0:
            return None, None

        opens  = df["open"].values.astype(float)
        highs  = df["high"].values.astype(float)
        lows   = df["low"].values.astype(float)
        closes = df["close"].values.astype(float)

        # Volume (usa ones se não disponível)
        if "volume" in df.columns:
            volumes = df["volume"].values.astype(float)
        elif "tick_volume" in df.columns:
            volumes = df["tick_volume"].values.astype(float)
        else:
            volumes = np.ones(len(df))

        # Calcula média de volume para normalização
        avg_volume = np.mean(volumes) if np.mean(volumes) > 0 else 1.0

        n          = len(df)
        start_idx  = max(0, n - self.lookback_bars)

        bullish_obs: list[OrderBlock] = []
        bearish_obs: list[OrderBlock] = []

        # Percorre barras — precisa de pelo menos 2 barras à frente para
        # confirmar o impulso (i = OB candidate, i+1 = impulse bar)
        for i in range(start_idx, n - 2):
            candles_ago = n - 1 - i

            # Ignora OBs demasiado antigos
            if candles_ago > self.max_age_bars:
                continue

            ob_open  = opens[i]
            ob_high  = highs[i]
            ob_low   = lows[i]
            ob_close = closes[i]
            ob_body  = abs(ob_close - ob_open)

            # Barra seguinte — início do possível impulso
            imp_open  = opens[i + 1]
            imp_high  = highs[i + 1]
            imp_low   = lows[i + 1]
            imp_close = closes[i + 1]
            imp_body  = abs(imp_close - imp_open)

            # ----------------------------------------------------------
            # BULLISH ORDER BLOCK
            # Condições:
            #   1. Vela OB é bearish (close < open)
            #   2. Vela seguinte é bullish e impulsiva (corpo > min_impulse × ATR)
            #   3. Impulso fecha acima do high do OB (quebra estrutura)
            # ----------------------------------------------------------
            ob_is_bearish  = ob_close < ob_open
            imp_is_bullish = imp_close > imp_open
            impulse_strong = imp_body >= self.min_impulse_atr * atr
            breaks_above   = imp_close > ob_high

            if ob_is_bearish and imp_is_bullish and impulse_strong and breaks_above:
                strength = self._calculate_strength(
                    ob_body, imp_body, atr,
                    volumes[i], avg_volume,
                )
                if strength >= self.min_strength:
                    mitigated = self._check_mitigation(
                        closes[i + 2:],
                        ob_high, ob_low,
                        direction="bullish",
                    )
                    obs = OrderBlock(
                        direction   = "bullish",
                        high        = ob_high,
                        low         = ob_low,
                        midpoint    = (ob_high + ob_low) / 2,
                        strength    = strength,
                        timeframe   = self.timeframe,
                        candles_ago = candles_ago,
                        mitigated   = mitigated,
                        index       = i,
                    )
                    bullish_obs.append(obs)

            # ----------------------------------------------------------
            # BEARISH ORDER BLOCK
            # Condições:
            #   1. Vela OB é bullish (close > open)
            #   2. Vela seguinte é bearish e impulsiva
            #   3. Impulso fecha abaixo do low do OB (quebra estrutura)
            # ----------------------------------------------------------
            ob_is_bullish  = ob_close > ob_open
            imp_is_bearish = imp_close < imp_open
            breaks_below   = imp_close < ob_low

            if ob_is_bullish and imp_is_bearish and impulse_strong and breaks_below:
                strength = self._calculate_strength(
                    ob_body, imp_body, atr,
                    volumes[i], avg_volume,
                )
                if strength >= self.min_strength:
                    mitigated = self._check_mitigation(
                        closes[i + 2:],
                        ob_high, ob_low,
                        direction="bearish",
                    )
                    obs = OrderBlock(
                        direction   = "bearish",
                        high        = ob_high,
                        low         = ob_low,
                        midpoint    = (ob_high + ob_low) / 2,
                        strength    = strength,
                        timeframe   = self.timeframe,
                        candles_ago = candles_ago,
                        mitigated   = mitigated,
                        index       = i,
                    )
                    bearish_obs.append(obs)

        # Selecciona o OB mais próximo do preço actual (não mitigado preferido)
        nearest_bull = self._select_nearest(bullish_obs, current_price, "bullish")
        nearest_bear = self._select_nearest(bearish_obs, current_price, "bearish")

        return nearest_bull, nearest_bear

    def price_in_ob(
        self,
        ob: Optional[OrderBlock],
        current_price: float,
        atr: float,
    ) -> bool:
        """
        True se o preço actual está dentro da zona do OB
        (com margem de proximidade em ATR).
        """
        if ob is None or ob.mitigated:
            return False
        margin = atr * self.proximity_atr_mult
        return ob.contains(current_price, margin=margin)

    # ------------------------------------------------------------------
    # Cálculo de força
    # ------------------------------------------------------------------

    def _calculate_strength(
        self,
        ob_body:    float,
        imp_body:   float,
        atr:        float,
        volume:     float,
        avg_volume: float,
    ) -> float:
        """
        Força do OB — combina 3 factores:

        1. Tamanho do impulso relativo ao ATR         (peso 0.50)
           Impulso forte = mais institucional

        2. Volume relativo da barra OB                (peso 0.30)
           Volume alto = mais participação institucional

        3. Tamanho do corpo do OB relativo ao ATR     (peso 0.20)
           Corpo maior = mais convicção na vela OB

        Cada factor normalizado a [0.0, 1.0] antes de ponderar.
        """
        # Factor 1: impulso
        impulse_factor = min(1.0, imp_body / (self.min_impulse_atr * atr * 2))

        # Factor 2: volume relativo
        vol_ratio      = volume / (avg_volume + 1e-9)
        volume_factor  = min(1.0, vol_ratio / 2.0)   # 2× avg vol = score máximo

        # Factor 3: corpo do OB
        body_factor    = min(1.0, ob_body / (atr + 1e-9))

        strength = (
            0.50 * impulse_factor +
            0.30 * volume_factor  +
            0.20 * body_factor
        )

        return round(min(1.0, max(0.0, strength)), 3)

    # ------------------------------------------------------------------
    # Verificação de mitigação
    # ------------------------------------------------------------------

    def _check_mitigation(
        self,
        subsequent_closes: np.ndarray,
        ob_high: float,
        ob_low:  float,
        direction: str,
    ) -> bool:
        """
        Verifica se o OB foi mitigado — i.e. se o preço regressou à zona
        depois do impulso inicial.

        Bullish OB: mitigado se close penetrou >= mitigation_threshold
                    da distância desde ob_low até ob_high
        Bearish OB: mitigado se close penetrou >= mitigation_threshold
                    da distância desde ob_high até ob_low
        """
        if len(subsequent_closes) == 0:
            return False

        ob_size = ob_high - ob_low
        if ob_size <= 0:
            return False

        threshold = self.mitigation_threshold

        for close in subsequent_closes:
            if direction == "bullish":
                # Preço desceu de volta ao OB
                if close <= ob_high:
                    penetration = (ob_high - close) / ob_size
                    if penetration >= threshold:
                        return True
            else:  # bearish
                # Preço subiu de volta ao OB
                if close >= ob_low:
                    penetration = (close - ob_low) / ob_size
                    if penetration >= threshold:
                        return True

        return False

    # ------------------------------------------------------------------
    # Selecção do OB mais próximo
    # ------------------------------------------------------------------

    def _select_nearest(
        self,
        obs: list[OrderBlock],
        current_price: float,
        direction: str,
    ) -> Optional[OrderBlock]:
        """
        Selecciona o OB mais relevante para o preço actual.

        Prioridade:
        1. OBs não mitigados (mais válidos)
        2. Mais próximo do preço actual
        3. Se empate em distância — maior força

        Para OB bullish: procura OBs abaixo do preço (suporte)
        Para OB bearish: procura OBs acima do preço (resistência)
        """
        if not obs:
            return None

        # Separa mitigados de não-mitigados
        valid   = [ob for ob in obs if not ob.mitigated]
        invalid = [ob for ob in obs if ob.mitigated]

        # Tenta primeiro os não-mitigados
        candidates = valid if valid else invalid

        if direction == "bullish":
            # OBs abaixo do preço — suporte
            below = [ob for ob in candidates if ob.midpoint <= current_price]
            pool  = below if below else candidates
        else:
            # OBs acima do preço — resistência
            above = [ob for ob in candidates if ob.midpoint >= current_price]
            pool  = above if above else candidates

        if not pool:
            return None

        # Ordena por distância ao preço (mais próximo primeiro)
        pool.sort(key=lambda ob: abs(ob.midpoint - current_price))

        # Em caso de empate nos 2 mais próximos → maior força
        if len(pool) >= 2:
            d0 = abs(pool[0].midpoint - current_price)
            d1 = abs(pool[1].midpoint - current_price)
            if abs(d0 - d1) < 1e-6 and pool[1].strength > pool[0].strength:
                return pool[1]

        return pool[0]
