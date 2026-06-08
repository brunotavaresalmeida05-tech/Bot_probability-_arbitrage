"""server/routers/dashboard_api.py — Endpoints consumed by dashboard/js/app.js."""
from __future__ import annotations
from fastapi import APIRouter, Query
from server.state_reader import read_state, read_history

router = APIRouter(tags=["dashboard"])


@router.get("/account")
def get_account():
    state = read_state()
    acc = state.get("account", {})
    positions = state.get("positions", [])
    return {
        "balance":          acc.get("balance", 0),
        "equity":           acc.get("equity", 0),
        "margin":           acc.get("margin", 0),
        "free_margin":      acc.get("free_margin", 0),
        "profit":           acc.get("profit", 0),
        "daily_pnl":        acc.get("daily_pnl", 0),
        "currency":         acc.get("currency", "EUR"),
        "positions_count":  len(positions),
    }


@router.get("/positions")
def get_positions():
    state = read_state()
    return [
        {
            "symbol": p.get("symbol", ""),
            "type":   p.get("type", p.get("direction", "BUY")),
            "entry":  p.get("price_open", p.get("entry_price", 0)),
            "profit": p.get("profit", 0),
            "volume": p.get("volume", 0),
        }
        for p in state.get("positions", [])
    ]


@router.get("/strategies")
def get_strategies():
    state = read_state()
    signals = state.get("signals", {})
    counts: dict[str, dict] = {}
    for key, val in signals.items():
        strat = key.split(":")[0] if ":" in key else key
        entry = counts.setdefault(strat, {"name": strat, "trades": 0, "wins": 0,
                                           "win_rate": 0, "avg_pnl": 0.0, "sharpe": 0.0})
        if isinstance(val, dict):
            entry["trades"] += 1
            if val.get("signal") in ("BUY", "SELL"):
                entry["wins"] += 1
    for v in counts.values():
        n = v["trades"]
        v["win_rate"] = round(v["wins"] / n * 100, 1) if n > 0 else 0
    return list(counts.values())


@router.get("/symbols")
def get_symbols():
    state = read_state()
    market = state.get("market", {})
    signals = state.get("signals", {})
    result = []
    seen: set[str] = set()
    for key, val in signals.items():
        sym = key.split(":")[-1] if ":" in key else key
        if sym in seen:
            continue
        seen.add(sym)
        mkt = market.get(sym, {})
        sig = val.get("signal", "HOLD") if isinstance(val, dict) else str(val)
        result.append({
            "symbol":  sym,
            "z_score": round(val.get("strength", 0.0), 3) if isinstance(val, dict) else 0.0,
            "price":   mkt.get("close", mkt.get("bid", 0)),
            "spread":  mkt.get("spread", 0),
            "signal":  sig,
        })
    return result


@router.get("/history")
def get_history(limit: int = 100):
    rows = read_history(limit=limit)
    return [
        {
            "date":   r.get("ts", "")[:10],
            "symbol": r.get("symbol", ""),
            "type":   r.get("direction", r.get("type", "")),
            "entry":  r.get("entry_price", r.get("price", 0)),
            "profit": r.get("profit", 0),
        }
        for r in rows
    ]


@router.get("/symbol-specs")
def get_symbol_specs():
    """Ficha técnica financeira de cada instrumento (do state.json se disponível)."""
    state = read_state()
    return state.get("symbol_specs", {})


