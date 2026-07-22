"""
页面5：持仓分析 — 可增删改保存 + 基本面 + K线 + 技术指标 + 预测 + 止盈止损 + 仓位
"""

import streamlit as st
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config as cfg
from utils.helpers import fmt_cn, fmt_pct
import data_fetcher as df_
import data_manager as dm 
import analyzer as anl
import visualizer as viz
import pandas as pd
import numpy as np

st.set_page_config(page_title="持仓分析", page_icon="💼", layout="wide")

# ============================================================
# 持仓管理（session_state + 本地json持久化）
# ============================================================

PORTFOLIO_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "portfolio.json")

def load_portfolio() -> dict:
    """加载持仓：优先本地json → config.py"""
    try:
        if os.path.exists(PORTFOLIO_FILE):
            with open(PORTFOLIO_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return dict(cfg.PORTFOLIO)

def save_portfolio(data: dict):
    """保存持仓到本地json"""
    os.makedirs(os.path.dirname(PORTFOLIO_FILE), exist_ok=True)
    with open(PORTFOLIO_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def _add_from_dropdown():
    """下拉框选中回调：自动加入持仓"""
    sel = st.session_state.get("ms", "")
    if sel and "—" in sel:
        c, n = sel.split("—")[0].strip(), sel.split("—")[1].strip()
        st.session_state.portfolio[c] = n
        st.session_state.ms = ""

# 初始化session_state
if "portfolio" not in st.session_state:
    st.session_state.portfolio = load_portfolio()

st.title("💼 持仓股深度分析")
st.caption(f"数据更新时间：{pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}")

# 预加载股票列表（来自本地CSV，一键下载时已保存。首次使用点侧边栏下载）
STOCK_LIST_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "stock_list.csv")
stock_list = None
if os.path.exists(STOCK_LIST_FILE):
    stock_list = pd.read_csv(STOCK_LIST_FILE, dtype={"code": str, "name": str})

# ============================================================
# 持仓管理区
# ============================================================
# 搜索 + 操作栏
c1, c2, c3 = st.columns([5, 1, 1])
with c1:
    search = st.text_input("🔍 添加持仓（输代码或名称，点结果直接加入）",
                           placeholder="如 茅台 / 600519",
                           key="stock_search")
with c2:
    st.write("")
    if st.button("💾 保存", use_container_width=True, type="primary"):
        save_portfolio(st.session_state.portfolio)
        st.session_state._just_saved = True
        st.rerun()
with c3:
    st.write("")
    if st.session_state.get("_just_saved") and st.button("🔄 重新分析", use_container_width=True):
        st.session_state._just_saved = False
        st.cache_data.clear()
        st.rerun()

# 搜索结果
if search and len(search) >= 1 and stock_list is not None and not stock_list.empty:
    mask = stock_list["code"].str.contains(search, na=False) | stock_list["name"].str.contains(search, na=False)
    matches = stock_list[mask].head(10)
    if not matches.empty:
        options = [f"{r['code']} — {r['name']}" for _, r in matches.iterrows()]
        sel = st.selectbox("匹配结果", options, key="ms")
        if st.button("✅ 加入持仓", key="add_sel"):
            if sel:
                parts = sel.replace(chr(0x2014), '|').split('|')
                c, n = parts[0].strip(), parts[1].strip()
                st.session_state.portfolio[c] = n
                st.rerun()
    else:
        st.caption("无匹配")

# 当前持仓标签
if st.session_state.portfolio:
    st.markdown("**持仓列表：**")
    tags = st.columns(min(8, len(st.session_state.portfolio)))
    del_code = None
    for i, (code, name) in enumerate(list(st.session_state.portfolio.items())):
        with tags[i % 8]:
            if st.button(f"✕ {name}", key=f"tag_{code}", help=f"删除 {code}"):
                del_code = code
    if del_code:
        del st.session_state.portfolio[del_code]
        st.rerun()

st.divider()

# ============================================================
# 分析区
# ============================================================
portfolio = st.session_state.portfolio
if not portfolio:
    st.warning("请先添加上方添加持仓股")
    st.stop()

stock_names = [f"{name}({code})" for code, name in portfolio.items()]
selected = st.selectbox("选择持仓股", stock_names)
selected_code = selected.split("(")[1].rstrip(")")
selected_name = selected.split("(")[0]

# 快速切换
if len(portfolio) > 1:
    cols_tabs = st.columns(len(portfolio))
    for i, (code, name) in enumerate(portfolio.items()):
        with cols_tabs[i]:
            if st.button(f"{name}", key=f"tab_{code}", use_container_width=True,
                         type="primary" if code == selected_code else "secondary"):
                st.session_state._selected_holding = code
                st.rerun()

# ============================================================
# ⭐ 结论卡片（放在选择持仓股后面，基本面之前）
# ============================================================
with st.container():
    st.markdown("---")
    
    # 从 session_state 读取实时行情（快）
    rt = st.session_state.get("_realtime_cache", {}).get(selected_code, {})
    if not rt:
        with st.spinner("加载实时数据..."):
            rt = df_.get_stock_realtime(selected_code)
            if rt:
                if "_realtime_cache" not in st.session_state:
                    st.session_state._realtime_cache = {}
                st.session_state._realtime_cache[selected_code] = rt
    
    # 直接从 _dragon_analyzed 读取（app.py 加载时已计算好）
    cached = st.session_state.get("_dragon_analyzed", {}).get(selected_code, {})
    
    # 如果有缓存，直接用，不用重新计算
    if cached:
        pred = cached.get("pred", {})
        sr = cached.get("sr", {})
    else:
        # 没有缓存才计算（第一次加载时）
        kdf = df_.get_stock_kline(selected_code, days=120)
        pred = {}
        sr = {}
        if not kdf.empty:
            kdf = anl.calc_all_indicators(kdf)
            pred = anl.predict_next_day(kdf)
            sr = anl.calc_stop_loss_take_profit(kdf, "中等")
    
    # 从本地缓存读财务数据（快）
    fin_data = dm.load_local(f"stock_{selected_code}_fin.json")
    if not fin_data:
        fin_data = df_.get_stock_financial(selected_code)
    
    eps = fin_data.get('eps', 0) if fin_data else 0
    bps = fin_data.get('bps', 0) if fin_data else 0
    
    if rt and rt.get("price"):
        price = rt.get("price", 0)
        pct = rt.get("change_pct", 0)
        
        if price and eps and eps > 0:
            pe = price / eps
        else:
            pe = 0
        if price and bps and bps > 0:
            pb = price / bps
        else:
            pb = 0
        
        direction = pred.get("direction", "—")
        confidence = pred.get("confidence", 0)
        stop_loss = sr.get("stop_loss_tight", "—")
        take_profit = sr.get("take_profit_1", "—")
        
        fin_score = 50
        if fin_data and fin_data.get("roe"):
            roe = fin_data.get("roe", 0)
            fin_score = min(100, max(0, roe * 5 + 30))
        tech_score = 50 + pred.get("score", 0) * 10
        total_score = (fin_score + tech_score) / 2
        
        if total_score >= 70:
            risk_level = "🟢 低风险"
        elif total_score >= 50:
            risk_level = "🟡 中风险"
        else:
            risk_level = "🔴 高风险"
        
        try:
            if stop_loss != "—" and take_profit != "—":
                down_risk = (price - float(stop_loss)) / price * 100 if price > 0 else 0
                up_reward = (float(take_profit) - price) / price * 100 if price > 0 else 0
                reward_ratio = up_reward / down_risk if down_risk > 0 else 0
                reward_str = f"{reward_ratio:.1f}:1"
            else:
                reward_str = "—"
        except:
            reward_str = "—"
        
        pe_pb_str = f"{pe:.1f}/{pb:.1f}" if pe and pb and pe > 0 and pb > 0 else "—"
        
        row1_col1, row1_col2, row1_col3, row1_col4 = st.columns(4)
        row1_col1.metric("📊 当前价", f"{price:.2f}", delta=f"{pct:+.2f}%")
        row1_col2.metric("🎯 预测方向", direction, delta=f"置信度 {confidence}%")
        row1_col3.metric("📈 综合评分", f"{total_score:.0f}分")
        row1_col4.metric("🛡️ 风险", risk_level)
        
        row2_col1, row2_col2, row2_col3, row2_col4 = st.columns(4)
        row2_col1.metric("🛑 止损", f"¥{stop_loss}" if stop_loss != "—" else "—")
        row2_col2.metric("🎯 止盈", f"¥{take_profit}" if take_profit != "—" else "—")
        row2_col3.metric("⚖️ 盈亏比", reward_str)
        row2_col4.metric("📊 PE/PB", pe_pb_str)
    else:
        row1_col1, row1_col2, row1_col3, row1_col4 = st.columns(4)
        row1_col1.metric("📊 当前价", "—")
        row1_col2.metric("🎯 预测方向", "—")
        row1_col3.metric("📈 综合评分", "—")
        row1_col4.metric("🛡️ 风险", "—")
        
        row2_col1, row2_col2, row2_col3, row2_col4 = st.columns(4)
        row2_col1.metric("🛑 止损", "—")
        row2_col2.metric("🎯 止盈", "—")
        row2_col3.metric("⚖️ 盈亏比", "—")
        row2_col4.metric("📊 PE/PB", "—")
    
    st.markdown("---")
# === 基本面 ===
st.subheader("📋 基本面数据")
with st.spinner("正在获取基本面数据..."):
    fin_data = df_.get_stock_financial(selected_code)

# 从 session_state 读取实时行情
realtime = st.session_state.get("_realtime_cache", {}).get(selected_code, {})

col_f1, col_f2, col_f3, col_f4 = st.columns(4)

if realtime:
    col_f1.metric("最新价", f"{realtime.get('price', 0):.2f}",
                  delta=f"{realtime.get('change_pct', 0):+.2f}%" if realtime.get('change_pct') else None)
    col_f2.metric("总市值", fmt_cn(realtime.get('total_mv', 0)) if realtime.get('total_mv') else "—")
    col_f3.metric("动态PE", f"{realtime.get('pe', 0):.1f}" if realtime.get('pe') else "—")
    col_f4.metric("市净率PB", f"{realtime.get('pb', 0):.2f}" if realtime.get('pb') else "—")

if fin_data:
    col_a, col_b, col_c, col_d = st.columns(4)
    col_a.metric("营业总收入", fmt_cn(fin_data.get('revenue', 0)) if fin_data.get('revenue') else "—")
    col_b.metric("净利润", fmt_cn(fin_data.get('net_profit', 0)) if fin_data.get('net_profit') else "—")
    col_c.metric("ROE", f"{fin_data.get('roe', 0):.2f}%" if fin_data.get('roe') else "—")
    col_d.metric("毛利率", f"{fin_data.get('gross_margin', 0):.2f}%" if fin_data.get('gross_margin') else "—")
else:
    st.info("无法获取基本面数据（非交易日正常）")

st.divider()

# === K线分析 + 技术指标 ===
st.subheader("📈 K线分析与技术指标")
with st.spinner("正在加载K线数据..."):
    kline_df = df_.get_stock_kline(selected_code, days=120)

if kline_df.empty:
    st.error("无法获取K线数据")
    st.stop()

kline_df = anl.calc_all_indicators(kline_df)

fig_kline = viz.plot_kline_with_volume(kline_df, title=f"{selected_name}({selected_code}) K线图")
st.plotly_chart(fig_kline, use_container_width=True)

st.subheader("🔍 技术指标")
indicator_tab = st.radio("选择指标", ["MACD", "KDJ", "RSI", "BOLL"], horizontal=True)
if indicator_tab == "MACD":
    st.plotly_chart(viz.plot_macd(kline_df), use_container_width=True)
elif indicator_tab == "KDJ":
    st.plotly_chart(viz.plot_kdj(kline_df), use_container_width=True)
elif indicator_tab == "RSI":
    st.plotly_chart(viz.plot_rsi(kline_df), use_container_width=True)
else:
    st.plotly_chart(viz.plot_boll(kline_df), use_container_width=True)

trend = anl.classify_trend(kline_df)
cols_t = st.columns(4)
cols_t[0].info(f"**短期**\n{trend.get('short_signal', '—')}")
cols_t[1].info(f"**中期**\n{trend.get('mid_signal', '—')}")
cols_t[2].info(f"**MACD**\n{trend.get('macd_signal', '—')}")

patterns = anl.detect_patterns(kline_df)
if patterns:
    cols_t[3].warning(f"**K线形态**\n" + "\n".join(patterns))
else:
    cols_t[3].info("**K线形态**\n无明显形态")

st.divider()

# === 明日预测 ===
st.subheader("🔮 明日预测")
prediction = anl.predict_next_day(kline_df)

col_p1, col_p2, col_p3 = st.columns(3)
col_p1.metric("预测方向", prediction.get("direction", "—"))
col_p2.metric("置信度", f"{prediction.get('confidence', 0)}%")
col_p3.metric("波动区间", prediction.get("range", "—"))

fig_pred = viz.plot_prediction_range(kline_df, prediction)
st.plotly_chart(fig_pred, use_container_width=True)

st.info(f"**综合评分：{prediction.get('score', 0)}分**")
if prediction.get("reasons"):
    st.write("**判断依据：**")
    for r in prediction["reasons"]:
        st.caption(f"  • {r}")

# === 止盈止损 + 仓位 ===
st.divider()
st.subheader("🎯 止盈止损 & 仓位建议")

risk_tolerance = st.select_slider("风险偏好", ["保守", "中等", "激进"], value="中等")
sl_tp = anl.calc_stop_loss_take_profit(kline_df, risk_tolerance)

if sl_tp:
    col_stop, col_take = st.columns(2)
    with col_stop:
        st.error(f"**🛑 止损位（严格）**：¥{sl_tp.get('stop_loss_tight', '—')}")
        st.warning(f"**🛑 止损位（宽松）**：¥{sl_tp.get('stop_loss_loose', '—')}")
    with col_take:
        st.success(f"**🎯 止盈位 1**：¥{sl_tp.get('take_profit_1', '—')}")
        st.success(f"**🎯 止盈位 2**：¥{sl_tp.get('take_profit_2', '—')}")
        st.success(f"**🎯 止盈位 3**：¥{sl_tp.get('take_profit_3', '—')}")

    st.metric("💼 建议仓位", sl_tp.get("suggested_position", "—"))
    st.caption(f"ATR(14)：{sl_tp.get('atr', 0)} | 风险偏好：{sl_tp.get('risk_tolerance', '—')}")

# === 综合评分 ===
st.divider()
st.subheader("⭐ 综合评分")

score_components = {}
if fin_data:
    roe = fin_data.get("roe", 0) or 0
    score_components["基本面"] = min(100, max(0, roe * 5 + 30))
else:
    score_components["基本面"] = 50

score_components["技术面"] = max(0, min(100, 50 + prediction.get("score", 0) * 10))

flow = df_.get_stock_fund_flow(selected_code)
if flow and flow.get("main_net_inflow"):
    main = flow.get("main_net_inflow", 0) or 0
    score_components["资金面"] = max(0, min(100, 50 + (1 if main > 0 else -1) * 20))
else:
    score_components["资金面"] = 50

trend_score = 0
if "多头" in trend.get("short_trend", ""):
    trend_score += 30
elif "空头" in trend.get("short_trend", ""):
    trend_score -= 20
if "多头" in trend.get("mid_trend", ""):
    trend_score += 20
score_components["趋势面"] = max(0, min(100, 50 + trend_score))

total_score = sum(score_components.values()) / len(score_components)

for k, v in score_components.items():
    st.write(f"**{k}**：{v:.0f}分")
    st.progress(v / 100)

fig_gauge = viz.plot_score_gauge(total_score, title=f"{selected_name} 综合评分")
st.plotly_chart(fig_gauge, use_container_width=True)