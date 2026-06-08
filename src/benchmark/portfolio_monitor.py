from __future__ import annotations
"""
Benchmark Portfolio Monitor — V9

Monitors 30+ benchmark assets to extract global capital flow context.
These assets are NEVER traded — they are reference/context only.

Sources: yfinance (covers all listed tickers)
Refresh: every 5 minutes (background thread)

The output feeds MacroContext and the prep workflow with:
  - Where institutional money is flowing (risk-on / risk-off)
  - Treasury curve shape from actual yield quotes
  - ADR flow (carry trade detection)
  - Precious metals complex health
  - Equity breadth
"""
import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


# Full benchmark universe from architecture spec
BENCHMARK_UNIVERSE: dict[str, str] = {
    # Gold
    "XAUUSD":    "GC=F",            # Gold Futures
    "XAUEUR":    "IAU",             # iShares Gold ETF (proxy EUR gold — yfinance XAUEUR=X delisted)
    # Oil
    "WTI":       "CL=F",
    "BRENT":     "BZ=F",
    # Dollar — DX=F delisted on yfinance; use UUP (Bullish USD ETF) as proxy
    "DXY":       "UUP",
    # US Equity
    "SP500":     "ES=F",            # S&P 500 Futures
    "VIX":       "^VIX",
    "VIX_FUT":   "VIXY",           # VX=F delisted; use VIXY ETF as VIX futures proxy
    "DJIA":      "^DJI",
    "NASDAQ":    "^IXIC",
    "ISHARES":   "IWM",
    # ETFs metals
    "GLTR":      "GLTR",            # precious metals basket
    "PPLT":      "PPLT",            # platinum ETF
    "SGOL":      "SGOL",            # Swiss gold ETF
    # Iron Ore proxy
    "IRON_PROXY":"TIO=F",
    # T-Note Futures
    "TU":        "ZT=F",            # 2Y T-Note futures
    "FV":        "ZF=F",            # 5Y T-Note futures
    "TY":        "ZN=F",            # 10Y T-Note futures
    # Treasury Yields (Yahoo Finance)
    "US10Y":     "^TNX",
    "US5Y":      "^FVX",
    "US30Y":     "^TYX",
    "US3M":      "^IRX",
    # ADR / EM Flows
    "EEM":       "EEM",             # EM ETF
    "FXI":       "FXI",             # China ETF
    "EWZ":       "EWZ",             # Brazil ETF
    "SPY":       "SPY",
    "QQQ":       "QQQ",
    # Other
    "FRPH":      "FRPH",            # FRP Holding
}


@dataclass
class BenchmarkQuote:
    symbol: str
    ticker: str
    last: float = 0.0
    prev_close: float = 0.0
    change_pct: float = 0.0
    high: float = 0.0
    low: float = 0.0
    volume: float = 0.0
    updated_at: str = ""


@dataclass
class BenchmarkSnapshot:
    quotes: dict[str, BenchmarkQuote] = field(default_factory=dict)
    updated_at: str = ""
    # Derived signals
    risk_on_score: float = 0.0      # [-1, +1]: positive = risk on
    treasury_demand: float = 0.0    # [-1, +1]: positive = high treasury demand (risk-off)
    gold_signal: str = "neutral"    # rising | falling | neutral
    carry_trade_active: bool = False

    def get(self, symbol: str) -> BenchmarkQuote | None:
        return self.quotes.get(symbol)

    def to_summary(self) -> dict:
        return {
            "risk_on_score": round(self.risk_on_score, 4),
            "treasury_demand": round(self.treasury_demand, 4),
            "gold_signal": self.gold_signal,
            "carry_trade_active": self.carry_trade_active,
            "assets_tracked": len(self.quotes),
            "updated_at": self.updated_at,
            "key_levels": {
                sym: {
                    "last": q.last,
                    "change_pct": round(q.change_pct * 100, 3),
                }
                for sym, q in self.quotes.items()
                if sym in ("VIX", "DXY", "SP500", "XAUUSD", "US10Y", "EEM")
            },
        }


