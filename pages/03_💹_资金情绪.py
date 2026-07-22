"""
页面3：资金情绪 — 主力/机构/散户资金流向 + 市场情绪
"""

import streamlit as st
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_pf = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "portfolio.json")
import json as _json
try:
    with open(_pf, "r", encoding="utf-8") as _f:
        _portfolio_data = _json.load(_f)
except Exception:
    import config as _cfg
    _portfolio_data = dict(_cfg.PORTFOLIO)

import config as cfg
from utils.formatters import fmt_dataframe
from utils.helpers import fmt_cn
import data_fetcher as df_
import visualizer as viz
import pandas as pd

st.set_page_config(page_title="资金情绪", page_icon="💹", layout="wide")

st.title("💹 资金情绪分析")
st.caption(f"交易日：{(st.session_state.get('_trading_day') or pd.Timestamp.now()).strftime('%Y-%m-%d')}")

# ============================================================
# 从 session_state 读取市场情绪（首页已加载）
# ============================================================
sentiment = st.session_state.get("_sentiment")
if sentiment is None or not sentiment:
    # 如果首页没加载过，自己加载
    with st.spinner("正在分析市场情绪..."):
        sentiment = df_.get_market_sentiment()
        st.session_state["_sentiment"] = sentiment

if sentiment:
    st.subheader("🎯 市场情绪仪表盘")

    cols = st.columns(6)
    cols[0].metric("上涨家数", sentiment.get("up_count", 0))
    cols[1].metric("下跌家数", sentiment.get("down_count", 0))
    cols[2].metric("上涨占比", f"{sentiment.get('up_ratio', 0):.1f}%")
    cols[3].metric("涨停家数", sentiment.get("zt_count", 0))
    cols[4].metric("炸板率", f"{sentiment.get('zha_rate', 0):.1f}%")
    cols[5].metric("两市成交额", f"{sentiment.get('total_amount', 0):.0f}亿" if sentiment.get("total_amount") else "—")

    # 情绪判断
    sent_label = sentiment.get("sentiment", "未知")
    sent_colors = {
        "🔥 极度亢奋": "#DC143C",
        "😊 偏暖": "#FF6B6B",
        "😐 中性": "#FFD700",
        "😟 偏冷": "#66CDAA",
        "❄️ 冰点": "#228B22",
        "💀 恐慌": "#006400",
    }
    color = sent_colors.get(sent_label, "#888")
    st.markdown(f"### <span style='color:{color}'>{sent_label}</span>", unsafe_allow_html=True)

    # 涨跌比进度条
    up_ratio = sentiment.get("up_ratio", 50) / 100
    st.progress(up_ratio, text=f"上涨占比：{up_ratio*100:.1f}%")

st.divider()

# 全市场资金流向
st.subheader("📊 全市场资金流向")
with st.spinner("正在获取资金流向数据..."):
    fund_df = df_.get_market_fund_flow()

if not fund_df.empty:
    st.dataframe(fmt_dataframe(fund_df), hide_index=True, use_container_width=True)
else:
    st.info("暂无全市场资金流向数据")

# ============================================================
# 个股资金流向（持仓股）- 从 session_state 读取实时行情
# ============================================================
st.subheader("🎯 持仓股资金流向")
st.caption("检测主力/机构/散户在持仓股上的资金动向")

for code, name in _portfolio_data.items():
    # 从 session_state 读取实时行情（首页已加载）
    rt = st.session_state.get("_realtime_cache", {}).get(code, {})
    
    # 显示资金流向（需要单独获取，因为资金流向数据不是实时行情）
    with st.spinner(f"正在获取 {name}({code}) 资金数据..."):
        flow = df_.get_stock_fund_flow(code)

    if flow:
        with st.expander(f"{name} ({code}) — 资金流向", expanded=(code == list(_portfolio_data.keys())[0])):
            cols = st.columns(5)
            main_inflow = flow.get("main_net_inflow", 0) or 0
            cols[0].metric("主力净流入(万)", fmt_cn(main_inflow),
                          delta="流入" if main_inflow > 0 else "流出", delta_color="inverse")
            cols[1].metric("超大单(万)", fmt_cn(flow.get('super_large_net', 0) or 0))
            cols[2].metric("大单(万)", fmt_cn(flow.get('large_net', 0) or 0))
            cols[3].metric("中单(万)", fmt_cn(flow.get('mid_net', 0) or 0))
            cols[4].metric("小单(万)", fmt_cn(flow.get('small_net', 0) or 0))

            # 饼图
            fig_pie = viz.plot_fund_flow_pie(flow, title=f"{name} 资金流向分布")
            st.plotly_chart(fig_pie, use_container_width=True)
    else:
        st.caption(f"{name}({code})：暂无法获取资金数据")

# 操作建议
st.subheader("💡 资金面解读")
st.info("""
**判断逻辑：**
- 🟢 **主力流入 + 散户流出** = 机构吸筹，可能后续拉升
- 🔴 **主力流出 + 散户流入** = 主力出货，散户接盘，谨慎
- 🟡 **主力/散户同向** = 趋势延续信号，顺势而为
- ⚪ **缩量横盘** = 多空观望，等待方向选择
""")