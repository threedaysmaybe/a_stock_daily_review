"""
页面4：龙头股分析 — 涨停板 + 连板天梯 + 技术分析 + 建仓建议
"""

import streamlit as st
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import warnings
warnings.filterwarnings("ignore")

import config as cfg
import data_fetcher as df_
import analyzer as anl
import visualizer as viz
from utils.helpers import fmt_cn
import pandas as pd
import numpy as np
from datetime import datetime
import streamlit.components.v1 as components

st.set_page_config(page_title="龙头股分析", page_icon="🐉", layout="wide")

# ============================================================
# Session State 缓存
# ============================================================
if "_dragon_analyzed" not in st.session_state:
    st.session_state._dragon_analyzed = {}

if "_dragon_loaded" not in st.session_state:
    st.session_state._dragon_loaded = False


def parse_pct(val):
    """解析百分比字符串为数值"""
    if pd.isna(val) or val is None:
        return np.nan
    try:
        if isinstance(val, (int, float)):
            return float(val)
        s = str(val).strip().replace("%", "").replace(" ", "")
        return float(s)
    except:
        return np.nan


def format_time(val):
    """格式化时间为 HH:MM:SS"""
    if pd.isna(val) or val is None or val == "":
        return ""
    try:
        if isinstance(val, (int, float)):
            s = str(int(val)).zfill(6)
            return s[:2] + ":" + s[2:4] + ":" + s[4:6]
        s = str(val).strip().replace(".0", "")
        if len(s) == 6 and s.isdigit():
            return s[:2] + ":" + s[2:4] + ":" + s[4:6]
        return s
    except Exception:
        return str(val)


def get_realtime_from_cache(code: str):
    """从 session_state 获取实时行情，没有则返回空"""
    cache = st.session_state.get("_realtime_cache", {})
    return cache.get(code, {})


def render_stock_card(row: pd.Series):
    """渲染单个股票卡片 - 固定尺寸"""
    name = row.get("名称", "")
    code = row.get("代码", "")
    change_pct = row.get("涨跌幅", 0)
    
    change_pct = parse_pct(change_pct)
    if np.isnan(change_pct):
        change_pct = 0
    
    first_time = row.get("首次封板时间", "")
    is_one_board = row.get("一字板", False)
    is_blown = row.get("炸板次数", 0) > 0
    
    time_str = format_time(first_time)
    color = "#DC143C" if change_pct >= 0 else "#228B22"
    
    tags = []
    if is_one_board:
        tags.append('一字板')
    if is_blown:
        tags.append('炸板')
    if time_str and time_str not in ["00:00:00", "0:00:00"]:
        tags.append(time_str)
    
    tags_text = " | ".join(tags) if tags else ""
    
    card_html = f'''
    <div style="
        background: #1E293B;
        border-radius: 8px;
        padding: 10px 12px;
        min-height: 85px;
        height: 85px;
        border-left: 4px solid {color};
        border: 1px solid #334155;
        display: flex;
        flex-direction: column;
        justify-content: space-between;
        margin: 4px 0;
    ">
        <div style="display: flex; justify-content: space-between; align-items: center;">
            <span style="font-weight: bold; font-size: 17px; color: #FFFFFF;">{name}</span>
            <span style="color: {color}; font-weight: bold; font-size: 16px;">{change_pct:+.2f}%</span>
        </div>
        <div>
            <span style="font-size: 12px; color: #94A3B8;">{code}</span>
            <span style="font-size: 12px; color: #64748B; margin-left: 8px;">{tags_text}</span>
        </div>
    </div>
    '''
    st.markdown(card_html, unsafe_allow_html=True)


