"""
每日A股复盘模型 — Streamlit Web应用
主入口：仪表盘概览 + 页面路由

启动方式：
    cd a_stock_daily_review
    streamlit run app.py

手机访问：启动后在浏览器打开 http://你的IP:8501
"""

import streamlit as st
import pandas as pd
import numpy as np
import os
import json
import base64
from datetime import datetime

import config as cfg
import data_fetcher as df_
import analyzer as anl
import visualizer as viz
import data_manager as dm

# ============================================================
# 读取并编码图标（base64内联）
# ============================================================
def get_icon_base64():
    """读取 stock.ico 并转为 base64 编码"""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 优先使用 PNG（手机主屏幕兼容性更好）
    png_path = os.path.join(base_dir, "stock.png")
    ico_path = os.path.join(base_dir, "stock.ico")
    
    if os.path.exists(png_path):
        with open(png_path, "rb") as f:
            return base64.b64encode(f.read()).decode(), "image/png"
    elif os.path.exists(ico_path):
        with open(ico_path, "rb") as f:
            return base64.b64encode(f.read()).decode(), "image/x-icon"
    else:
        # 如果都没有，返回 None
        return None, None

icon_b64, icon_type = get_icon_base64()

# ============================================================
# Streamlit 页面配置
# ============================================================
st.set_page_config(
    page_title="每日A股复盘",
    page_icon="📊" if icon_b64 is None else f"data:{icon_type};base64,{icon_b64}",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ============================================================
# 主屏幕图标（PWA / 添加到主屏幕）
# ============================================================
if icon_b64:
    # 如果是 PNG，用 PNG 的 MIME 类型；如果是 ICO，也尝试作为 PNG 显示（部分浏览器支持）
    mime_type = "image/png" if icon_type == "image/png" else "image/x-icon"
    
    # 尝试用 stock.png（如果没有则用 stock.ico）
    base_dir = os.path.dirname(os.path.abspath(__file__))
    png_path = os.path.join(base_dir, "stock.png")
    
    if os.path.exists(png_path):
        with open(png_path, "rb") as f:
            icon_b64_png = base64.b64encode(f.read()).decode()
            icon_data_uri = f"data:image/png;base64,{icon_b64_png}"
    else:
        icon_data_uri = f"data:{mime_type};base64,{icon_b64}"
    
    st.markdown(f"""
    <!-- 主屏幕图标 (iOS/Android) -->
    <link rel="apple-touch-icon" sizes="180x180" href="{icon_data_uri}">
    <link rel="apple-touch-icon" sizes="152x152" href="{icon_data_uri}">
    <link rel="apple-touch-icon" sizes="120x120" href="{icon_data_uri}">
    <link rel="icon" type="image/png" sizes="192x192" href="{icon_data_uri}">
    <link rel="icon" type="image/png" sizes="32x32" href="{icon_data_uri}">
    <link rel="icon" type="image/png" sizes="16x16" href="{icon_data_uri}">
    
    <!-- PWA 配置 -->
    <meta name="apple-mobile-web-app-title" content="A股复盘">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    <meta name="theme-color" content="#0e1117">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    
    <style>
        /* 确保图标在加载时正确显示 */
        .stApp {{
            background-color: #0e1117;
        }}
    </style>
    """, unsafe_allow_html=True)
else:
    st.markdown("""
    <!-- 备用：如果图标文件不存在，使用 emoji -->
    <link rel="apple-touch-icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>📊</text></svg>">
    <meta name="apple-mobile-web-app-title" content="A股复盘">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="theme-color" content="#0e1117">
    """, unsafe_allow_html=True)

# ============================================================
# 加载持仓（本地优先）
# ============================================================
def load_portfolio() -> dict:
    _PORTFOLIO_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "portfolio.json")
    _portfolio = dict(cfg.PORTFOLIO)
    if os.path.exists(_PORTFOLIO_FILE):
        try:
            with open(_PORTFOLIO_FILE, "r", encoding="utf-8") as _f:
                _portfolio = json.load(_f)
        except Exception:
            pass
    return _portfolio


# ============================================================
# 侧边栏
# ============================================================
st.sidebar.title("📈 每日A股复盘")
st.sidebar.caption(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}")

# 导航
st.sidebar.markdown("---")
st.sidebar.markdown("### 📋 导航")

pages = {
    "🏠 首页仪表盘": "app",
    "📊 大盘走势": "01_📊_大盘走势",
    "🔥 板块分析": "02_🔥_板块分析",
    "💹 资金情绪": "03_💹_资金情绪",
    "🐉 龙头股": "04_🐉_龙头股",
    "💼 持仓分析": "05_💼_持仓分析",
    "🕵️ 游资追踪": "06_🕵️_游资追踪",
    "🔮 明日预测": "07_🔮_明日预测",
}

st.sidebar.markdown("使用左侧导航栏切换页面 ⬅️")
st.sidebar.markdown("---")

# ============================================================
# 数据状态 & 更新
# ============================================================
st.sidebar.markdown("### 📦 数据状态")

has_data = dm.has_data_today()
latest = dm.get_latest_date()