class BenchmarkPortfolioMonitor:
    """
    Background monitor for the 30+ benchmark asset universe.
    Does NOT trade — context only.
    """

    def __init__(self, update_interval: int = 300):
        self._interval = update_interval
        self._lock = threading.Lock()
        self._snapshot = BenchmarkSnapshot()
        self._thread: threading.Thread | None = None
        self._running = False

    @property
    def snapshot(self) -> BenchmarkSnapshot:
        with self._lock:
            return self._snapshot

    def start(self):
        self._running = True
        self._update()
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="benchmark-monitor"
        )
        self._thread.start()
        logger.info(f"BenchmarkPortfolioMonitor started ({len(BENCHMARK_UNIVERSE)} assets)")

    def stop(self):
        self._running = False

    def _update(self):
        quotes = self._fetch_all()
        snap = BenchmarkSnapshot(
            quotes=quotes,
            updated_at=datetime.now(timezone.utc).isoformat(),
        )
        snap.risk_on_score = self._compute_risk_on_score(quotes)
        snap.treasury_demand = self._compute_treasury_demand(quotes)
        snap.gold_signal = self._compute_gold_signal(quotes)
        snap.carry_trade_active = self._detect_carry_trade(quotes)

        with self._lock:
            self._snapshot = snap

        logger.info(
            f"Benchmark updated: risk_on={snap.risk_on_score:+.2f} "
            f"treasury={snap.treasury_demand:+.2f} gold={snap.gold_signal} "
            f"carry={snap.carry_trade_active}"
        )

    def _fetch_all(self) -> dict[str, BenchmarkQuote]:
        quotes = {}
        try:
            import yfinance as yf
            tickers_list = list(BENCHMARK_UNIVERSE.values())
            # Batch download for efficiency
            data = yf.download(
                tickers_list, period="2d", interval="1d",
                auto_adjust=True, progress=False, threads=True
            )
            ts_now = datetime.now(timezone.utc).isoformat()

            for sym, ticker_sym in BENCHMARK_UNIVERSE.items():
                try:
                    t = yf.Ticker(ticker_sym)
                    info = t.info
                    last = float(info.get("regularMarketPrice") or 0)
                    prev = float(info.get("previousClose") or last)
                    high = float(info.get("regularMarketDayHigh") or last)
                    low  = float(info.get("regularMarketDayLow") or last)
                    vol  = float(info.get("regularMarketVolume") or 0)
                    chg  = (last - prev) / prev if prev else 0.0

                    quotes[sym] = BenchmarkQuote(
                        symbol=sym, ticker=ticker_sym,
                        last=last, prev_close=prev,
                        change_pct=chg, high=high, low=low,
                        volume=vol, updated_at=ts_now,
                    )
                except Exception:
                    pass
        except Exception as e:
            logger.warning(f"Benchmark fetch error: {e}")
        return quotes

    def _compute_risk_on_score(self, q: dict) -> float:
        scores = []
        # SPY or SP500 rising = risk on
        for k in ("SPY", "SP500"):
            if k in q and q[k].change_pct != 0:
                scores.append(1 if q[k].change_pct > 0 else -1)
        # VIX falling = risk on
        if "VIX" in q:
            scores.append(-1 if q["VIX"].change_pct > 0 else 1)
        # EEM rising = risk on
        if "EEM" in q:
            scores.append(1 if q["EEM"].change_pct > 0 else -1)
        # DXY falling = risk on
        if "DXY" in q:
            scores.append(-1 if q["DXY"].change_pct > 0 else 1)
        return round(sum(scores) / len(scores), 4) if scores else 0.0

    def _compute_treasury_demand(self, q: dict) -> float:
        """High treasury demand = yields falling = risk-off."""
        scores = []
        for k in ("US10Y", "US5Y", "TY", "FV", "TU"):
            if k in q:
                # Yield falling = price rising = high demand = risk-off (+1)
                scores.append(-1 if q[k].change_pct > 0 else 1)
        return round(sum(scores) / len(scores), 4) if scores else 0.0

    def _compute_gold_signal(self, q: dict) -> str:
        for k in ("XAUUSD", "GLTR", "SGOL"):
            if k in q and q[k].change_pct != 0:
                return "rising" if q[k].change_pct > 0.002 else ("falling" if q[k].change_pct < -0.002 else "neutral")
        return "neutral"

    def _detect_carry_trade(self, q: dict) -> bool:
        eem_up = q.get("EEM", BenchmarkQuote("", "")).change_pct > 0.003
        dxy_dn = q.get("DXY", BenchmarkQuote("", "")).change_pct < -0.002
        return eem_up and dxy_dn

    def _loop(self):
        while self._running:
            time.sleep(self._interval)
            try:
                self._update()
            except Exception as e:
                logger.error(f"BenchmarkMonitor loop error: {e}")