def render_ladder_board(df: pd.DataFrame):
    """渲染连板天梯"""
    if df.empty or "连板数" not in df.columns:
        st.info("暂无连板数据")
        return
    
    board_groups = {}
    for _, row in df.iterrows():
        boards = int(row.get("连板数", 1))
        if boards not in board_groups:
            board_groups[boards] = []
        board_groups[boards].append(row)
    
    max_board = max(board_groups.keys())
    
    # 板块标签
    st.subheader("📊 连板天梯")
    today = datetime.now().strftime("%m月%d日 %A")
    st.caption(f"📅 {today}")
    
    sector_counts = {}
    for _, row in df.iterrows():
        sector = row.get("所属行业", "其他")
        if pd.isna(sector) or not sector:
            sector = "其他"
        sector_counts[sector] = sector_counts.get(sector, 0) + 1
    
    sorted_sectors = sorted(sector_counts.items(), key=lambda x: -x[1])
    
    cols_per_row = 8
    for i in range(0, len(sorted_sectors), cols_per_row):
        row_sectors = sorted_sectors[i:i+cols_per_row]
        cols = st.columns(cols_per_row)
        for j, (sector, count) in enumerate(row_sectors):
            with cols[j]:
                st.markdown(f"**{sector}** ({count})")
    
    st.divider()
    
    # 连板天梯
    for board_num in range(max_board, 0, -1):
        if board_num not in board_groups:
            continue
        
        stocks = board_groups[board_num]
        
        if board_num >= 6:
            label = f"🔥 {board_num}板 🏆"
        elif board_num >= 4:
            label = f"⭐ {board_num}板"
        elif board_num >= 2:
            label = f"📌 {board_num}板"
        else:
            label = "📌 首板"
        
        st.markdown(f"### {label}  ({len(stocks)}只)")
        
        cols_per_row = 4
        for i in range(0, len(stocks), cols_per_row):
            row_stocks = stocks[i:i+cols_per_row]
            cols = st.columns(cols_per_row)
            for j, stock in enumerate(row_stocks):
                with cols[j]:
                    render_stock_card(stock)
        
        st.divider()


# ============================================================
# 1. 获取数据
# ============================================================
st.title("🐉 热门龙头股分析")
st.caption(f"交易日：{(st.session_state.get('_trading_day') or pd.Timestamp.now()).strftime('%Y-%m-%d')}")

st.subheader("📋 今日涨停板")

# 优先从 session_state 读取，没有则重新获取
limit_up_df = st.session_state.get("_limit_up_df")
if limit_up_df is None or limit_up_df.empty:
    with st.spinner("正在获取涨停板数据..."):
        limit_up_df = df_.get_limit_up_stocks()
        st.session_state["_limit_up_df"] = limit_up_df

if limit_up_df.empty:
    st.warning("今日暂无涨停板数据（可能为非交易日）")
    st.stop()

# ---- 统计概览 ----
col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("📈 涨停家数", len(limit_up_df))

if "连板数" in limit_up_df.columns:
    max_boards = limit_up_df["连板数"].max()
    col2.metric("🏆 最高连板", f"{max_boards}连板")
    multi_boards = len(limit_up_df[limit_up_df["连板数"] > 1])
    col3.metric("📌 连板股数", multi_boards)
    
    if "炸板次数" in limit_up_df.columns:
        blown_count = len(limit_up_df[limit_up_df["炸板次数"] > 0])
        blown_rate = blown_count / len(limit_up_df) * 100
        col4.metric("💥 炸板率", f"{blown_rate:.1f}%")
    
    if "一字板" in limit_up_df.columns:
        one_board_count = len(limit_up_df[limit_up_df["一字板"] == True])
        col5.metric("🔒 一字板", one_board_count)

st.divider()

# ============================================================
# 一次性分析所有涨停股（只在首次加载时执行）
# ============================================================
if not st.session_state._dragon_loaded:
    with st.spinner("正在分析所有涨停股技术指标..."):
        progress_bar = st.progress(0, text="分析进度")
        total = len(limit_up_df)
        
        for idx, (_, row) in enumerate(limit_up_df.iterrows()):
            code = str(row.get("代码", "")).zfill(6)
            name = row.get("名称", "")
            
            kdf = df_.get_stock_kline(code, days=120)
            if not kdf.empty:
                kdf = anl.calc_all_indicators(kdf)
                pred = anl.predict_next_day(kdf)
                trend = anl.classify_trend(kdf)
                sr = anl.calc_stop_loss_take_profit(kdf, "中等")
                
                st.session_state._dragon_analyzed[code] = {
                    "kline": kdf,
                    "pred": pred,
                    "trend": trend,
                    "sr": sr,
                    "name": name,
                }
            
            progress_bar.progress((idx + 1) / total, text=f"分析中 ({idx+1}/{total}) {name}")
        
        progress_bar.empty()
        st.session_state._dragon_loaded = True
        st.rerun()

# ============================================================
# 显示连板天梯
# ============================================================
render_ladder_board(limit_up_df)

