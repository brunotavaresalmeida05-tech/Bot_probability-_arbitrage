from __future__ import annotations

import pandas as pd
import streamlit as st
import plotly.express as px

from data_io import load_presets, load_history, load_live_kpi
from compare import compare_sessions, save_historical_rankings, build_comparison_figures, prepare_trend
from ui_helpers import inject_dark_css, render_header, kpi, render_top_cards, dark_fig, render_distribution

st.set_page_config(
    page_title="Trading Bot Dashboard",
    layout="wide",
    initial_sidebar_state="expanded",
)

PRESETS_PATH = "input/presets.yaml"
HISTORY_PATH = "output/historical_rankings.csv"
RUNS_CSV = "input/runs.csv"
CURVES_CSV = "input/equity_curves.csv"
CONFIG_PATH = "input/config.yaml"

DEFAULTS = {
    "selected_metric": "score_mean",
    "selected_group": "version",
    "dist_type": "box",
    "sort_ascending": False,
    "top_n": 5,
    "only_top2": False,
    "selected_groups": [],
    "date_range": None,
    "preset_name": "custom",
    "_applied_preset": "custom",
}

metric_options = {
    "score_mean": "Score médio",
    "rank_best": "Melhor rank",
    "sharpe_mean": "Sharpe médio",
    "max_dd_mean": "Max DD médio",
}

group_options = {
    "version": "Version",
    "strategy": "Strategy",
    "symbol": "Symbol",
}

dist_options = {
    "box": "Box",
    "violin": "Violin",
    "histogram": "Histogram",
}


def init_state():
    for k, v in DEFAULTS.items():
        st.session_state.setdefault(k, v)


def apply_preset(name: str, presets: dict):
    preset = presets.get(name)
    if not preset:
        return
    for k, v in preset.items():
        if k in DEFAULTS:
            st.session_state[k] = v
    st.session_state["preset_name"] = name
    st.rerun()


def reset_filters():
    for k, v in DEFAULTS.items():
        st.session_state[k] = v
    st.rerun()


