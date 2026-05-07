from data_io import load_presets
from compare import compare_sessions
from ui_helpers import kpi, render_distribution
import pandas as pd


def test_imports():
    from data_io import load_yaml, load_history, load_runs, load_curves
    from compare import filter_sessions, rank_sessions, prepare_curves, prepare_trend
    from ui_helpers import inject_dark_css, render_header, render_top_cards
    assert all(callable(f) for f in [
        load_yaml, load_history, load_runs, load_curves,
        filter_sessions, rank_sessions, prepare_curves, prepare_trend,
        inject_dark_css, render_header, render_top_cards,
    ])


def test_kpi_html():
    html = kpi("Saldo", "€1,000")
    assert "Saldo" in html
    assert "€1,000" in html
    assert "card" in html


def test_render_distribution_modes():
    dummy = pd.DataFrame({"version": ["a", "a", "b", "b"], "score": [1, 2, 3, 4]})
    for mode in ["box", "violin", "histogram"]:
        fig = render_distribution(dummy, "version", mode)
        assert fig is not None


def test_compare_sessions_integration():
    summary, curves = compare_sessions(
        runs_csv="input/runs.csv",
        curves_csv="input/equity_curves.csv",
        config_path="input/config.yaml",
    )
    assert not summary.empty
    assert not curves.empty
    assert curves["run_id"].isin(summary["run_id"]).all()
    assert summary["rank"].is_monotonic_increasing


def test_presets_load():
    presets = load_presets("input/presets.yaml")
    assert isinstance(presets, dict)
    assert set(presets.keys()) == {"conservador", "agressivo", "eurusd_only"}