# ---- 完整数据表格 ----
with st.expander("📊 查看完整涨停板数据"):
    ddf = limit_up_df.copy()
    
    display_cols = ["代码", "名称", "涨跌幅", "所属行业", "连板数", "炸板次数", "首次封板时间", "最后封板时间"]
    available_cols = [c for c in display_cols if c in ddf.columns]
    
    if "一字板" in ddf.columns:
        available_cols.append("一字板")
    
    ddf_display = ddf[available_cols].copy()
    
    for col in ddf_display.columns:
        col_lower = str(col).lower()
        
        if "封板时间" in col_lower:
            ddf_display[col] = ddf_display[col].apply(format_time)
        
        elif "涨跌幅" in col_lower:
            ddf_display[col] = ddf_display[col].apply(parse_pct)
        
        elif "一字板" in col_lower:
            ddf_display[col] = ddf_display[col].apply(lambda x: "✅" if x else "")
    
    column_config = {}
    for col in ddf_display.columns:
        col_lower = str(col).lower()
        if "涨跌幅" in col_lower:
            column_config[col] = st.column_config.NumberColumn(
                col, format="%.2f%%", width="small"
            )
        elif "代码" in col_lower:
            column_config[col] = st.column_config.TextColumn(col, width="small")
        elif "名称" in col_lower:
            column_config[col] = st.column_config.TextColumn(col, width="medium")
        elif "所属行业" in col_lower:
            column_config[col] = st.column_config.TextColumn(col, width="medium")
        elif "连板数" in col_lower or "炸板次数" in col_lower:
            column_config[col] = st.column_config.NumberColumn(col, width="small")
        elif "封板时间" in col_lower:
            column_config[col] = st.column_config.TextColumn(col, width="small")
        elif "一字板" in col_lower:
            column_config[col] = st.column_config.TextColumn(col, width="small")
    
    st.dataframe(
        ddf_display,
        column_config=column_config,
        hide_index=True,
        use_container_width=True,
        height=400
    )

st.divider()

# ============================================================
# 2. 龙头股技术分析（直接从缓存读取）
# ============================================================
st.subheader("🔍 龙头股技术分析")

stock_options = []
for _, row in limit_up_df.iterrows():
    code = str(row.get("代码", "")).zfill(6)
    name = row.get("名称", "")
    boards = row.get("连板数", 1)
    stock_options.append(f"{code} — {name} ({boards}连板)")

selected = st.selectbox("选择涨停股进行深度分析", stock_options, key="dragon_select")

if selected:
    parts = selected.split("—")
    code = parts[0].strip()
    name = parts[1].strip().split("(")[0].strip()
    
    analyzed = st.session_state._dragon_analyzed.get(code)
    
    if analyzed is None:
        st.warning(f"{name}({code}) 分析数据不存在")
    else:
        kdf = analyzed["kline"]
        pred = analyzed["pred"]
        trend = analyzed["trend"]
        sr = analyzed["sr"]
        
        # ---- 从 session_state 读取实时行情（不再请求网络） ----
        rt = get_realtime_from_cache(code)
        
        st.subheader(f"📊 {name} ({code}) 实时行情")
        metric_cols = st.columns(6)
        
        # 从K线获取最新价作为备选
        latest_close = kdf["close"].iloc[-1] if not kdf.empty else 0
        
        price = rt.get("price", 0) or latest_close
        change_pct = rt.get("change_pct", 0)
        amount = rt.get("amount", 0)
        turnover = rt.get("turnover", 0)
        pe = rt.get("pe", 0)
        pb = rt.get("pb", 0)
        total_mv = rt.get("total_mv", 0)
        
        metric_cols[0].metric("最新价", f"{price:.2f}" if price else "—")
        metric_cols[1].metric(
            "涨跌幅", 
            f"{change_pct:+.2f}%" if change_pct else "—",
            delta=f"{rt.get('change_amt', 0):+.2f}" if rt.get('change_amt') else None,
            delta_color="inverse"
        )
        metric_cols[2].metric("成交额", fmt_cn(amount) if amount else "—")
        metric_cols[3].metric("换手率", f"{turnover:.2f}%" if turnover else "—")
        metric_cols[4].metric("PE/PB", f"{pe:.1f}/{pb:.1f}" if pe else "—")
        metric_cols[5].metric("总市值", fmt_cn(total_mv) if total_mv else "—")
        
        # ---- K线图（ECharts，支持缩放拖动） ----
        st.subheader("📈 K线图")
        kline_html = viz.plot_kline_echarts(kdf, title=f"{name}({code}) · 日K线", height=500)
        components.html(kline_html, height=530)
        
        # ---- 技术指标（ECharts，支持缩放拖动） ----
        st.subheader("🔧 技术指标")
        indicator_tabs = st.tabs(["MACD", "KDJ", "RSI", "BOLL"])
        indicator_types = ["MACD", "KDJ", "RSI", "BOLL"]
        for tab, ind_type in zip(indicator_tabs, indicator_types):
            with tab:
                ind_html = viz.plot_indicator_echarts(kdf, ind_type, height=280)
                components.html(ind_html, height=310)
        
        # ---- 趋势研判 ----
        st.subheader("📋 趋势研判")
        trend_cols = st.columns(4)
        trend_cols[0].info(f"**短期趋势**\n\n{trend.get('short_signal', '—')}")
        trend_cols[1].info(f"**中期趋势**\n\n{trend.get('mid_signal', '—')}")
        trend_cols[2].info(f"**MACD信号**\n\n{trend.get('macd_signal', '—')}")
        patterns = anl.detect_patterns(kdf)
        if patterns:
            trend_cols[3].warning(f"**K线形态**\n\n" + "\n".join(patterns))
        else:
            trend_cols[3].info("**K线形态**\n\n无明显形态")
        
        # ---- 明日预测 ----
        st.subheader("🔮 明日预测")
        pred_cols = st.columns(3)
        pred_cols[0].metric("预测方向", pred.get("direction", "—"))
        pred_cols[1].metric("置信度", f"{pred.get('confidence', 0)}%")
        pred_cols[2].metric("波动区间", pred.get("range", "—"))
        if pred.get("reasons"):
            with st.expander("📝 预测依据"):
                for reason in pred["reasons"]:
                    st.caption(f"• {reason}")
        
        # ---- 止盈止损 ----
        if sr:
            st.subheader("🎯 止盈止损位")
            sr_cols = st.columns(5)
            sr_cols[0].error(f"**止损（严格）**\n¥{sr.get('stop_loss_tight', '—')}")
            sr_cols[1].warning(f"**止损（宽松）**\n¥{sr.get('stop_loss_loose', '—')}")
            sr_cols[2].success(f"**止盈1**\n¥{sr.get('take_profit_1', '—')}")
            sr_cols[3].success(f"**止盈2**\n¥{sr.get('take_profit_2', '—')}")
            sr_cols[4].info(f"**建议仓位**\n{sr.get('suggested_position', '—')}")

