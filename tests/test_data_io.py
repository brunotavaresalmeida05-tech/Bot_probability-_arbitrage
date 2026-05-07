from pathlib import Path
import pandas as pd
from data_io import load_yaml, load_presets, load_history, load_runs, load_curves


def test_load_yaml_missing():
    assert load_yaml("nonexistent.yaml", {}) == {}


def test_load_yaml_present():
    p = load_yaml("input/presets.yaml", {})
    assert isinstance(p, dict)
    assert "conservador" in p


def test_load_presets():
    p = load_presets("input/presets.yaml")
    assert isinstance(p, dict) and len(p) == 3


def test_load_presets_missing():
    assert load_presets("nonexistent.yaml") == {}


def test_load_history_missing():
    df = load_history("nonexistent.csv")
    assert isinstance(df, pd.DataFrame) and df.empty


def test_load_history_present():
    df = load_history("output/historical_rankings.csv")
    assert isinstance(df, pd.DataFrame)
    if not df.empty:
        assert "ts_run" in df.columns
        assert "score" in df.columns


def test_load_runs():
    df = load_runs("input/runs.csv")
    assert isinstance(df, pd.DataFrame) and not df.empty
    assert "run_id" in df.columns
    assert "strategy" in df.columns


def test_load_curves():
    df = load_curves("input/equity_curves.csv")
    assert isinstance(df, pd.DataFrame) and not df.empty
    assert "run_id" in df.columns
    assert "equity" in df.columns