if has_data:
    st.sidebar.success("✅ 今日已更新")
else:
    delta = ""
    if latest:
        try:
            latest_dt = datetime.strptime(latest, "%Y%m%d")
            days_ago = (datetime.now() - latest_dt).days
            delta = f"（{days_ago}天前）"
        except Exception:
            pass
    st.sidebar.warning(f"⚠️ 数据过期 {delta}" if delta else "⚠️ 未下载数据")

st.sidebar.caption(f"上次更新：{latest if latest else '无'}")

if st.sidebar.button("🔄 更新数据 & 重新分析", use_container_width=True, type="primary"):
    with st.spinner("正在下载最新数据..."):
        progress_bar = st.progress(0)
        status_text = st.empty()

        def on_progress(i, total, name):
            pct = min((i + 1) / total, 1.0) if total > 0 else 1.0
            progress_bar.progress(pct)
            status_text.text(f"({i+1}/{total}) {name}")

        meta = dm.download_all(progress_callback=on_progress)
        progress_bar.empty()
        status_text.empty()
        if meta["ok"] > 0:
            # 清除所有缓存
            st.cache_data.clear()
            st.session_state._market_data_loaded = False
            st.rerun()
        else:
            st.error("下载失败，请检查网络（周末正常）")

with st.sidebar.expander("⚙️ 更多"):
    if st.button("🗑️ 仅清除缓存", use_container_width=True):
        st.cache_data.clear()
        st.session_state._market_data_loaded = False
        st.rerun()

st.sidebar.markdown("---")

# ============================================================
# 持仓股一览
# ============================================================
_portfolio = load_portfolio()

st.sidebar.markdown("### 💼 我的持仓")
for code, name in _portfolio.items():
    # 从 session_state 读取实时行情（如果有）
    rt = st.session_state.get("_realtime_cache", {}).get(code, {})
    if rt:
        pct = rt.get("change_pct", 0) or 0
        arrow = "▲" if pct >= 0 else "▼"
        color = "#DC143C" if pct >= 0 else "#228B22"
        st.sidebar.markdown(f"- {name} <span style='color:{color}'>{arrow}{pct:+.2f}%</span>", unsafe_allow_html=True)
    else:
        st.sidebar.markdown(f"- {name}")

st.sidebar.markdown("---")
st.sidebar.caption("数据来源：akshare | 同花顺 | 东方财富")
st.sidebar.caption("仅供研究参考，不构成投资建议")


# ============================================================
# 加载所有数据到 Session State（共享给其他页面）
# ============================================================
if "_market_data_loaded" not in st.session_state:
    st.session_state._market_data_loaded = False

if not st.session_state._market_data_loaded:
    with st.spinner("正在加载市场数据..."):
        # 获取指数行情
        st.session_state._indices_data = df_.get_all_indices()
        
        # 获取市场情绪
        st.session_state._sentiment = df_.get_market_sentiment()
        
        # 获取板块数据
        st.session_state._sector_df = df_.get_sector_spot()
        
        # 获取涨停板数据
        st.session_state._limit_up_df = df_.get_limit_up_stocks()
        
        # 获取所有持仓股的实时行情（为其他页面准备）
        st.session_state._realtime_cache = {}
        for code, name in _portfolio.items():
            rt = df_.get_stock_realtime(code)
            if rt:
                st.session_state._realtime_cache[code] = rt
        
        st.session_state._market_data_loaded = True

# 从 session_state 读取数据
indices_data = st.session_state.get("_indices_data", {})
sentiment = st.session_state.get("_sentiment", {})
sector_df = st.session_state.get("_sector_df", pd.DataFrame())
limit_up_df = st.session_state.get("_limit_up_df", pd.DataFrame())
realtime_cache = st.session_state.get("_realtime_cache", {})

# ============================================================
# 首页仪表盘
# ============================================================

st.title("📈 每日A股复盘 · 仪表盘")
st.caption(f"更新于 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | 数据来源：akshare")

# --- 第一行：三大指数 + 情绪 ---
st.subheader("📊 大盘概览")

cols_idx = st.columns(5)
for i, (name, data) in enumerate(indices_data.items()):
    if i >= 4:
        break
    with cols_idx[i]:
        price = data.get("price", 0) or 0
        pct = data.get("change_pct", 0) or 0
        st.metric(name, f"{price:.2f}" if price else "—", delta=f"{pct:+.2f}%" if pct else None)

# 情绪
with cols_idx[4]:
    st.metric("市场情绪", sentiment.get("sentiment", "—") if sentiment else "—")

# --- 第二行：市场状态 ---
st.markdown("---")
cols_status = st.columns(6)
if sentiment:
    cols_status[0].metric("上涨家数", sentiment.get("up_count", 0))
    cols_status[1].metric("下跌家数", sentiment.get("down_count", 0))
    cols_status[2].metric("涨停", sentiment.get("zt_count", 0))
    cols_status[3].metric("炸板率", f"{sentiment.get('zha_rate', 0):.1f}%")
    cols_status[4].metric("成交额(亿)", f"{sentiment.get('total_amount', 0):.0f}" if sentiment.get("total_amount") else "—")
    cols_status[5].metric("涨跌比", f"{sentiment.get('up_ratio', 0):.1f}%" if sentiment.get("up_ratio") else "—")

