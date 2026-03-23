"""
src/optimizer.py  —  Walk-Forward Validation (critérios adaptados ao timeframe)
"""
import pandas as pd
import numpy as np
import itertools
import threading
import time
from datetime import datetime
from typing import Optional
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import config.settings as cfg
import src.mt5_connector as mt5c
import src.logger as log

best_params: dict = {}
_optimizer_lock   = threading.Lock()
_last_run: float  = 0.0


def get_best_params() -> dict:
    with _optimizer_lock:
        return dict(best_params)


def _compute_zscore_series(close, ma_p, sd_p):
    ma = close.rolling(ma_p).mean()
    sd = close.rolling(sd_p).std(ddof=0).replace(0, np.nan)
    return (close - ma) / sd


def _compute_atr(df, period):
    h, l, c = df["high"], df["low"], df["close"]
    tr = pd.concat([h - l, (h - c.shift(1)).abs(), (l - c.shift(1)).abs()], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def _run_backtest(df, params):
    close = df["close"]
    z     = _compute_zscore_series(close, params["MA_PERIOD"], params["STDDEV_PERIOD"])
    ma    = close.rolling(params["MA_PERIOD"]).mean()
    atr   = _compute_atr(df, cfg.ATR_PERIOD)
    trades, position = [], None

    for i in range(len(df)):
        zi, ci, mi, atri = z.iloc[i], close.iloc[i], ma.iloc[i], atr.iloc[i]
        if pd.isna(zi) or pd.isna(mi) or pd.isna(atri): continue
        if position is not None:
            ptype, entry, sl = position["type"], position["entry"], position["sl"]
            if (ptype=="BUY" and ci<=sl) or (ptype=="SELL" and ci>=sl) or \
               (ptype=="BUY" and zi>=-params["Z_EXIT"]) or (ptype=="SELL" and zi<=params["Z_EXIT"]) or \
               (ptype=="BUY" and zi<=-params["Z_STOP"]) or (ptype=="SELL" and zi>=params["Z_STOP"]):
                trades.append((ci-entry) if ptype=="BUY" else (entry-ci))
                position = None
            continue
        if zi <= -params["Z_ENTER"] and ci < mi:
            position = {"type": "BUY",  "entry": ci, "sl": ci - cfg.SL_ATR_MULT * atri}
        elif zi >= params["Z_ENTER"] and ci > mi:
            position = {"type": "SELL", "entry": ci, "sl": ci + cfg.SL_ATR_MULT * atri}

    if not trades:
        return {"sharpe": -99, "win_rate": 0, "n_trades": 0}
    arr    = np.array(trades)
    sharpe = (arr.mean() / (arr.std() or 1e-9)) * np.sqrt(252)
    return {"sharpe": round(float(sharpe), 4),
            "win_rate": round(float((arr > 0).mean()), 4),
            "n_trades": len(arr)}


def _walk_forward(df, params, n_windows=3):
    total     = len(df)
    min_train = max(params["MA_PERIOD"] * 2, 50)
    if total < min_train + 15:
        return {"oos_sharpe": -99, "oos_win_rate": 0, "oos_n_trades": 0,
                "stability": 0, "windows_tested": 0}

    step = max((total - min_train) // (n_windows + 1), 15)
    oos_results = []
    for w in range(n_windows):
        train_end = min_train + (w + 1) * step
        test_end  = min(train_end + step, total)
        if train_end >= total or (test_end - train_end) < 10: break
        oos = _run_backtest(df.iloc[train_end:test_end], params)
        oos["window"] = w + 1
        oos_results.append(oos)

    if not oos_results:
        return {"oos_sharpe": -99, "oos_win_rate": 0, "oos_n_trades": 0,
                "stability": 0, "windows_tested": 0}

    sharpes   = [r["sharpe"]   for r in oos_results]
    stability = sum(1 for s in sharpes if s > 0) / len(sharpes)
    return {
        "oos_sharpe":     round(float(np.mean(sharpes) - 0.3 * np.std(sharpes)), 4),
        "oos_win_rate":   round(float(np.mean([r["win_rate"] for r in oos_results])), 4),
        "oos_n_trades":   sum(r["n_trades"] for r in oos_results),
        "stability":      round(float(stability), 4),
        "windows_tested": len(oos_results),
        "window_results": oos_results,
    }


def run_optimization(symbols=None):
    global best_params, _last_run
    symbols = symbols or cfg.SYMBOLS
    results = {}

    keys   = list(cfg.OPTIMIZER_GRID.keys())
    combos = list(itertools.product(*[cfg.OPTIMIZER_GRID[k] for k in keys]))
    if len(combos) > cfg.OPTIMIZER_MAX_TRIALS:
        np.random.shuffle(combos)
        combos = combos[:cfg.OPTIMIZER_MAX_TRIALS]

    log.info(f"OPTIMIZER: {len(combos)} combinações × {len(symbols)} símbolos", "OPT")

    for symbol in symbols:
        log.info(f"OPTIMIZER: a optimizar {symbol}...", "OPT")

        # Prioridade: M5 com 500 barras, fallback D1
        df = mt5c.get_bars(symbol, cfg.TIMEFRAME, 500)
        if df is None or len(df) < 80:
            df = mt5c.get_bars(symbol, "D1", cfg.OPTIMIZER_LOOKBACK + 50)
        if df is None or len(df) < 80:
            log.warning(f"OPTIMIZER: dados insuficientes {symbol}", "OPT")
            continue

        min_oos_trades = max(3, len(df) // 80)
        best_score, best_combo, best_wf, candidates = -np.inf, None, None, []

        for combo in combos:
            params = dict(zip(keys, combo))
            if params["MA_PERIOD"] <= params["STDDEV_PERIOD"]: continue
            if params["Z_EXIT"]    >= params["Z_ENTER"]:       continue
            if params["Z_ENTER"]   >= params["Z_STOP"]:        continue

            wf = _walk_forward(df, params, n_windows=3)
            if wf["oos_n_trades"] < min_oos_trades: continue
            if wf["oos_win_rate"] < 0.30:           continue
            if wf["stability"]    < 0.33:           continue

            score = wf["oos_sharpe"]
            candidates.append(score)
            if score > best_score:
                best_score, best_combo, best_wf = score, params, wf

        if best_combo:
            results[symbol] = {**best_combo, **best_wf, "n_candidates": len(candidates)}
            log.success(
                f"OPTIMIZER {symbol}: MA={best_combo['MA_PERIOD']} SD={best_combo['STDDEV_PERIOD']} "
                f"ZE={best_combo['Z_ENTER']} | OOS Sharpe={best_wf['oos_sharpe']:.3f} "
                f"stab={best_wf['stability']:.0%} ({len(candidates)} candidatos)",
                "OPT"
            )
        else:
            log.warning(f"OPTIMIZER {symbol}: usando defaults ({len(df)} barras disponíveis)", "OPT")

    with _optimizer_lock:
        best_params = results
    _last_run = time.time()
    _save_results(results)
    return results


def _save_results(results):
    os.makedirs(cfg.LOG_DIR, exist_ok=True)
    rows = [{"timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "symbol": s, **r}
            for s, r in results.items()]
    if rows:
        path = os.path.join(cfg.LOG_DIR, "optimizer_results.csv")
        pd.DataFrame(rows).to_csv(path, mode="a", header=not os.path.exists(path), index=False)


def should_reoptimize():
    if not cfg.OPTIMIZER_ENABLED: return False
    if _last_run == 0.0: return True
    return (time.time() - _last_run) / 3600 >= cfg.OPTIMIZER_INTERVAL_H


def apply_best_params(symbol):
    p = get_best_params()
    return p.get(symbol, {
        "MA_PERIOD": cfg.MA_PERIOD, "STDDEV_PERIOD": cfg.STDDEV_PERIOD,
        "Z_ENTER": cfg.Z_ENTER, "Z_EXIT": cfg.Z_EXIT, "Z_STOP": cfg.Z_STOP,
    })


def start_optimizer_thread(symbols):
    def _loop():
        while True:
            if should_reoptimize():
                try: run_optimization(symbols)
                except Exception as e: log.error(f"OPTIMIZER erro: {e}", "OPT")
            time.sleep(3600)
    threading.Thread(target=_loop, daemon=True, name="optimizer").start()
    log.info("OPTIMIZER: thread walk-forward iniciada", "OPT")
