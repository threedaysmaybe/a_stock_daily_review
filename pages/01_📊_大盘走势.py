"""
页面1：大盘走势 — 三大指数K线 + 量价分析 + 趋势指标
"""

import streamlit as st
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config as cfg
from utils.formatters import fmt_dataframe
import data_fetcher as df_
import analyzer as anl
import visualizer as viz
import pandas as pd
import streamlit.components.v1 as components

st.set_page_config(page_title="大盘走势", page_icon="📊", layout="wide")

st.title("📊 大盘走势分析")
st.caption(f"交易日：{(st.session_state.get('_trading_day') or pd.Timestamp.now()).strftime('%Y-%m-%d')}")

# ============================================================
# 从 session_state 读取指数行情（首页已加载）
# ============================================================
indices_data = st.session_state.get("_indices_data")
if indices_data is None:
    # 如果首页没加载过，自己加载
    with st.spinner("正在获取指数行情..."):
        indices_data = df_.get_all_indices()
        st.session_state["_indices_data"] = indices_data

# 实时行情概览
cols = st.columns(4)
for i, (name, data) in enumerate(indices_data.items()):
    with cols[i]:
        price = data.get("price", 0)
        pct = data.get("change_pct", 0)
        color = "#DC143C" if pct >= 0 else "#228B22"
        arrow = "▲" if pct >= 0 else "▼"
        st.metric(
            label=name,
            value=f"{price:.2f}" if price else "—",
            delta=f"{arrow} {pct:+.2f}%" if pct else None,
            delta_color="inverse",
        )

st.divider()

# 指数选择
index_options = list(cfg.INDICES.keys())
selected_index = st.selectbox("选择指数", index_options, index=0)
index_code = cfg.INDICES[selected_index]

# 获取K线数据（K线数据量大，单独获取）
with st.spinner(f"正在加载{selected_index} K线数据..."):
    df = df_.get_index_kline(index_code)
    if not df.empty:
        df = anl.calc_all_indicators(df)

if df.empty:
    st.error("无法获取指数数据，请检查网络连接")
    st.stop()

# K线图 + 成交量（ECharts，支持缩放拖动）
st.subheader(f"📈 {selected_index} — K线图（近120日）")
kline_html = viz.plot_kline_echarts(df, title=f"{selected_index} · 日K线图", height=500)
components.html(kline_html, height=530)

# 技术指标（ECharts，支持缩放拖动）
st.subheader("🔍 技术指标详情")

indicator_tabs = st.tabs(["MACD", "KDJ", "RSI", "BOLL"])
indicator_types = ["MACD", "KDJ", "RSI", "BOLL"]

for tab, ind_type in zip(indicator_tabs, indicator_types):
    with tab:
        ind_html = viz.plot_indicator_echarts(df, ind_type, height=280)
        components.html(ind_html, height=310)

# 趋势分析
st.subheader("📋 趋势研判")
trend = anl.classify_trend(df)

cols = st.columns(3)
with cols[0]:
    st.info(f"**短期趋势**\n\n{trend.get('short_trend', '—')}\n\n{trend.get('short_signal', '')}")
with cols[1]:
    st.info(f"**中期趋势**\n\n{trend.get('mid_trend', '—')}\n\n{trend.get('mid_signal', '')}")
with cols[2]:
    st.info(f"**MACD信号**\n\n{trend.get('macd_signal', '—')}")

# 关键点位
sr = trend.get("sr_levels", {})
if sr:
    st.subheader("📍 关键支撑/压力位")
    col_s, col_r = st.columns(2)
    with col_s:
        st.write("**支撑位**")
        for s in sr.get("supports", []):
            st.write(f"🟢 {s['label']}: ¥{s['price']} ({s['type']})")
    with col_r:
        st.write("**压力位**")
        for r in sr.get("resistances", []):
            st.write(f"🔴 {r['label']}: ¥{r['price']} ({r['type']})")

# 量价分析
st.subheader("📊 量价关系")
if not df.empty and len(df) >= 5:
    # 5日量价变化
    recent5 = df.tail(5)
    vol_change = recent5["volume"].iloc[-1] / recent5["volume"].iloc[-2] - 1 if len(recent5) >= 2 else 0
    price_change = recent5["close"].iloc[-1] / recent5["close"].iloc[-2] - 1 if len(recent5) >= 2 else 0

    col_a, col_b, col_c = st.columns(3)
    with col_a:
        vol_avg5 = recent5["volume"].mean()
        vol_avg20 = df["volume"].tail(20).mean()
        vol_ratio = vol_avg5 / vol_avg20 if vol_avg20 > 0 else 1
        st.metric("5日均量/20日均量", f"{vol_ratio:.2f}",
                  delta="放量" if vol_ratio > 1.2 else "缩量" if vol_ratio < 0.8 else "正常")
    with col_b:
        st.metric("近5日涨跌", f"{recent5['close'].iloc[-1] / recent5['close'].iloc[0] - 1:+.2%}")
    with col_c:
        avg_amplitude = recent5.apply(lambda x: (x["high"] - x["low"]) / x["close"] * 100, axis=1).mean()
        st.metric("5日平均振幅", f"{avg_amplitude:.2f}%")