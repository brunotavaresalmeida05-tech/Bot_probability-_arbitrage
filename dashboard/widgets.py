import streamlit as st
import pandas as pd
from datetime import datetime, timezone


def show_health_status(state):
    """Display bot health status widget."""
    if not state:
        st.error("No health data available")
        return
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        status = state.get("status", "unknown")
        if status == "healthy" or state.get("ok", False):
            st.success(f"✅ Bot Status: {status.upper()}")
        else:
            st.error(f"❌ Bot Status: {status.upper()}")
    
    with col2:
        last_loop = state.get("last_loop_age_sec", 999)
        if last_loop < 120:
            st.info(f"⏱️ Last Loop: {last_loop:.0f}s ago")
        else:
            st.warning(f"⚠️ Last Loop: {last_loop:.0f}s ago (stale)")
    
    with col3:
        running = state.get("running", False)
        if running:
            st.success("🟢 Running")
        else:
            st.error("🔴 Stopped")


def show_metrics_cards(metrics):
    """Display key metrics as cards."""
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            label="Total Trades",
            value=metrics.get("total_trades", 0)
        )
    
    with col2:
        ret = metrics.get("total_return_pct", 0)
        st.metric(
            label="Total Return",
            value=f"{ret:.2f}%",
            delta=f"{ret:.2f}%" if ret != 0 else None
        )
    
    with col3:
        sharpe = metrics.get("sharpe_ratio", 0)
        st.metric(
            label="Sharpe Ratio",
            value=f"{sharpe:.2f}"
        )
    
    with col4:
        dd = metrics.get("max_drawdown_pct", 0)
        st.metric(
            label="Max Drawdown",
            value=f"{dd:.2f}%",
            delta=f"{dd:.2f}%" if dd < 0 else None,
            delta_color="inverse"
        )


def show_recent_trades(equity_df, limit=10):
    """Display recent trades table."""
    if equity_df.empty:
        st.info("No trades yet")
        return
    
    st.subheader(f"Recent Trades (Last {limit})")
    
    recent = equity_df.tail(limit).copy()
    recent["ts"] = pd.to_datetime(recent["ts"]).dt.strftime("%Y-%m-%d %H:%M")
    recent["pnl"] = recent["pnl"].astype(float)
    
    # Select columns to display
    display_cols = ["ts", "symbol", "side", "entry_price", "exit_price", "pnl", "equity"]
    display = recent[display_cols].copy()
    display.columns = ["Time", "Symbol", "Side", "Entry", "Exit", "PnL", "Equity"]
    
    st.dataframe(
        display.style.applymap(
            lambda x: "color: green" if isinstance(x, (int, float)) and x > 0 else ("color: red" if isinstance(x, (int, float)) and x < 0 else ""),
            subset=["PnL"]
        ),
        use_container_width=True,
        hide_index=True
    )


def show_alert_log():
    """Placeholder for alert feed - reads from logs or state."""
    st.subheader("Alert Feed")
    
    # This would read from a log file or state in production
    # For now, show static example
    alerts = [
        {"time": "2026-05-06 17:18", "type": "info", "message": "Bot started successfully"},
        {"time": "2026-05-06 17:19", "type": "success", "message": "Trade #5 closed: +$9.55"},
    ]
    
    for alert in alerts:
        if alert["type"] == "info":
            st.info(f"{alert['time']} - {alert['message']}")
        elif alert["type"] == "success":
            st.success(f"{alert['time']} - {alert['message']}")
        elif alert["type"] == "warning":
            st.warning(f"{alert['time']} - {alert['message']}")
        elif alert["type"] == "error":
            st.error(f"{alert['time']} - {alert['message']}")


def show_error_count():
    """Display consecutive error count."""
    from core.monitoring import _consecutive_errors
    count = _consecutive_errors
    
    if count == 0:
        st.success(f"✅ No consecutive errors")
    elif count < 3:
        st.warning(f"⚠️ Consecutive errors: {count}")
    else:
        st.error(f"❌ Consecutive errors: {count} (threshold reached!)")
