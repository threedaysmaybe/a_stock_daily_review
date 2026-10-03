"""
页面1：大盘走势 — 三大指数K线 + 量价分析 + 趋势指标
"""

import streamlit as st
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config as cfg
from utils.formatters import fmt_dataframe
from utils.ui import inject_css, conclusion
import data_fetcher as df_
import analyzer as anl
import visualizer as viz
import pandas as pd
import streamlit.components.v1 as components

st.set_page_config(page_title="大盘走势", page_icon="📊", layout="wide")
inject_css()

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

# === 结论前置：趋势 + 支撑压力 + 量价 ===
trend = anl.classify_trend(df)

# 核心结论卡片
_short = trend.get("short_trend", "—")
_mid = trend.get("mid_trend", "—")
_macd = trend.get("macd_signal", "—")
_tone = "neutral"
if "多头" in _short or "上涨" in _short or "向上" in _short:
    _tone = "bull"
elif "空头" in _short or "下跌" in _short or "向下" in _short:
    _tone = "bear"
conclusion(f"趋势研判：短期<b>{_short}</b>",
           f"中期 {_mid} ｜ MACD {_macd}",
           tone=_tone)

st.subheader("📋 趋势研判")
cols_trend = st.columns(3)
with cols_trend[0]:
    st.info(f"**短期趋势**\n\n{trend.get('short_trend', '—')}\n\n{trend.get('short_signal', '')}")
with cols_trend[1]:
    st.info(f"**中期趋势**\n\n{trend.get('mid_trend', '—')}\n\n{trend.get('mid_signal', '')}")
with cols_trend[2]:
    st.info(f"**MACD信号**\n\n{trend.get('macd_signal', '—')}")

sr = trend.get("sr_levels", {})
if sr:
    st.subheader("📍 关键支撑/压力位")
    st.caption("**怎么算的（3个支撑 + 3个压力）**：")
    st.caption("① **均线**：MA20、MA60 在价格**下方** → 回踩时是**支撑**（托底）；在**上方** → 反弹时是**压力**（受阻）。")
    st.caption("② **波段高低点**：近120日里，每个「左右两边都比它高」的低点是**波谷=支撑**；「左右两边都比它低」的高点是**波峰=压力**。")
    st.caption("③ 把①和②汇总，**离当前价最近的排前面**，各取最近 3 个。")
    col_s, col_r = st.columns(2)
    with col_s:
        st.write("**支撑位（越靠上越近）**")
        for s in sr.get("supports", []):
            st.write(f"🟢 {s['label']} ¥{s['price']} ｜ {s['type']}")
    with col_r:
        st.write("**压力位（越靠下越近）**")
        for r in sr.get("resistances", []):
            st.write(f"🔴 {r['label']} ¥{r['price']} ｜ {r['type']}")

st.subheader("📊 量价关系")
if not df.empty and len(df) >= 5:
    recent5 = df.tail(5)
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

    # 量价解读
    _chg5 = recent5["close"].iloc[-1] / recent5["close"].iloc[0] - 1
    if vol_ratio > 1.2 and _chg5 > 0:
        _vj = "放量上涨：资金积极进场，趋势偏强；但需防高位放量滞涨。"
    elif vol_ratio > 1.2 and _chg5 < 0:
        _vj = "放量下跌：有恐慌抛售，短线偏弱；但急跌后常有反抽。"
    elif vol_ratio < 0.8 and _chg5 > 0:
        _vj = "缩量上涨：抛压减轻，但追涨动能不足，持续性存疑。"
    elif vol_ratio < 0.8 and _chg5 < 0:
        _vj = "缩量下跌：抛压衰竭，可能接近阶段底部。"
    else:
        _vj = "量价配合正常，趋势延续。"
    st.info(f"**量价解读**：{_vj}")
    with st.expander("💡 量价关系怎么理解（新手必看）"):
        st.markdown("""
**核心逻辑：量是价格的「燃料」，没有量支撑的涨跌都难以持续。**

- **放量上涨**：多头主动买入、真金白银进场，推动价格上涨，健康。但要小心「高位放量滞涨」——量很大却涨不动/冲高回落，往往是主力在出货。
- **放量下跌**：空头主动抛售，抛压重。急跌后常有反抽，但趋势偏空，别急着抄底。
- **缩量上涨**：分两种情况——
  - **低位**缩量上涨：筹码锁定好、惜售，健康，说明抛压小；
  - **高位**缩量上涨：追涨资金承接不足，上涨乏力，警惕见顶。
- **缩量下跌**：抛压减轻，可能是下跌尾声。但若持续阴跌无量，也可能是无人接盘的「钝刀割肉」。
- **量价背离**：价涨量缩（上涨动能不足）、价跌量增（下跌抛压加剧），都是危险信号。

**一句话**：涨要放量才扎实，跌要缩量才见底；放量滞涨/放量下跌最要警惕。
""")

