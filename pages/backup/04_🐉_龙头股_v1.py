"""
页面4：龙头股分析 — 涨停板 + 连板 + 技术分析 + 建仓建议
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

st.set_page_config(page_title="龙头股分析", page_icon="🐉", layout="wide")

# ============================================================
# Session State 缓存
# ============================================================
if "_dragon_cache" not in st.session_state:
    st.session_state._dragon_cache = {}

def get_analyzed_stock(code: str):
    """获取已分析的股票数据（带缓存）"""
    if code in st.session_state._dragon_cache:
        return st.session_state._dragon_cache[code]
    
    kdf = df_.get_stock_kline(code, days=120)
    if kdf.empty:
        st.session_state._dragon_cache[code] = None
        return None
    
    kdf = anl.calc_all_indicators(kdf)
    result = {
        "kline": kdf,
        "pred": anl.predict_next_day(kdf),
        "trend": anl.classify_trend(kdf),
        "sr": anl.calc_stop_loss_take_profit(kdf, "中等"),
    }
    st.session_state._dragon_cache[code] = result
    return result

# ============================================================
# 页面标题
# ============================================================
st.title("🐉 热门龙头股分析")
st.caption(f"数据更新时间：{pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}")

# ============================================================
# 1. 涨停板列表
# ============================================================
st.subheader("📋 今日涨停板")

with st.spinner("正在获取涨停板数据..."):
    limit_up_df = df_.get_limit_up_stocks()

if limit_up_df.empty:
    st.warning("今日暂无涨停板数据（可能为非交易日）")
    st.stop()

# 格式化涨停板数据
ddf = limit_up_df.copy()

# 处理各列格式
for col in ddf.columns:
    col_lower = str(col).lower()
    
    # 时间列：封板时间
    if any(k in col_lower for k in ["封板时间", "封板"]):
        try:
            t = ddf[col].astype(str).str.replace(".0", "", regex=False).str.zfill(6)
            ddf[col] = t.str[:2] + ":" + t.str[2:4] + ":" + t.str[4:6]
        except Exception:
            pass
    
    # 百分比列：涨跌幅、换手率
    elif any(k in col_lower for k in ["涨跌幅", "换手率", "换手"]):
        try:
            ddf[col] = pd.to_numeric(ddf[col], errors="coerce").apply(
                lambda v: f"{v:+.2f}%" if pd.notna(v) else "—"
            )
        except Exception:
            pass
    
    # 金额列：成交额、封板资金、市值
    elif any(k in str(col).lower() for k in ["成交额", "封板资金", "流通市值", "总市值"]):
        try:
            ddf[col] = pd.to_numeric(ddf[col], errors="coerce").apply(
                lambda v: fmt_cn(v) if pd.notna(v) else "—"
            )
        except Exception:
            pass

st.dataframe(ddf, hide_index=True, use_container_width=True, height=400)

col1, col2, col3 = st.columns(3)
col1.metric("涨停家数", len(limit_up_df))

# 计算连板统计
if "连板数" in limit_up_df.columns:
    max_boards = limit_up_df["连板数"].max()
    col2.metric("最高连板", f"{max_boards}连板")
    multi_boards = len(limit_up_df[limit_up_df["连板数"] > 1])
    col3.metric("连板股数", multi_boards)

st.divider()

# ============================================================
# 2. 连板龙虎榜
# ============================================================
if "连板数" in limit_up_df.columns:
    st.subheader("🔥 连板龙虎榜")
    multi_board_df = limit_up_df[limit_up_df["连板数"] > 1].sort_values("连板数", ascending=False)
    
    if not multi_board_df.empty:
        cols = st.columns(min(4, len(multi_board_df)))
        for i, (_, row) in enumerate(multi_board_df.iterrows()):
            if i >= 4:
                break
            name = row.get("名称", "")
            code = row.get("代码", "")
            boards = int(row["连板数"])
            fire = "🔥" * min(boards, 5)
            with cols[i]:
                st.markdown(f"### {fire}")
                st.markdown(f"**{name}**")
                st.caption(f"{code} · {boards}连板")
    else:
        st.info("今日无连板股（仅首板）")

st.divider()

# ============================================================
# 3. 龙头股技术分析（选择涨停股）
# ============================================================
st.subheader("🔍 龙头股技术分析")

# 构建选择列表
stock_options = []
for _, row in limit_up_df.iterrows():
    code = str(row.get("代码", "")).zfill(6)
    name = row.get("名称", "")
    boards = row.get("连板数", 1)
    stock_options.append(f"{code} — {name} ({boards}连板)")

selected = st.selectbox("选择涨停股进行分析", stock_options, key="dragon_select")

if selected:
    # 解析选择
    parts = selected.split("—")
    code = parts[0].strip()
    name = parts[1].strip().split("(")[0].strip()
    
    # 获取实时行情
    with st.spinner(f"正在加载 {name} 数据..."):
        rt = df_.get_stock_realtime(code)
        result = get_analyzed_stock(code)
    
    if result is None:
        st.warning(f"无法获取 {name}({code}) 的K线数据")
    else:
        kdf = result["kline"]
        pred = result["pred"]
        trend = result["trend"]
        sr = result["sr"]
        
        # ---- 实时行情指标 ----
        st.subheader(f"📊 {name} ({code}) 实时行情")
        metric_cols = st.columns(6)
        
        if rt:
            metric_cols[0].metric("最新价", f"{rt.get('price', 0):.2f}")
            metric_cols[1].metric(
                "涨跌幅", 
                f"{rt.get('change_pct', 0):+.2f}%",
                delta=f"{rt.get('change_amt', 0):+.2f}" if rt.get('change_amt') else None
            )
            metric_cols[2].metric("成交额", fmt_cn(rt.get('amount', 0)) or "—")
            metric_cols[3].metric(
                "换手率", 
                f"{rt.get('turnover', 0):.2f}%" if rt.get('turnover') else "—"
            )
            metric_cols[4].metric(
                "PE/PB", 
                f"{rt.get('pe', 0):.1f}/{rt.get('pb', 0):.1f}" if rt.get('pe') else "—"
            )
            metric_cols[5].metric("总市值", fmt_cn(rt.get('total_mv', 0)) or "—")
        else:
            for col in metric_cols:
                col.metric("—", "—")
        
        # ---- K线图 ----
        st.subheader("📈 K线图")
        fig_kline = viz.plot_kline_with_volume(
            kdf, 
            title=f"{name}({code}) · 日K线", 
            height=500
        )
        st.plotly_chart(fig_kline, use_container_width=True)
        
        # ---- 技术指标选择 ----
        st.subheader("🔧 技术指标")
        indicator_tabs = st.tabs(["MACD", "KDJ", "RSI", "BOLL"])
        
        indicator_functions = {
            "MACD": viz.plot_macd,
            "KDJ": viz.plot_kdj,
            "RSI": viz.plot_rsi,
            "BOLL": viz.plot_boll,
        }
        
        for tab, name_key in zip(indicator_tabs, indicator_functions.keys()):
            with tab:
                fig = indicator_functions[name_key](kdf)
                st.plotly_chart(fig, use_container_width=True)
        
        # ---- 趋势研判 ----
        st.subheader("📋 趋势研判")
        trend_cols = st.columns(4)
        trend_cols[0].info(f"**短期趋势**\n\n{trend.get('short_signal', '—')}")
        trend_cols[1].info(f"**中期趋势**\n\n{trend.get('mid_signal', '—')}")
        trend_cols[2].info(f"**MACD信号**\n\n{trend.get('macd_signal', '—')}")
        
        # K线形态
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
        
        # 预测理由
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
# 4. 明日建仓建议
# ============================================================
st.subheader("📋 明日建仓建议")
st.caption("基于技术指标综合评分，筛选明日值得关注的标的")

with st.spinner("正在分析涨停股..."):
    candidates = []
    
    for _, row in limit_up_df.iterrows():
        code = str(row.get("代码", "")).zfill(6)
        name = row.get("名称", "")
        
        result = get_analyzed_stock(code)
        if result is None:
            continue
        
        pred = result["pred"]
        trend = result["trend"]
        
        # 计算综合评分
        score = pred.get("score", 0)
        
        # 趋势加分
        if "多头" in trend.get("short_trend", ""):
            score += 2
        if "金叉" in trend.get("macd_signal", ""):
            score += 1
        
        # 连板扣分（太高容易分歧）
        boards = int(row.get("连板数", 1))
        if boards >= 5:
            score -= 2
        elif boards >= 3:
            score -= 1
        
        # 只保留正分标的
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
    # 按评分排序
    candidates.sort(key=lambda x: x["score"], reverse=True)
    
    st.info(f"共筛选出 {len(candidates)} 个潜在标的")
    
    # 展示前5名
    for i, c in enumerate(candidates[:5]):
        medals = ["🥇", "🥈", "🥉"]
        icon = medals[i] if i < 3 else f"{i+1}."
        
        with st.container():
            cols = st.columns([1, 3, 2, 2, 2])
            cols[0].write(f"### {icon}")
            cols[1].write(f"**{c['name']}** ({c['code']})")
            cols[2].write(f"评分：**{c['score']}** 分")
            cols[3].write(f"{c['direction']} (置信度{c['confidence']}%)")
            cols[4].write(f"{c['boards']}连板 · {c['trend_signal']}")
    
    # 最优建议
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

# ============================================================
# 页脚
# ============================================================
st.divider()
st.caption("⚠️ 以上分析仅供研究参考，不构成投资建议。市场有风险，投资需谨慎。")