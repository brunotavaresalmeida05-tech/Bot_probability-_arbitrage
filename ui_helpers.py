from __future__ import annotations

import streamlit as st
import plotly.express as px


def inject_dark_css():
    st.markdown("""
    <style>
    :root {
        --bg: #0f172a;
        --panel: #111827;
        --panel2: #0b1220;
        --border: #1f2937;
        --text: #e5e7eb;
        --muted: #94a3b8;
        --accent: #38bdf8;
        --accent2: #00d4aa;
        --danger: #fb7185;
    }
    .main { background: linear-gradient(180deg, #0b1020 0%, #0f172a 100%); color: var(--text); }
    section[data-testid="stSidebar"] { background: linear-gradient(180deg, #0b1220 0%, #111827 100%); }
    [data-testid="stSidebar"] * { color: var(--text); }
    .block-container { padding-top: 1rem; }
    div[data-testid="stMetric"] {
        background: rgba(17,24,39,.85);
        border: 1px solid var(--border);
        border-radius: 14px;
        padding: 12px 14px;
    }
    div[data-testid="stMetric"] label { color: var(--muted); }
    div[data-testid="stMetric"] [data-testid="stMetricValue"] { color: var(--text); }
    .card {
        background: rgba(17,24,39,.92);
        border: 1px solid var(--border);
        border-radius: 16px;
        padding: 14px;
        box-shadow: 0 10px 30px rgba(0,0,0,.18);
        margin-bottom: 16px;
    }
    .small-title { font-size: 12px; color: var(--muted); text-transform: uppercase; letter-spacing: .08em; }
    .big-title { font-size: 22px; font-weight: 800; color: var(--text); }
    .stPlotlyChart { border-radius: 12px; overflow: hidden; }
    hr { border-color: var(--border); }
    .stButton > button {
        background: rgba(56,189,248,.1);
        border: 1px solid rgba(56,189,248,.25);
        color: var(--accent); border-radius: 10px; font-weight: 600; width: 100%;
    }
    .stButton > button:hover { background: rgba(56,189,248,.2); border-color: var(--accent); }
    </style>
    """, unsafe_allow_html=True)


def render_header():
    st.markdown("""
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px;">
      <div>
        <div style="font-size:28px;font-weight:800;color:#e5e7eb;">Trading Bot Dashboard</div>
        <div style="font-size:13px;color:#94a3b8;">Real-time strategy comparison and observability</div>
      </div>
      <div style="display:flex;gap:8px;">
        <div style="padding:6px 10px;border-radius:999px;background:#0b1220;border:1px solid #1f2937;color:#38bdf8;font-weight:700;">BOT LIVE</div>
        <div style="padding:6px 10px;border-radius:999px;background:#0b1220;border:1px solid #1f2937;color:#00d4aa;font-weight:700;">NORMAL</div>
      </div>
    </div>
    """, unsafe_allow_html=True)


def kpi(label: str, value: str) -> str:
    return f"""
    <div class="card">
        <div class="small-title">{label}</div>
        <div style="font-size:22px;font-weight:800;color:#f8fafc;margin-top:4px;">{value}</div>
    </div>
    """


def render_top_cards(summary):
    if summary.empty:
        st.info("Sem dados para apresentar.")
        return
    top2 = summary.head(2)
    cols = st.columns(2)
    for i, (_, row) in enumerate(top2.iterrows()):
        with cols[i]:
            st.markdown(f"""
            <div class="card">
                <div class="small-title">Top {i+1}</div>
                <div class="big-title">{row.get("strategy", "")} · {row.get("version", "")}</div>
                <div style="margin-top:8px;color:#cbd5e1;">
                    <div><b>Run:</b> {row.get("run_id", "")}</div>
                    <div><b>Rank:</b> {row.get("rank", "")}</div>
                    <div><b>Score:</b> {row.get("score", 0):.4f}</div>
                    <div><b>Equity:</b> {row.get("equity_final", 0):.4f}</div>
                    <div><b>Max DD:</b> {row.get("max_dd", 0):.4f}</div>
                    <div><b>Sharpe:</b> {row.get("sharpe", 0):.4f}</div>
                    <div><b>Win rate:</b> {row.get("win_rate", 0):.2%}</div>
                </div>
            </div>
            """, unsafe_allow_html=True)


def dark_fig(fig):
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(color="#94a3b8")),
        title_font_color="#e5e7eb",
        font_color="#94a3b8",
    )
    fig.update_xaxes(gridcolor="#1f2937")
    fig.update_yaxes(gridcolor="#1f2937")
    return fig


def render_distribution(hist, selected_group, dist_type):
    if dist_type == "box":
        return px.box(hist, x=selected_group, y="score", points="all")
    elif dist_type == "violin":
        return px.violin(hist, x=selected_group, y="score", box=True, points="all")
    else:
        return px.histogram(hist, x="score", color=selected_group, barmode="overlay", opacity=0.65)