st.divider()

# K线图 + 成交量（ECharts，支持缩放拖动）
st.subheader(f"📈 {selected_index} — K线图（近120日）")
# K线位置解读
if not df.empty and len(df) >= 20:
    _close = df["close"].iloc[-1]
    _ma20 = df["close"].rolling(20).mean().iloc[-1]
    _ma60 = df["close"].rolling(60).mean().iloc[-1]
    if _close > _ma20 > _ma60:
        _kpos = "价格站上 MA20/MA60，均线多头排列，中期趋势偏强。"
    elif _close < _ma20 < _ma60:
        _kpos = "价格跌破 MA20/MA60，均线空头排列，中期趋势偏弱。"
    else:
        _kpos = "价格在均线附近震荡，方向不明，需观察突破方向。"
    st.caption(f"**K线解读**：{_kpos}")
kline_html = viz.plot_kline_echarts(df, title=f"{selected_index} · 日K线图", height=500, sr_levels=sr)
components.html(kline_html, height=530)

# ============================================================
# 技术面综合研判（量价 + MACD + KDJ/RSI + 背离，串起来看）
# ============================================================
st.subheader("🧠 技术面综合研判")
_verdict = anl.technical_verdict(df)
if _verdict:
    conclusion(
        f"综合结论：<b>{_verdict['summary']}</b>",
        f"量比 {_verdict['vol_ratio']}，近5日 {_verdict['chg5']:+.1%}（信号数量对比，非评分）",
        tone=_verdict["tone"],
    )
    # 当前结论（按方向分组，用颜色卡片展示，支持换行）
    if _verdict.get("alerts"):
        _bull_a = [a["t"] for a in _verdict["alerts"] if a["d"] == "bull"]
        _bear_a = [a["t"] for a in _verdict["alerts"] if a["d"] == "bear"]
        _neu_a = [a["t"] for a in _verdict["alerts"] if a["d"] == "neutral"]
        if _bull_a and _bear_a:
            st.warning("⚠️ 信号有冲突（多方 vs 空方同时出现），需谨慎权衡")

        def _card(text, bg, border, color):
            return f'<div style="background:{bg};border-left:4px solid {border};border-radius:6px;padding:10px 12px;margin:5px 0;color:{color};font-size:13px;line-height:1.8;">{text.replace(chr(10), "<br>")}</div>'

        for _a in _bull_a:
            st.markdown(_card(_a, "#0F3D2E", "#22C55E", "#D1FAE5"), unsafe_allow_html=True)
        for _a in _bear_a:
            st.markdown(_card(_a, "#3F1D1D", "#EF4444", "#FEE2E2"), unsafe_allow_html=True)
        for _a in _neu_a:
            st.markdown(_card(_a, "#1E293B", "#94A3B8", "#E2E8F0"), unsafe_allow_html=True)
    _c1, _c2 = st.columns(2)
    with _c1:
        st.markdown(f"**🟢 多方信号（{len(_verdict['bull'])}个）**")
        for _b in _verdict["bull"] or ["无"]:
            st.caption(f"• {_b}")
    with _c2:
        st.markdown(f"**🔴 空方信号（{len(_verdict['bear'])}个）**")
        for _b in _verdict["bear"] or ["无"]:
            st.caption(f"• {_b}")
    st.markdown("**信号拆解（串起来看，不孤立）**：")
    _lines = [
        f"• **量价**：{_verdict['vol_price']}",
        f"• **趋势动能**：{_verdict['macd_state']}",
        f"• **短线情绪**：{_verdict['mood']}",
    ]
    if _verdict["divergence"]:
        _lines.append(f"• **背离警示**：{_verdict['divergence']}")
    for _l in _lines:
        st.caption(_l)
    with st.expander("💡 技术分析常见「假信号」提示（避坑）"):
        st.markdown("""
- **底背离未必见底**：量能不足时，空头只是「减少抛压」而非「多头进场」，价格企稳是假象，需放量确认。
- **顶背离可被化解**：若后续放量创新高、动能续上，顶背离失效，别急着看空。
- **金叉分位置**：零轴下方的金叉是「弱势金叉」，可信度低；零轴上方的金叉（强势金叉）才更可靠。
- **超买/超卖会钝化**：强势股可长期超买（KDJ/RSI 高位钝化），超买≠立刻卖；弱势股超卖也可能阴跌，别盲目抄底。
- **缩量上涨要看位置**：低位缩量=惜售健康；高位缩量=承接不足乏力。
- **放量滞涨是危险信号**：量很大但价格不涨或冲高回落，往往在出货。
- **假突破**：放量突破关键位后，次日缩量回落、重新跌破，突破无效。
- 以上信号仅客观罗列，不构成买卖建议。
""")
    st.divider()

