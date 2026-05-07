import pandas as pd
from compare import (
    filter_sessions, rank_sessions, prepare_curves,
    compare_sessions, build_comparison_figures,
    save_historical_rankings, prepare_trend,
)


def _dummy_runs():
    return pd.DataFrame({
        "run_id": ["a", "b", "c"],
        "strategy": ["A", "A", "B"],
        "version": ["v1", "v2", "v1"],
        "symbol": ["EURUSD", "EURUSD", "GBPUSD"],
        "sharpe": [2.0, 1.5, 0.5],
        "win_rate": [0.6, 0.5, 0.4],
        "equity_final": [10000, 8000, 5000],
        "max_dd": [0.05, 0.10, 0.20],
    })


def _dummy_curves():
    return pd.DataFrame({
        "run_id": ["a", "a", "b", "b"],
        "ts": ["2026-01-01", "2026-01-02", "2026-01-01", "2026-01-02"],
        "equity": [1000, 1100, 1000, 900],
    })


def test_filter_sessions_no_filter():
    df = _dummy_runs()
    result = filter_sessions(df, {})
    assert len(result) == len(df)
    assert list(result.columns) == list(df.columns)


def test_filter_sessions_with_filter():
    df = _dummy_runs()
    config = {"filters": {"strategies": ["A"]}}
    result = filter_sessions(df, config)
    assert len(result) == 2
    assert (result["strategy"] == "A").all()


def test_rank_sessions():
    df = _dummy_runs()
    config = {"ranking_weights": {"sharpe": 0.5, "win_rate": 0.2, "equity_final": 0.2, "max_dd": 0.1}}
    result = rank_sessions(df, config)
    assert "score" in result.columns
    assert "rank" in result.columns
    assert result["rank"].is_monotonic_increasing


def test_prepare_curves_normalized():
    curves = _dummy_curves()
    config = {"display": {"normalize_equity": True}}
    result = prepare_curves(curves, config)
    assert "equity_plot" in result.columns
    assert "drawdown" in result.columns
    # first equity_plot of each run should be 1.0
    first = result.groupby("run_id")["equity_plot"].first()
    assert (first == 1.0).all()


def test_compare_sessions():
    summary, curves = compare_sessions(
        runs_csv="input/runs.csv",
        curves_csv="input/equity_curves.csv",
        config_path="input/config.yaml",
    )
    assert not summary.empty
    assert not curves.empty
    assert "score" in summary.columns
    assert "rank" in summary.columns
    assert curves["run_id"].isin(summary["run_id"]).all()


def test_build_comparison_figures():
    summary, curves = compare_sessions(
        runs_csv="input/runs.csv",
        curves_csv="input/equity_curves.csv",
        config_path="input/config.yaml",
    )
    eq, dd = build_comparison_figures(summary, curves)
    assert eq is not None and dd is not None


def test_save_historical_rankings(tmp_path):
    summary = pd.DataFrame({
        "run_id": ["test_run"], "strategy": ["T"], "version": ["v1"],
        "rank": [1], "score": [10.0], "equity_final": [1000],
        "max_dd": [0.05], "sharpe": [2.0], "win_rate": [0.6],
    })
    p = tmp_path / "test_hist.csv"
    save_historical_rankings(summary, str(p))
    assert p.exists()
    loaded = pd.read_csv(p)
    assert len(loaded) == 1


def test_prepare_trend():
    hist = pd.DataFrame({
        "ts_run": pd.to_datetime(["2026-01-01", "2026-01-01", "2026-01-02"]),
        "version": ["v1", "v2", "v1"],
        "score": [10, 8, 12],
        "rank": [1, 2, 1],
        "sharpe": [2.0, 1.5, 2.5],
        "max_dd": [0.05, 0.10, 0.03],
    })
    trend = prepare_trend(hist, "version")
    assert not trend.empty
    assert "date" in trend.columns
    assert "score_mean" in trend.columns
    assert "rank_best" in trend.columns
