"""Tests for src/engine/regime_router.py (Fase 9A / 9B EMA migration)."""
import pytest
from src.engine.regime_router import detect, RegimeState, RegimeResult
from src.technical.indicators import IndicatorBundle, MACDResult, ATRStopResult
from src.macro.macro_context import MacroContext


def _bundle(
    symbol: str = "EURUSD",
    adx: float = 20.0,
    ema20: float = 1.1050,
    ema50: float = 1.1000,
    ema100: float = 1.0900,
    macd_dir: str = "bullish",
    atr_dir: str = "bullish",
) -> IndicatorBundle:
    b = IndicatorBundle(symbol=symbol, timeframe="M15")
    b.adx    = adx
    b.ema20  = ema20
    b.ema50  = ema50
    b.ema100 = ema100
    b.macd   = MACDResult(macd_line=0.001, signal_line=0.0, direction=macd_dir)
    b.atr_stop = ATRStopResult(value=1.08, direction=atr_dir)
    return b


def _macro(vix: float = 20.0, vix_regime: str = "normal") -> MacroContext:
    m = MacroContext()
    m.vix = vix
    m.vix_regime = vix_regime
    return m


# ── TRENDING ──────────────────────────────────────────────────────────────────

class TestTrending:
    def test_trending_up_strong_adx(self):
        b = _bundle(adx=30.0, ema50=1.10, ema100=1.09)
        r = detect(b, _macro())
        assert r.state == RegimeState.TRENDING_UP
        assert r.direction == "bullish"
        assert r.lot_context == 1.0

    def test_trending_down_strong_adx(self):
        b = _bundle(adx=28.0, ema20=1.075, ema50=1.08, ema100=1.10,
                    macd_dir="bearish", atr_dir="bearish")
        r = detect(b, _macro())
        assert r.state == RegimeState.TRENDING_DOWN
        assert r.direction == "bearish"
        assert r.lot_context == 1.0

    def test_borderline_trending_uses_085(self):
        b = _bundle(adx=22.0, ema50=1.10, ema100=1.09)
        r = detect(b, _macro())
        assert r.state in (RegimeState.TRENDING_UP, RegimeState.TRENDING_DOWN)
        assert r.lot_context == 0.85

    def test_confidence_scales_with_adx(self):
        # adx=40 → adx_conf=1.0; ema aligned → +0.10 bonus → clamped to 1.0
        b = _bundle(adx=40.0, ema50=1.10, ema100=1.09)
        r = detect(b, _macro())
        assert r.confidence == 1.0

    def test_ema_alignment_bonus_applied(self):
        # adx=28 → adx_conf=0.70; ema20>ema50>ema100 → +0.10 → conf=0.80
        b = _bundle(adx=28.0, ema20=1.105, ema50=1.100, ema100=1.090)
        r = detect(b, _macro())
        assert r.confidence >= 0.79

    def test_ema_misaligned_no_bonus(self):
        # ema20 between ema50 and ema100 → not aligned → no bonus
        b = _bundle(adx=28.0, ema20=1.095, ema50=1.100, ema100=1.090)
        r = detect(b, _macro())
        # conf = 28/40 = 0.70 (no bonus)
        assert r.confidence == pytest.approx(0.70, abs=0.01)

    def test_bearish_ema_gives_trending_down(self):
        # ema50 < ema100 (+2 bear), ema20 < ema50 (+1 bear), MACD+ATR bearish (+2)
        b = _bundle(adx=30.0, ema20=1.075, ema50=1.08, ema100=1.10,
                    macd_dir="bearish", atr_dir="bearish")
        r = detect(b, _macro())
        assert r.state == RegimeState.TRENDING_DOWN


# ── RANGING ───────────────────────────────────────────────────────────────────

class TestRanging:
    def test_low_adx_ranging(self):
        b = _bundle(adx=15.0, ema50=1.10, ema100=1.09)
        r = detect(b, _macro())
        assert r.state == RegimeState.RANGING
        assert r.lot_context == 0.75

    def test_adx_at_boundary_ranging(self):
        b = _bundle(adx=19.9, ema50=1.10, ema100=1.09)
        r = detect(b, _macro())
        assert r.state == RegimeState.RANGING

    def test_zero_adx_defaults_to_neutral(self):
        # adx=0 → uses default 20.0 (borderline); all indicators bull → lot <= 0.85
        b = _bundle(adx=0.0, ema50=1.10, ema100=1.09)
        r = detect(b, _macro())
        assert r.lot_context <= 0.85


# ── VOLATILE ──────────────────────────────────────────────────────────────────