@router.get("/pretrade")
def pretrade_check(
    symbol:    str = Query(...),
    direction: str = Query(..., pattern="^(BUY|SELL)$"),
    entry:     float = Query(...),
    sl:        float = Query(...),
    tp:        float = Query(0.0),
    lot:       float = Query(0.01),
    balance:   float = Query(10000.0),
):
    """
    On-demand pre-trade financial calculation.
    Returns notional, margin, risk, R:R, costs and viability verdict.
    Example: GET /api/pretrade?symbol=EURUSD&direction=BUY&entry=1.0850&sl=1.0820&tp=1.0910&lot=0.1&balance=5000
    """
    try:
        from src.risk.symbol_spec import SymbolSpecLoader
        from src.risk.pretrade_calculator import PreTradeCalculator
        loader = SymbolSpecLoader()
        calc   = PreTradeCalculator(loader)
        result = calc.evaluate(symbol, direction, entry, sl, tp, lot, balance)
        spec   = loader.get(symbol)
        return {
            "symbol":          result.symbol,
            "direction":       result.direction,
            "lot":             result.lot,
            "notional":        result.notional,
            "margin_required": result.margin_required,
            "stop_pts":        result.stop_pts,
            "risk_money":      result.risk_money,
            "reward_money":    result.reward_money,
            "rr_ratio":        result.rr_ratio,
            "rr_net":          result.rr_net,
            "spread_cost":     result.spread_cost,
            "swap_1d":         result.swap_1d,
            "slippage_est":    result.slippage_est,
            "total_cost":      result.total_cost,
            "cost_pct_of_risk": result.cost_pct_of_risk,
            "session_ok":      result.session_ok,
            "viable":          result.viable,
            "verdict":         result.verdict,
            "warnings":        result.warnings,
            "spec": {
                "type":        spec.instrument_type,
                "contract":    spec.contract_size,
                "tick_size":   spec.tick_size,
                "tick_value":  spec.tick_value,
                "point_value": round(spec.point_value, 6),
                "margin_rate": spec.margin_rate,
                "swap_long":   spec.swap_long,
                "swap_short":  spec.swap_short,
                "session":     spec.session_best,
                "source":      spec.source,
            },
        }
    except Exception as e:
        return {"error": str(e)}


@router.get("/phase9")
def phase9_report():
    """Phase 9 stability monitoring report."""
    try:
        from src.analytics.phase9_monitor import read_report
        return read_report()
    except Exception as e:
        return {"error": str(e)}


@router.get("/macro-profiles")
def macro_profiles():
    """
    Macro profile for each symbol: drivers, key events, risk_mode, rate sensitivity.
    Example: GET /api/macro-profiles?symbol=GOLD
    """
    from src.macro.asset_macro_profile import AssetMacroProfile
    from src.macro.interest_rate_transmission import InterestRateTransmissionEngine, _load_map
    try:
        profile = AssetMacroProfile()
        rate_eng = InterestRateTransmissionEngine()
        result = {}
        for sym in profile.all_symbols():
            p = profile.full_profile(sym)
            result[sym] = p
        return result
    except Exception as e:
        return {"error": str(e)}


@router.get("/macro-rate-environment")
def macro_rate_environment():
    """Current interest rate environment classification."""
    try:
        from src.macro.interest_rate_transmission import InterestRateTransmissionEngine
        state = read_state()
        rates = state.get("macro_policy_summary", {}).get("rates", {})
        macro = state.get("macro", {})
        engine = InterestRateTransmissionEngine()
        env = engine.classify(
            us10y           = rates.get("us10y", 4.5),
            us2y            = rates.get("us2y", 4.0),
            dxy_zscore      = 0.0,
            inflation_score = macro.get("inflation_score", 0.3),
        )
        return {
            "direction":       env.direction,
            "prolonged_mode":  env.prolonged_mode,
            "is_hawkish":      env.is_hawkish,
            "is_dovish":       env.is_dovish,
            "real_yield_up":   env.real_yield_up,
            "real_yield_est":  env.real_yield_est,
            "us10y":           env.us10y,
            "us2y":            env.us2y,
            "spread":          env.spread,
            "consumer_effect": engine.consumer_effect(env),
            "equity_effect":   engine.equity_effect(env),
            "per_symbol": {
                sym: engine.symbol_mult(sym, env)
                for sym in ["EURUSD","USDJPY","GOLD","UsaTec","BTCUSD","USDCAD","AUDUSD"]
            },
        }
    except Exception as e:
        return {"error": str(e)}


@router.get("/instrument-selection")
def instrument_selection():
    """
    Shows which instrument is selected as primary for each underlying
    (resolves spot vs future duplicates).
    """
    try:
        from src.risk.symbol_spec import SymbolSpecLoader
        from src.risk.instrument_selector import InstrumentSelector
        loader   = SymbolSpecLoader()
        selector = InstrumentSelector(loader)
        all_syms = list({
            "EURUSD","GBPUSD","USDJPY","AUDUSD","USDCHF","USDCAD",
            "Usa500","USA500Jun26","UsaTec","USAtec","US100Jun26",
            "Ger40","Ger40Jun26","UK100","UK100Jun26","Jp225","Jp225Jun26",
            "GOLD","SILVER","LCrude","Brent","NGas",
            "BTCUSD","ETHUSD",
        })
        return selector.report(all_syms)
    except Exception as e:
        return {"error": str(e)}