# --- 第三行：持仓快速预览 ---
st.markdown("---")
st.subheader("💼 持仓快速预览")

if _portfolio:
    cols_hold = st.columns(len(_portfolio))
    for i, (code, name) in enumerate(_portfolio.items()):
        with cols_hold[i]:
            rt = realtime_cache.get(code, {})
            if rt:
                price = rt.get("price", 0) or 0
                pct = rt.get("change_pct", 0) or 0
                st.metric(f"{name}", f"{price:.2f}", delta=f"{pct:+.2f}%")
            else:
                st.metric(name, "—")
else:
    st.info("暂无持仓，请在 config.py 中配置 PORTFOLIO")

# --- 第四行：板块热力图（小） ---
st.markdown("---")
col_left, col_right = st.columns([2, 1])

with col_left:
    st.subheader("🔥 板块涨跌热力图")
    if not sector_df.empty:
        fig_heat = viz.plot_sector_heatmap(sector_df, height=400)
        st.plotly_chart(fig_heat, use_container_width=True)
    else:
        st.info("板块数据暂不可用")

with col_right:
    st.subheader("📋 板块TOP5")
    if not sector_df.empty:
        top5 = sector_df.head(5)
        bottom5 = sector_df.tail(5)
        st.markdown("**🟢 涨幅前5**")
        for _, row in top5.iterrows():
            name = row.get("sector_name", "")
            pct = row.get("change_pct", 0)
            st.write(f"🔥 {name}: +{pct:.2f}%")
        st.markdown("**🔴 跌幅前5**")
        for _, row in bottom5.iterrows():
            name = row.get("sector_name", "")
            pct = row.get("change_pct", 0)
            st.write(f"📉 {name}: {pct:.2f}%")

# --- 第五行：持仓评分排行 ---
st.markdown("---")
st.subheader("⭐ 持仓综合评分排行")

hold_scores = []
for code, name in _portfolio.items():
    try:
        df = df_.get_stock_kline(code)
        if not df.empty:
            df = anl.calc_all_indicators(df)
            pred = anl.predict_next_day(df)
            trend = anl.classify_trend(df)

            score = pred.get("score", 0) * 10 + 50
            flow = df_.get_stock_fund_flow(code)
            if flow and flow.get("main_net_inflow", 0):
                if flow["main_net_inflow"] > 0:
                    score += 10
                else:
                    score -= 5
            score = max(0, min(100, score))

            hold_scores.append({
                "name": name, "code": code,
                "score": score,
                "direction": pred.get("direction", "—"),
                "confidence": pred.get("confidence", 0),
                "trend": trend.get("short_signal", "—"),
            })
    except Exception:
        hold_scores.append({"name": name, "code": code, "score": 50, "direction": "—", "confidence": 0, "trend": "—"})

if hold_scores:
    hold_scores.sort(key=lambda x: x["score"], reverse=True)
    cols_score = st.columns(len(hold_scores))
    for i, hs in enumerate(hold_scores):
        with cols_score[i]:
            score_color = "#DC143C" if hs["score"] >= 60 else "#FFD700" if hs["score"] >= 40 else "#228B22"
            st.markdown(f"### {hs['name']}")
            st.markdown(f"<h1 style='color:{score_color};text-align:center;'>{hs['score']:.0f}</h1>",
                        unsafe_allow_html=True)
            st.caption(f"评分 | {hs['direction']} | {hs['trend']}")

# --- 第六行：游资动向摘要 ---
st.markdown("---")
st.subheader("🕵️ 游资动向（近5日）")
with st.spinner("加载龙虎榜..."):
    hot_df = df_.get_hot_money_trades(days=5)

if not hot_df.empty:
    hot_summary = hot_df.groupby("hot_money_name").agg(
        操作笔数=("hot_money_name", "count"),
        净买入=("净额", "sum"),
    ).sort_values("净买入", ascending=False).reset_index()

    hot_cols = st.columns(min(5, len(hot_summary)))
    for i, (_, row) in enumerate(hot_summary.iterrows()):
        if i >= 5:
            break
        with hot_cols[i]:
            net = row["净买入"] or 0
            net_w = net / 10000
            st.metric(
                row["hot_money_name"],
                f"{net_w:+.0f}万",
                delta=f"{row['操作笔数']}笔",
            )
    fig_hot = viz.plot_hot_money_summary(hot_df, height=300)
    st.plotly_chart(fig_hot, use_container_width=True)
else:
    st.info("近5日暂无目标游资上榜记录（可能为非交易日）")

# --- 底部 ---
st.markdown("---")
st.markdown(f"""
<div style="text-align:center;color:#94A3B8;font-size:12px;">
    <p>📊 每日A股复盘模型 | 数据来源：akshare / 同花顺 / 东方财富</p>
    <p>⚠️ 以上分析仅供研究参考，不构成任何投资建议。市场有风险，投资需谨慎。</p>
    <p>数据更新时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
</div>
""", unsafe_allow_html=True)