# 技术指标（ECharts，支持缩放拖动）
st.subheader("🔍 技术指标详情")

indicator_tabs = st.tabs(["MACD", "KDJ", "RSI", "BOLL"])
indicator_types = ["MACD", "KDJ", "RSI", "BOLL"]
indicator_notes = {
    "MACD": [
        "**红柱** = MACD>0（DIF在DEA上方）= 多头动能",
        "**绿柱** = MACD<0（DIF在DEA下方）= 空头动能",
        "**金叉**（🟡）= DIF上穿DEA，偏多；**死叉**（⚪）= DIF下穿DEA，偏空",
        "柱体逐根变长=加速，变短=动能衰减",
    ],
    "KDJ": [
        "**金叉**（🟡）= K上穿D，短线偏多；**死叉**（⚪）= K下穿D，偏空",
        "K突破80 = 超买（追高风险）；跌破20 = 超卖（超跌，别盲目抄底）",
    ],
    "RSI": [
        "RSI>70 = 超买（红虚线）；<30 = 超卖（绿虚线）",
        "RSI在50上方偏强，下方偏弱",
    ],
    "BOLL": [
        "价格触上轨=压力，触下轨=支撑",
        "布林收口=变盘前兆，开口=趋势启动",
    ],
}


def _current_signal(df, ind_type):
    last = df.iloc[-1]
    if ind_type == "MACD" and "DIF" in last.index:
        dif, dea, macd = last["DIF"], last["DEA"], last["MACD"]
        if dif > dea:
            return f"🟢 DIF({dif:.2f}) > DEA({dea:.2f})，红柱多头动能，偏多"
        return f"🔴 DIF({dif:.2f}) < DEA({dea:.2f})，绿柱空头动能，偏空"
    if ind_type == "KDJ" and "K" in last.index:
        k, d = last["K"], last["D"]
        pos = "超买（追高风险）" if k > 80 else "超卖（超跌）" if k < 20 else "中性区"
        cross = "，金叉偏多" if k > d else "，死叉偏空"
        return f"K={k:.1f} D={d:.1f}，{pos}{cross}"
    if ind_type == "RSI" and "RSI6" in last.index:
        rsi = last["RSI6"]
        pos = "超买" if rsi > 70 else "超卖" if rsi < 30 else "中性"
        return f"RSI6={rsi:.1f}，{pos}区"
    if ind_type == "BOLL" and "BOLL_UP" in last.index:
        close, up, dn = last["close"], last["BOLL_UP"], last["BOLL_DN"]
        pos = "触及上轨（压力）" if close >= up else "触及下轨（支撑）" if close <= dn else "轨道中部"
        return f"收盘{close:.2f}，{pos}"
    return ""


for tab, ind_type in zip(indicator_tabs, indicator_types):
    with tab:
        _sig = _current_signal(df, ind_type)
        if _sig:
            st.info(f"**当前信号**：{_sig}")
        st.markdown("**怎么读**：")
        for _line in indicator_notes[ind_type]:
            st.caption(f"• {_line}")
        ind_html = viz.plot_indicator_echarts(df, ind_type, height=280)
        components.html(ind_html, height=310)
