import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


def plot_equity_curve(equity_df):
    """Equity curve with drawdown overlay."""
    if equity_df.empty:
        return go.Figure().update_layout(title="No equity data")
    
    equity_df = equity_df.copy()
    equity_df["ts"] = pd.to_datetime(equity_df["ts"], utc=True)
    equity_df = equity_df.sort_values("ts")
    
    # Calculate drawdown
    peak = equity_df["equity"].cummax()
    drawdown = (equity_df["equity"] - peak) / peak * 100
    
    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.1,
        subplot_titles=("Equity Curve", "Drawdown %"),
        row_heights=[0.7, 0.3]
    )
    
    # Equity line
    fig.add_trace(
        go.Scatter(
            x=equity_df["ts"],
            y=equity_df["equity"],
            mode="lines+markers",
            name="Equity",
            line=dict(color="blue", width=2),
            marker=dict(size=6),
        ),
        row=1, col=1
    )
    
    # Drawdown area
    fig.add_trace(
        go.Scatter(
            x=equity_df["ts"],
            y=drawdown,
            mode="lines",
            name="Drawdown %",
            line=dict(color="red", width=1),
            fill="tozeroy",
            fillcolor="rgba(255, 0, 0, 0.1)",
        ),
        row=2, col=1
    )
    
    fig.update_layout(
        height=600,
        title="Equity Curve & Drawdown",
        showlegend=True,
        hovermode="x unified",
    )
    
    fig.update_yaxes(title_text="Equity ($)", row=1, col=1)
    fig.update_yaxes(title_text="Drawdown (%)", row=2, col=1)
    
    return fig


def plot_pnl_distribution(equity_df):
    """Bar chart of PnL per trade."""
    if equity_df.empty:
        return go.Figure().update_layout(title="No trade data")
    
    equity_df = equity_df.copy()
    equity_df["pnl"] = equity_df["pnl"].astype(float)
    
    colors = ["green" if p >= 0 else "red" for p in equity_df["pnl"]]
    
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=equity_df.index + 1,
        y=equity_df["pnl"],
        marker_color=colors,
        name="PnL",
    ))
    
    fig.update_layout(
        title="PnL per Trade",
        xaxis_title="Trade #",
        yaxis_title="PnL ($)",
        height=400,
    )
    
    fig.add_hline(y=0, line_dash="dash", line_color="black", line_width=1)
    
    return fig


def plot_rolling_sharpe(rolling_df):
    """Plot rolling Sharpe ratio."""
    if rolling_df.empty or "sharpe_ratio" not in rolling_df.columns:
        return go.Figure().update_layout(title="No rolling data")
    
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=rolling_df["ts"],
        y=rolling_df["sharpe_ratio"],
        mode="lines",
        name="Rolling Sharpe",
        line=dict(color="purple", width=2),
    ))
    
    fig.update_layout(
        title="Rolling Sharpe Ratio (20 trades)",
        xaxis_title="Time",
        yaxis_title="Sharpe Ratio",
        height=300,
    )
    
    fig.add_hline(y=1, line_dash="dash", line_color="green", annotation_text="Sharpe = 1")
    
    return fig
