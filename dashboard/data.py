import os
import pandas as pd
from config.settings import EQUITY_PATH, FILLS_PATH, EQUITY_COLUMNS, FILL_COLUMNS
from core.metrics import calculate_metrics, calculate_rolling_metrics


def load_equity():
    """Load equity CSV or return empty DataFrame."""
    if os.path.exists(EQUITY_PATH):
        df = pd.read_csv(EQUITY_PATH)
        df["ts"] = pd.to_datetime(df["ts"], utc=True)
        return df
    return pd.DataFrame(columns=EQUITY_COLUMNS)


def load_fills():
    """Load fills CSV or return empty DataFrame."""
    if os.path.exists(FILLS_PATH):
        df = pd.read_csv(FILLS_PATH)
        df["ts"] = pd.to_datetime(df["ts"], utc=True)
        return df
    return pd.DataFrame(columns=FILL_COLUMNS)


def get_metrics(equity_df):
    """Calculate and return metrics dict."""
    if equity_df.empty:
        return {
            "total_trades": 0,
            "total_return_pct": 0.0,
            "sharpe_ratio": 0.0,
            "max_drawdown_pct": 0.0,
            "win_rate": 0.0,
            "avg_trade": 0.0,
            "profit_factor": 0.0,
        }
    
    return calculate_metrics(equity_df)


def get_rolling_metrics(equity_df, window=20):
    """Get rolling metrics for dashboard charts."""
    if equity_df.empty or len(equity_df) < 2:
        return pd.DataFrame()
    
    return calculate_rolling_metrics(equity_df, window)


def get_latest_state():
    """Get latest bot state from health endpoint."""
    try:
        import requests
        r = requests.get("http://localhost:8080/health", timeout=2)
        if r.status_code == 200:
            return r.json()
    except:
        pass
    
    # Fallback: read from CSV
    equity_df = load_equity()
    if equity_df.empty:
        return {"status": "no_data", "running": False}
    
    return {
        "status": "unknown",
        "running": True,
        "equity": float(equity_df.iloc[-1]["equity"]),
        "trades": len(equity_df),
    }