st.divider()

# ============================================================
# 3. 明日建仓建议
# ============================================================
st.subheader("📋 明日建仓建议")
st.caption("基于技术指标综合评分，筛选明日值得关注的标的")

candidates = []
for _, row in limit_up_df.iterrows():
    code = str(row.get("代码", "")).zfill(6)
    name = row.get("名称", "")
    
    analyzed = st.session_state._dragon_analyzed.get(code)
    if analyzed is None:
        continue
    
    pred = analyzed["pred"]
    trend = analyzed["trend"]
    
    score = pred.get("score", 0)
    if "多头" in trend.get("short_trend", ""):
        score += 2
    if "金叉" in trend.get("macd_signal", ""):
        score += 1
    
    boards = int(row.get("连板数", 1))
    if boards >= 5:
        score -= 2
    elif boards >= 3:
        score -= 1
    
    if score <= 0:
        continue
    
    candidates.append({
        "code": code,
        "name": name,
        "score": round(score, 1),
        "direction": pred.get("direction", "—"),
        "confidence": pred.get("confidence", 0),
        "boards": boards,
        "trend_signal": trend.get("short_signal", "—"),
    })

if candidates:
    candidates.sort(key=lambda x: x["score"], reverse=True)
    st.info(f"共筛选出 {len(candidates)} 个潜在标的")
    for i, c in enumerate(candidates[:5]):
        medals = ["🥇", "🥈", "🥉"]
        icon = medals[i] if i < 3 else f"{i+1}."
        cols = st.columns([1, 3, 2, 2, 2])
        cols[0].write(f"### {icon}")
        cols[1].write(f"**{c['name']}** ({c['code']})")
        cols[2].write(f"评分：**{c['score']}** 分")
        cols[3].write(f"{c['direction']} (置信度{c['confidence']}%)")
        cols[4].write(f"{c['boards']}连板 · {c['trend_signal']}")
    
    best = candidates[0]
    st.divider()
    st.success(f"""
    ### 💡 最优建仓建议
    
    **{best['name']}（{best['code']}）**
    
    - 📊 综合评分：**{best['score']}** 分
    - 🔮 预测方向：{best['direction']}（置信度 {best['confidence']}%）
    - 📈 趋势信号：{best['trend_signal']}
    - 🔥 连板数：{best['boards']} 连板
    
    > ⚠️ **风险提示**：涨停股次日通常高开，建议集合竞价观察强度，切勿追高。
    > 止损位可参考涨停价下方 3%-5%。
    """)
else:
    st.warning("当前无符合筛选条件的标的，建议观望")

st.divider()
st.caption("⚠️ 以上分析仅供研究参考，不构成投资建议。市场有风险，投资需谨慎。")