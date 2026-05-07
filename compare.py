from __future__ import annotations

from pathlib import Path
import pandas as pd
import plotly.express as px

from data_io import load_yaml, load_runs, load_curves


def filter_sessions(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    out = df.copy()
    filt = config.get("filters", {})

    for col, key in [("strategy", "strategies"), ("symbol", "symbols"), ("timeframe", "timeframes"), ("version", "versions")]:
        vals = filt.get(key, [])
        if vals:
            out = out[out[col].isin(vals)]

    if "min_trades" in filt and "total_trades" in out.columns:
        out = out[out["total_trades"] >= filt["min_trades"]]

    if "min_days" in filt and {"start_ts", "end_ts"}.issubset(out.columns):
        days = (out["end_ts"] - out["start_ts"]).dt.total_seconds() / 86400
        out = out[days >= filt["min_days"]]

    return out.reset_index(drop=True)


def rank_sessions(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    weights = config.get("ranking_weights", {})
    out = df.copy()

    for col in ["sharpe", "win_rate", "equity_final", "max_dd"]:
        if col not in out.columns:
            out[col] = 0.0

    sharpe_s = out["sharpe"].fillna(0)
    win_rate_s = out["win_rate"].fillna(0)
    equity_rank = out["equity_final"].rank(pct=True, method="average").fillna(0)
    dd_rank = out["max_dd"].abs().rank(pct=True, method="average").fillna(0)

    out["score"] = (
        sharpe_s * weights.get("sharpe", 0.5)
        + win_rate_s * weights.get("win_rate", 0.2)
        + equity_rank * weights.get("equity_final", 0.2)
        + (1 - dd_rank) * weights.get("max_dd", 0.1)
    )

    out["rank"] = out["score"].rank(ascending=False, method="dense")
    return out.sort_values(["rank", "score"], ascending=[True, False]).reset_index(drop=True)


def prepare_curves(curves: pd.DataFrame, config: dict) -> pd.DataFrame:
    out = curves.copy()
    display = config.get("display", {})
    normalize = display.get("normalize_equity", True)

    if "run_id" not in out.columns or "equity" not in out.columns:
        return out

    if normalize:
        out["equity_plot"] = out.groupby("run_id")["equity"].transform(
            lambda s: s / s.iloc[0] if s.iloc[0] != 0 else s
        )
    else:
        out["equity_plot"] = out["equity"]

    out["drawdown"] = out.groupby("run_id")["equity"].transform(lambda s: s / s.cummax() - 1)
    return out


def compare_sessions(
    runs_csv: str = "data/session_runs.csv",
    curves_csv: str = "data/session_curves.csv",
    config_path: str = "config/ranking.yaml",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    config = load_yaml(config_path, {})
    runs = load_runs(runs_csv)
    curves = load_curves(curves_csv)

    filtered = filter_sessions(runs, config)
    ranked = rank_sessions(filtered, config)

    top_n = config.get("display", {}).get("top_n", 2)
    summary = ranked.head(top_n).copy()

    top_ids = summary["run_id"].astype(str).tolist() if "run_id" in summary.columns else []
    curves["run_id"] = curves["run_id"].astype(str)
    curves = curves[curves["run_id"].isin(top_ids)].copy()
    curves = prepare_curves(curves, config)

    return summary, curves


def build_comparison_figures(summary: pd.DataFrame, curves: pd.DataFrame) -> tuple:
    eq_fig = px.line(curves, x="ts", y="equity_plot", color="run_id", title="Equity Comparison")
    dd_fig = px.line(curves, x="ts", y="drawdown", color="run_id", title="Drawdown Comparison")
    return eq_fig, dd_fig


def save_historical_rankings(summary: pd.DataFrame, path: str = "data/historical_rankings.csv") -> None:
    if summary.empty:
        return
    out = summary.copy()
    out["ts_run"] = pd.Timestamp.utcnow()

    cols = [
        "ts_run", "run_id", "strategy", "version", "rank", "score",
        "equity_final", "max_dd", "sharpe", "win_rate"
    ]
    for col in cols:
        if col not in out.columns:
            out[col] = pd.NA

    out = out[cols]
    p = Path(path)
    if p.exists():
        existing = pd.read_csv(path)
        if list(existing.columns) != list(out.columns):
            raise ValueError("Column mismatch in historical_rankings.csv")
        out.to_csv(path, mode="a", index=False, header=False)
    else:
        out.to_csv(path, index=False)


def prepare_trend(df: pd.DataFrame, group_col: str = "version") -> pd.DataFrame:
    out = df.copy()
    if "ts_run" not in out.columns:
        return pd.DataFrame()
    out["date"] = out["ts_run"].dt.date

    agg = out.groupby(["date", group_col], as_index=False).agg(
        score_mean=("score", "mean"),
        rank_best=("rank", "min"),
        sharpe_mean=("sharpe", "mean"),
        max_dd_mean=("max_dd", "mean"),
        top2_count=("rank", lambda s: (s <= 2).sum())
    )
    return agg
