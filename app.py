"""
每日A股复盘模型 — Streamlit Web应用
主入口：仪表盘概览 + 页面路由

启动方式：
    cd a_stock_daily_review
    streamlit run app.py

手机访问：启动后在浏览器打开 http://你的IP:8501
"""

import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import numpy as np
import os
import sys
import subprocess
import json
import base64
import time
from datetime import datetime

# ============================================================
# 导入自定义模块
# ============================================================
import config as cfg
import data_fetcher as df_
import analyzer as anl
import visualizer as viz
import data_manager as dm
from utils.ui import inject_css, conclusion, pct_color

# ============================================================
# Streamlit 页面配置
# ============================================================
st.set_page_config(
    page_title="每日A股复盘",
    page_icon="stock.png",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(f"""
<!-- 手机主屏幕图标（保留 title/theme 等 meta） -->
<meta name="apple-mobile-web-app-title" content="A股复盘">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="theme-color" content="#1a73e8">
""", unsafe_allow_html=True)

# 动态注入 apple-touch-icon 到顶层 head（iOS「添加到主屏幕」图标）
# Streamlit 只能往 body 注入 HTML，需用 JS 操作 parent document 的 head
components.html(
    """
    <script>
    (function() {
        try {
            const parentDoc = window.parent.document;
            const head = parentDoc.head || parentDoc.getElementsByTagName('head')[0];
            const iconUrl = window.location.origin + '/app/static/apple-touch-icon.png';
            ['180x180', '152x152', '120x120'].forEach(function(sz) {
                let link = parentDoc.querySelector('link[rel="apple-touch-icon"][sizes="' + sz + '"]');
                if (!link) {
                    link = parentDoc.createElement('link');
                    link.rel = 'apple-touch-icon';
                    link.sizes = sz;
                    head.appendChild(link);
                }
                link.href = iconUrl;
            });
        } catch (e) {}
    })();
    </script>
    """,
    height=0,
    width=0,
)

# ============================================================
# 加载持仓（统一走 data_manager，代码规范化，全页面一致）
def load_portfolio() -> dict:
    return dm.load_portfolio()


# ============================================================
# 侧边栏
# ============================================================
st.sidebar.title("📈 每日A股复盘")
st.sidebar.caption(
    f"📅 {st.session_state.get('_trading_day', datetime.now()):%Y-%m-%d}"
    if st.session_state.get('_trading_day') else
    f"📅 {datetime.now():%Y-%m-%d %H:%M}"
)

# 导航
st.sidebar.markdown("---")
st.sidebar.markdown("### 📋 导航")

pages = {
    "🏠 首页仪表盘": "app",
    "📊 大盘走势": "01_📊_大盘走势",
    "🔥 板块分析": "02_🔥_板块分析",
    "💹 资金情绪": "03_💹_资金情绪",
    "🏆 板块龙头": "10_🏆_板块龙头",
    "💼 持仓分析": "05_💼_持仓分析",
    "🎯 选股决策": "07_🎯_选股决策",
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
    # 进度条放侧边栏，避免遮挡主页、避免"卡在主页"的观感
    progress_bar = st.sidebar.progress(0, text="⏳ 准备下载...")
    status_text = st.sidebar.empty()

    def on_progress(i, total, name):
        pct = min((i + 1) / total, 0.95) if total > 0 else 0.95
        shown = min(i + 1, total)
        progress_bar.progress(pct, text=f"📥 ({shown}/{total}) {name}")
        status_text.caption(f"正在获取：{name}")

    meta = dm.download_all(progress_callback=on_progress)
    # 重置模块级缓存
    df_.get_sector_spot._cache = None
    df_.get_concept_spot._cache = None
    
    # 快速回补缺失的行业排名（单个API调用很快）
    missing = meta.get("backfill_needed", [])
    if missing:
        for i, (date_str, kind) in enumerate(missing):
            label = "行业" if kind == "sectors" else "概念"
            progress_bar.progress(0.95 + 0.05 * (i + 1) / (len(missing) + 1),
                                  text=f"📌 回补 {date_str} {label}排名...")
            dm.backfill_one(date_str, kind)
    
    # 个股深度数据（研报用）在「持仓分析」页按需采集，这里跳过，避免更新卡住
    # （stock_data_collect.py 逐只跑 subprocess，很慢，且非每日复盘必需）

    # 顺便跑选股引擎（不推送；结果存 stock_choose/output，供选股决策页/定时推送使用）
    try:
        from stock_choose import main as stock_choose_main
        sc_cfg = stock_choose_main.load_config("config.yaml")
        sc_date = stock_choose_main.default_run_date()
        if sc_date is None:
            status_text.caption("今天休市，跳过选股引擎")
        else:
            progress_bar.progress(0.97, text=f"🎯 跑选股引擎（{sc_date}）...")
            status_text.caption("选股引擎运行中：全市场数据 + 因子打分 + 信号 + 情绪仓位（约2-3分钟）")
            stock_choose_main.run_daily_pipeline(sc_cfg, sc_date, push=False)
            status_text.caption(f"✅ 选股完成：{sc_date}")
    except Exception as e:
        status_text.caption(f"选股引擎出错（不影响数据更新）：{type(e).__name__}: {e}")

    progress_bar.progress(1.0, text="✅ 全部完成，正在刷新...")
    progress_bar.empty()
    status_text.empty()
    if meta["ok"] > 0:
        # 清除所有缓存 + 强制下次读盘
        st.cache_data.clear()
        for k in ["_indices_data", "_sentiment", "_sector_df", "_concept_df", "_limit_up_df", "_realtime_cache", "holdings_pred", "holdings_pred_key"]:
            st.session_state.pop(k, None)
        st.session_state._market_data_loaded = False
        st.session_state._update_summary = f"成功 {meta['ok']}，失败 {meta['fail']}"
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
    # 全部从本地文件读取，不走缓存函数（避免右上角 Running xxx）
    st.session_state._indices_data = df_.get_all_indices()
    
    # 交易日：读上证K线本地文件
    try:
        sh_kline = dm.load_local("index_000001.csv")
        if sh_kline is not None and not sh_kline.empty:
            st.session_state._trading_day = sh_kline["date"].iloc[-1]
    except Exception:
        st.session_state._trading_day = datetime.now()
    
    # 市场情绪（读本地，秒返回）
    st.session_state._sentiment = df_.get_market_sentiment()
    
    s = dm.load_local("sectors.csv")
    st.session_state._sector_df = s if (s is not None and not (hasattr(s, 'empty') and s.empty)) else df_.get_sector_spot()
    c = dm.load_local("concept_sectors.csv")
    st.session_state._concept_df = c if (c is not None and not (hasattr(c, 'empty') and c.empty)) else df_.get_concept_spot()
    l = dm.load_local("limit_up.csv")
    st.session_state._limit_up_df = l if (l is not None and not (hasattr(l, 'empty') and l.empty)) else df_.get_limit_up_stocks()
    
    st.session_state._realtime_cache = {}
    # 从本地K线读最新收盘价
    for code, name in _portfolio.items():
        try:
            kf = dm.load_local(f"stock_{code}.csv")
            if kf is not None and not kf.empty and "close" in kf.columns:
                last = kf.iloc[-1]
                prev = kf.iloc[-2] if len(kf) >= 2 else last
                pct = (float(last["close"]) - float(prev["close"])) / float(prev["close"]) * 100 if len(kf) >= 2 else 0
                st.session_state._realtime_cache[code] = {
                    "price": float(last["close"]),
                    "change_pct": round(pct, 2),
                }
        except Exception:
            pass
    
    st.session_state._market_data_loaded = True

    # ===== 数据健康自检（防呆：主动报告哪些数据没拿到，不静默显示 0）=====
    _health = {}
    _sent = st.session_state.get("_sentiment") or {}
    _health["市场情绪"] = bool(_sent.get("up_count"))
    _sdf = st.session_state.get("_sector_df")
    _health["行业板块"] = _sdf is not None and len(_sdf) > 0
    _cdf = st.session_state.get("_concept_df")
    _health["概念板块"] = _cdf is not None and len(_cdf) > 0
    _ldf = st.session_state.get("_limit_up_df")
    _health["涨停池"] = _ldf is not None and len(_ldf) > 0
    _idx = st.session_state.get("_indices_data") or {}
    _health["指数行情"] = len(_idx) > 0
    st.session_state._data_health = _health
    st.session_state._data_health_warning = [k for k, v in _health.items() if not v]

# 从 session_state 读取数据
indices_data = st.session_state.get("_indices_data", {})
sentiment = st.session_state.get("_sentiment", {})
sector_df = st.session_state.get("_sector_df", pd.DataFrame())
limit_up_df = st.session_state.get("_limit_up_df", pd.DataFrame())
realtime_cache = st.session_state.get("_realtime_cache", {})

# 统一交易日显示
_trading_day = st.session_state.get("_trading_day", datetime.now())
_trading_day_str = _trading_day.strftime("%Y-%m-%d") if hasattr(_trading_day, 'strftime') else str(_trading_day)[:10]

# ============================================================
# 首页仪表盘
# ============================================================

inject_css()
st.title("📈 每日A股复盘 · 仪表盘")
st.caption(f"交易日 {_trading_day_str} | 数据来源：Tushare + akshare")

# 数据健康警告（防呆：主动报告哪些数据没拿到）
if st.session_state.get("_data_health_warning"):
    _miss = st.session_state["_data_health_warning"]
    st.warning(f"⚠️ 以下数据暂不可用：{'、'.join(_miss)}（可能休市或数据源异常，相关指标会显示「无数据」而非 0）")

# 核心结论卡片（突出主次）
if isinstance(sentiment, dict) and sentiment.get("up_count"):
    _up = sentiment.get("up_count", 0)
    _down = sentiment.get("down_count", 0)
    _ratio = sentiment.get("up_ratio", 0) or 0
    _zt = sentiment.get("zt_count", 0) or (len(limit_up_df) if not limit_up_df.empty else 0)
    _amt = sentiment.get("total_amount", 0) or 0
    _sent = (sentiment.get("sentiment") or "").lstrip("🔥😊😐😟❄️💀").strip()
    if _ratio > 65:
        _tone, _verdict = "bull", "偏暖，短线可积极"
    elif _ratio > 50:
        _tone, _verdict = "neutral", "中性，精选个股"
    elif _ratio > 35:
        _tone, _verdict = "bear", "偏冷，控制仓位"
    else:
        _tone, _verdict = "bear", "冰点/恐慌，谨慎观望"
    conclusion(f"市场情绪：{_sent or '—'} → {_verdict}",
               f"上涨 <b>{_up}</b> 家 / 下跌 <b>{_down}</b> 家（上涨占比 {_ratio:.1f}%），"
               f"涨停 <b>{_zt}</b> 家，两市成交 <b>{_amt:.0f}</b> 亿。",
               tone=_tone)

# 显示更新完成通知
if st.session_state.get("_update_summary"):
    summary = st.session_state.pop("_update_summary")
    st.toast(f"✅ 数据更新完成！{summary}", icon="✅")
    st.balloons()

# --- 第一行：三大指数 + 情绪 ---
st.subheader("📊 大盘概览")

cols_idx = st.columns(5)
for i, (name, data) in enumerate(indices_data.items()):
    if i >= 4:
        break
    with cols_idx[i]:
        price = data.get("price", 0) or 0
        pct = data.get("change_pct", 0) or 0
        st.metric(name, f"{price:.2f}" if price else "—", delta=f"{pct:+.2f}%" if pct else None, delta_color="inverse")

# 情绪
raw_sent = (sentiment or {}).get("sentiment", "") if isinstance(sentiment, dict) else ""
_s = raw_sent.lstrip("🔥😊😐😟❄️💀").strip()
with cols_idx[4]:
    st.metric("市场情绪", _s if _s else "—")

# --- 第二行：市场状态 ---
st.markdown("---")
cols_status = st.columns(6)
if isinstance(sentiment, dict):
    up = sentiment.get("up_count", 0)
    down = sentiment.get("down_count", 0)
    up_delta, down_delta = None, None
    # 较前一交易日涨跌家数变化
    try:
        data_dir = "data"
        dates = sorted([d for d in os.listdir(data_dir) 
                       if os.path.isdir(os.path.join(data_dir, d)) and d.isdigit()], reverse=True)
        today_sent = None
        for dd in dates:
            sp = os.path.join(data_dir, dd, "sentiment.json")
            if os.path.exists(sp):
                import json
                with open(sp, "r", encoding="utf-8") as f:
                    sdata = json.load(f)
                if sdata.get("up_count"):  # 有效数据
                    if today_sent is None:
                        today_sent = sdata  # 第一个有效=今天
                    else:
                        # 前一个有效=昨天
                        up_delta = up - sdata.get("up_count", 0)
                        down_delta = down - sdata.get("down_count", 0)
                        break
    except Exception:
        pass
    # 涨停/炸板从 limit_up 实时取
    zt_df = st.session_state.get("_limit_up_df", pd.DataFrame())
    zt_count = len(zt_df) if not zt_df.empty else sentiment.get("zt_count", 0)
    if not zt_df.empty and "炸板次数" in zt_df.columns:
        zha_count = int((zt_df["炸板次数"] > 0).sum())
        zha_rate = zha_count / len(zt_df) * 100 if len(zt_df) > 0 else 0
    else:
        zha_rate = sentiment.get("zha_rate", 0)

    total_amt = sentiment.get("total_amount", 0) or 0
    # 成交额相较昨日变化
    amt_delta_str = ""
    try:
        amt_kline = df_.get_index_kline("000001")
        if amt_kline is not None and not amt_kline.empty and len(amt_kline) >= 2:
            col = "amount" if "amount" in amt_kline.columns else ("volume" if "volume" in amt_kline.columns else None)
            if col:
                prev_val = float(amt_kline[col].iloc[-2])
                if prev_val > 0:
                    amt_change = (float(amt_kline[col].iloc[-1]) - prev_val) / prev_val * 100
                    amt_delta_str = f"{amt_change:+.1f}%"
    except Exception:
        pass

    cols_status[0].metric("上涨家数", f"{up}",
                          delta=f"{up_delta:+d}" if up_delta is not None else None,
                          delta_color="inverse")
    cols_status[1].metric("下跌家数", f"{down}",
                          delta=f"{down_delta:+d}" if down_delta is not None else None,
                          delta_color="inverse")
    cols_status[2].metric("涨停", f"{zt_count}")
    cols_status[3].metric("炸板率", f"{zha_rate:.1f}%")
    cols_status[4].metric("成交额(亿)", f"{total_amt:.0f}" if total_amt else "—",
                          delta=amt_delta_str if amt_delta_str else None,
                          delta_color="inverse")
    cols_status[5].metric("涨跌比", f"{sentiment.get('up_ratio', 0):.1f}%" if sentiment.get("up_ratio") else "—")

# --- 第三行：持仓快速预览 ---
st.markdown("---")
st.subheader("💼 持仓快速预览")

if _portfolio:
    cols_hold = st.columns(len(_portfolio))
    for i, (code, name) in enumerate(_portfolio.items()):
        with cols_hold[i]:
            rt = realtime_cache.get(code)
            if not rt:
                # 兜底：从本地K线读
                try:
                    kf = dm.load_local(f"stock_{code}.csv")
                    if kf is not None and not kf.empty and "close" in kf.columns:
                        last = kf.iloc[-1]
                        prev = kf.iloc[-2] if len(kf) >= 2 else last
                        pct = (float(last["close"]) - float(prev["close"])) / float(prev["close"]) * 100 if len(kf) >= 2 else 0
                        rt = {"price": float(last["close"]), "change_pct": round(pct, 2)}
                except Exception:
                    pass
            if rt:
                price = rt.get("price", 0) or 0
                pct = rt.get("change_pct", 0) or 0
                st.metric(f"{name}", f"{price:.2f}", delta=f"{pct:+.2f}%", delta_color="inverse")
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
    <p>交易日：{_trading_day_str} · 数据来源：akshare / 同花顺 / 东方财富</p>
</div>
""", unsafe_allow_html=True)