def main():
    inject_dark_css()
    init_state()
    presets = load_presets(PRESETS_PATH)

    # ─── Load data ───

    try:
        summary, curves = compare_sessions(RUNS_CSV, CURVES_CSV, CONFIG_PATH)
    except Exception as e:
        st.error(f"Erro ao carregar sessões: {e}")
        st.stop()

    if not summary.empty:
        save_historical_rankings(summary, HISTORY_PATH)

    history = load_history(HISTORY_PATH)
    live_kpi = load_live_kpi(summary)

    # ─── Header ───

    render_header()

    # ─── KPIs ───

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.markdown(kpi("Saldo", live_kpi["balance"]), unsafe_allow_html=True)
    c2.markdown(kpi("Equity", live_kpi["equity"]), unsafe_allow_html=True)
    c3.markdown(kpi("P&L Aberto", live_kpi["profit"]), unsafe_allow_html=True)
    c4.markdown(kpi("Posições", live_kpi["positions"]), unsafe_allow_html=True)
    c5.markdown(kpi("Regime", "Normal"), unsafe_allow_html=True)
    c6.markdown(kpi("Health", live_kpi["health"]), unsafe_allow_html=True)

    # ─── Sidebar + trend data ───

    hist = pd.DataFrame()
    with st.sidebar:
        st.markdown("## Controls")
        preset_names = ["custom"] + sorted(presets.keys())
        selected_preset = st.selectbox("Preset de filtros", options=preset_names, key="preset_name")

        if selected_preset != "custom" and st.session_state.get("_applied_preset") != selected_preset:
            st.session_state["_applied_preset"] = selected_preset
            apply_preset(selected_preset, presets)

        st.button("Reset filters", on_click=reset_filters)
        st.divider()

        st.selectbox("Métrica do trend", options=list(metric_options.keys()), format_func=lambda x: metric_options[x], key="selected_metric")
        st.selectbox("Agrupamento do trend", options=list(group_options.keys()), format_func=lambda x: group_options[x], key="selected_group")

        if not history.empty:
            min_date = history["ts_run"].dt.date.min()
            max_date = history["ts_run"].dt.date.max()

            if st.session_state["date_range"] is None:
                st.session_state["date_range"] = (min_date, max_date)

            st.date_input("Intervalo de datas", min_value=min_date, max_value=max_date, key="date_range")

            dr = st.session_state["date_range"]
            if isinstance(dr, tuple) and len(dr) == 2:
                start_date, end_date = dr
            else:
                start_date = end_date = dr

            hist = history[
                (history["ts_run"].dt.date >= start_date) &
                (history["ts_run"].dt.date <= end_date)
            ].copy()

            sg = st.session_state["selected_group"]
            available_groups = sorted(hist[sg].dropna().astype(str).unique().tolist())

            if not st.session_state["selected_groups"]:
                st.session_state["selected_groups"] = available_groups[:min(5, len(available_groups))]

            st.multiselect(f"Grupos ({sg})", options=available_groups, key="selected_groups")

            if st.session_state["selected_groups"]:
                hist = hist[hist[sg].astype(str).isin(st.session_state["selected_groups"])]

        st.selectbox("Distribuição", options=list(dist_options.keys()), format_func=lambda x: dist_options[x], key="dist_type")
        st.checkbox("Ordenar ascendente", key="sort_ascending")
        st.slider("Top N grupos", min_value=1, max_value=20, key="top_n")
        st.checkbox("Mostrar apenas grupos com top2_count > 0", key="only_top2")

    # ─── Trend computation ───

    if not hist.empty:
        selected_group = st.session_state["selected_group"]
        trend = prepare_trend(hist, selected_group)

        if st.session_state["only_top2"]:
            good = trend.groupby(selected_group)["top2_count"].max()
            good = good[good > 0].index.astype(str).tolist()
            trend = trend[trend[selected_group].astype(str).isin(good)]
            hist = hist[hist[selected_group].astype(str).isin(good)]

        score_rank = (
            hist.groupby(selected_group, as_index=False)
            .agg(
                score_mean=("score", "mean"),
                rank_best=("rank", "min"),
                sharpe_mean=("sharpe", "mean"),
                max_dd_mean=("max_dd", "mean"),
                top2_count=("rank", lambda s: (s <= 2).sum()),
            )
        )
        score_rank = score_rank.sort_values(
            st.session_state["selected_metric"],
            ascending=st.session_state["sort_ascending"],
        ).head(st.session_state["top_n"])

    # ─── Top 2 ───

    st.markdown("### 🏆 Top 2 Atual")
    render_top_cards(summary)

    # ─── Equity & Drawdown ───

    if not curves.empty:
        eq_fig, dd_fig = build_comparison_figures(summary, curves)
        eq_fig = dark_fig(eq_fig)
        dd_fig = dark_fig(dd_fig)

        col1, col2 = st.columns(2)
        with col1:
            st.markdown('<div class="card">', unsafe_allow_html=True)
            st.markdown('<div class="small-title">📈 Equity</div>', unsafe_allow_html=True)
            st.plotly_chart(eq_fig, use_container_width=True, config={"displayModeBar": False})
            st.markdown("</div>", unsafe_allow_html=True)
        with col2:
            st.markdown('<div class="card">', unsafe_allow_html=True)
            st.markdown('<div class="small-title">📉 Drawdown</div>', unsafe_allow_html=True)
            st.plotly_chart(dd_fig, use_container_width=True, config={"displayModeBar": False})
            st.markdown("</div>", unsafe_allow_html=True)

    # ─── Trend & Distribution ───

    if not history.empty and not hist.empty:
        sm = st.session_state["selected_metric"]
        sg = st.session_state["selected_group"]

        trend_fig = px.line(
            trend,
            x="date",
            y=sm,
            color=sg,
            markers=True,
            title=f"Trend de {metric_options[sm]} por {group_options[sg]}",
        )
        trend_fig = dark_fig(trend_fig)
        if sm == "rank_best":
            trend_fig.update_yaxes(autorange="reversed")

        col1, col2 = st.columns([3, 2])
        with col1:
            st.markdown('<div class="card">', unsafe_allow_html=True)
            st.plotly_chart(trend_fig, use_container_width=True, config={"displayModeBar": False})
            st.markdown("</div>", unsafe_allow_html=True)
        with col2:
            st.markdown('<div class="card">', unsafe_allow_html=True)
            st.markdown(f'<div class="small-title">📊 Score por {group_options[sg]}</div>', unsafe_allow_html=True)
            d = render_distribution(hist, sg, st.session_state["dist_type"])
            d = dark_fig(d)
            st.plotly_chart(d, use_container_width=True, config={"displayModeBar": False})
            st.markdown("</div>", unsafe_allow_html=True)

        # ─── Top N + CSV ───

        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown(f'<div class="small-title">🏅 Top {st.session_state["top_n"]} grupos</div>', unsafe_allow_html=True)
        st.dataframe(score_rank, use_container_width=True, hide_index=True)
        csv_bytes = hist.to_csv(index=False).encode("utf-8")
        st.download_button("⬇ Download filtered CSV", data=csv_bytes, file_name="filtered_history.csv", mime="text/csv")
        st.markdown("</div>", unsafe_allow_html=True)

        # ─── History table ───

        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown('<div class="small-title">📋 Histórico filtrado</div>', unsafe_allow_html=True)
        hist_cols = [c for c in [
            "ts_run", "run_id", "strategy", "version", "symbol",
            "rank", "score", "equity_final", "max_dd", "sharpe", "win_rate"
        ] if c in hist.columns]
        st.dataframe(hist.sort_values(["ts_run", "rank"])[hist_cols], use_container_width=True, hide_index=True)
        st.markdown("</div>", unsafe_allow_html=True)

    elif not history.empty and hist.empty:
        st.info("Nenhum dado no intervalo selecionado. Ajusta o filtro de datas.")
    else:
        st.info("Ainda não há histórico de rankings. Execute o comparador para gerar dados.")


if __name__ == "__main__":
    main()