class TestVolatile:
    def test_vix_above_30_volatile(self):
        b = _bundle(adx=30.0, ema50=1.10, ema100=1.09)
        r = detect(b, _macro(vix=32.0))
        assert r.state == RegimeState.VOLATILE
        assert r.lot_context == 0.25

    def test_vix_panic_halts_completely(self):
        b = _bundle(adx=30.0, ema50=1.10, ema100=1.09)
        r = detect(b, _macro(vix=45.0, vix_regime="panic"))
        assert r.state == RegimeState.VOLATILE
        assert r.lot_context == 0.0

    def test_vix_kill_halts_completely(self):
        b = _bundle(adx=30.0, ema50=1.10, ema100=1.09)
        r = detect(b, _macro(vix=38.0, vix_regime="kill"))
        assert r.state == RegimeState.VOLATILE
        assert r.lot_context == 0.0


# ── MACRO LOT CONTEXT ─────────────────────────────────────────────────────────

class TestMacroLotContext:
    def test_vix_alert_caps_lot_at_050(self):
        b = _bundle(adx=30.0, ema50=1.10, ema100=1.09)
        r = detect(b, _macro(vix=25.0, vix_regime="alert"))
        assert r.state in (RegimeState.TRENDING_UP, RegimeState.TRENDING_DOWN)
        assert r.lot_context == 0.50

    def test_vix_caution_caps_lot_at_075(self):
        b = _bundle(adx=30.0, ema50=1.10, ema100=1.09)
        r = detect(b, _macro(vix=22.0, vix_regime="caution"))
        assert r.state in (RegimeState.TRENDING_UP, RegimeState.TRENDING_DOWN)
        assert r.lot_context == 0.75

    def test_normal_vix_no_reduction(self):
        b = _bundle(adx=30.0, ema50=1.10, ema100=1.09)
        r = detect(b, _macro(vix=18.0, vix_regime="normal"))
        assert r.lot_context == 1.0

    def test_no_macro_returns_default(self):
        b = _bundle(adx=30.0, ema50=1.10, ema100=1.09)
        r = detect(b, macro=None)
        assert r.state in (RegimeState.TRENDING_UP, RegimeState.TRENDING_DOWN)
        assert r.lot_context == 1.0


# ── EMA VOTES ─────────────────────────────────────────────────────────────────

class TestEMAVotes:
    def test_full_bull_votes(self):
        # ema50>ema100 (+2), ema20>ema50 (+1), MACD (+1), ATR (+1) = 5 bull
        b = _bundle(adx=30.0, ema20=1.105, ema50=1.100, ema100=1.090,
                    macd_dir="bullish", atr_dir="bullish")
        r = detect(b, _macro())
        assert r.direction == "bullish"
        assert r.state == RegimeState.TRENDING_UP

    def test_mixed_ema_partial_bull(self):
        # ema50>ema100 (+2 bull), ema20<ema50 (+1 bear), MACD+ATR bull (+2) = 4 bull, 1 bear
        b = _bundle(adx=30.0, ema20=1.095, ema50=1.100, ema100=1.090,
                    macd_dir="bullish", atr_dir="bullish")
        r = detect(b, _macro())
        assert r.direction == "bullish"

    def test_inverted_ema_gives_bearish_structure(self):
        # ema50<ema100 (+2 bear), ema20<ema50 (+1 bear) = 3 bear → bear direction
        b = _bundle(adx=30.0, ema20=1.075, ema50=1.080, ema100=1.100,
                    macd_dir="bearish", atr_dir="bearish")
        r = detect(b, _macro())
        assert r.direction == "bearish"

    def test_ema_all_equal_neutral_no_votes(self):
        # All EMAs equal → no EMA votes → relies on MACD+ATR only (2 bull)
        b = _bundle(adx=30.0, ema20=1.100, ema50=1.100, ema100=1.100,
                    macd_dir="bullish", atr_dir="bullish")
        r = detect(b, _macro())
        assert r.direction == "bullish"  # MACD+ATR still give 2 bull


# ── RESULT FIELDS ─────────────────────────────────────────────────────────────

class TestResultFields:
    def test_result_has_all_fields(self):
        b = _bundle(adx=30.0)
        r = detect(b, _macro())
        assert isinstance(r, RegimeResult)
        assert r.adx > 0
        assert r.confidence >= 0.0
        assert isinstance(r.rationale, list)
        assert len(r.rationale) > 0

    def test_state_is_string_enum(self):
        b = _bundle(adx=30.0)
        r = detect(b, _macro())
        assert isinstance(r.state.value, str)
