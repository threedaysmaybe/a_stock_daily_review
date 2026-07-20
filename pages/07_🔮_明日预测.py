"""
页面7：明日预测 — 大盘+板块+持仓综合预判
"""

import streamlit as st
import json
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config as cfg
from utils.formatters import fmt_dataframe
try:
    with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "portfolio.json"), "r", encoding="utf-8") as _pf:
        _local_pf = json.load(_pf)
except Exception:
    _local_pf = dict(cfg.PORTFOLIO)
import data_fetcher as df_
import analyzer as anl
import visualizer as viz
import pandas as pd
import numpy as np

st.set_page_config(page_title="明日预测", page_icon="🔮", layout="wide")

st.title("🔮 明日综合预测")
st.caption(f"数据更新时间：{pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}")

# ============================================================
# 1. 大盘预测
# ============================================================
st.header("📊 大盘明日预判")

index_predictions = {}
with st.spinner("正在分析大盘指数..."):
    for name, code in cfg.INDICES.items():
        df = df_.get_index_kline(code)
        if not df.empty:
            df = anl.calc_all_indicators(df)
            pred = anl.predict_next_day(df)
            trend = anl.classify_trend(df)
            index_predictions[name] = {"prediction": pred, "trend": trend}

# 显示预测
if index_predictions:
    cols = st.columns(len(index_predictions))
    for i, (name, data) in enumerate(index_predictions.items()):
        pred = data["prediction"]
        trend = data["trend"]
        with cols[i]:
            st.subheader(name)
            st.metric("方向", pred.get("direction", "—"))
            st.caption(f"置信度：{pred.get('confidence', 0)}%")
            st.caption(f"波动区间：{pred.get('range', '—')}")
            st.caption(f"MACD：{trend.get('macd_signal', '—')}")

# 综合大盘判断
bullish = sum(1 for d in index_predictions.values()
              if "看涨" in d["prediction"].get("direction", "") or "偏强" in d["prediction"].get("direction", ""))
bearish = sum(1 for d in index_predictions.values()
              if "看跌" in d["prediction"].get("direction", "") or "偏弱" in d["prediction"].get("direction", ""))

st.divider()
if bullish > bearish:
    st.success(f"🎯 **大盘综合判断：偏多**（{bullish}/{len(index_predictions)}个指数看涨)")
elif bearish > bullish:
    st.error(f"🎯 **大盘综合判断：偏空**（{bearish}/{len(index_predictions)}个指数看跌)")
else:
    st.info(f"🎯 **大盘综合判断：震荡**（多空均衡）")

# ============================================================
# 2. 板块预测
# ============================================================
st.header("🔥 板块明日预判")

with st.spinner("正在分析板块走势..."):
    sector_df = df_.get_sector_spot()

if not sector_df.empty:
    # Top5 和 Bottom5
    top5 = sector_df.head(5)
    bottom5 = sector_df.tail(5)

    col_t, col_b = st.columns(2)
    with col_t:
        st.subheader("🟢 强势板块（可能延续）")
        for _, row in top5.iterrows():
            name = row.get("sector_name", "")
            pct = row.get("change_pct", 0)
            # 简化的延续判断
            if pct > 3:
                note = "⚠️ 短期过热，注意回调"
            elif pct > 1:
                note = "趋势延续，可关注"
            else:
                note = "温和上涨"
            st.write(f"🔥 **{name}**：{pct:+.2f}% — {note}")

    with col_b:
        st.subheader("🔴 弱势板块（可能反弹或继续下跌）")
        for _, row in bottom5.iterrows():
            name = row.get("sector_name", "")
            pct = row.get("change_pct", 0)
            if pct < -3:
                note = "💡 超跌，可能有反弹机会"
            elif pct < -1:
                note = "弱势延续，观望"
            else:
                note = "小幅调整"
            st.write(f"📉 **{name}**：{pct:+.2f}% — {note}")

# ============================================================
# 3. 持仓股预测汇总
# ============================================================
st.header("💼 持仓股明日预测")

holdings_pred = []
for code, name in _local_pf.items():
    with st.spinner(f"正在分析 {name}({code})..."):
        df = df_.get_stock_kline(code)
        if df.empty:
            continue
        df = anl.calc_all_indicators(df)
        pred = anl.predict_next_day(df)
        sl_tp = anl.calc_stop_loss_take_profit(df)

        realtime = df_.get_stock_realtime(code)

        holdings_pred.append({
            "code": code,
            "name": name,
            "price": realtime.get("price", df["close"].iloc[-1]) if realtime else df["close"].iloc[-1],
            "change_pct": realtime.get("change_pct", 0) if realtime else 0,
            "direction": pred.get("direction", "—"),
            "confidence": pred.get("confidence", 0),
            "range": pred.get("range", "—"),
            "score": pred.get("score", 0),
        })

if holdings_pred:
    # 表格
    pred_df = pd.DataFrame(holdings_pred)
    st.dataframe(fmt_dataframe(pred_df), hide_index=True, use_container_width=True)

    # 评分排行
    pred_df_sorted = pred_df.sort_values("score", ascending=False)
    st.subheader("📈 持仓股评分排行")
    for _, row in pred_df_sorted.iterrows():
        score = row["score"]
        bar_len = int(max(0, min(100, score + 5)) * 0.5)
        bar_color = "#DC143C" if score > 3 else "#FFD700" if score > 0 else "#228B22"
        st.write(f"**{row['name']}**({row['code']}) — {row['direction']} | 评分：{score:.1f}")
        st.markdown(f'<div style="background:{bar_color};height:6px;width:{bar_len}%;border-radius:3px;"></div>',
                    unsafe_allow_html=True)

    # 最佳/最差
    best = pred_df_sorted.iloc[0]
    worst = pred_df_sorted.iloc[-1]
    col_best, col_worst = st.columns(2)
    col_best.success(f"**最看好**：{best['name']} | {best['direction']} | 评分：{best['score']}")
    col_worst.error(f"**最谨慎**：{worst['name']} | {worst['direction']} | 评分：{worst['score']}")

# ============================================================
# 4. 综合操作建议
# ============================================================
st.divider()
st.header("📋 明日操作建议")

# 汇总各方信号
market_signal = 1 if bullish > bearish else (-1 if bearish > bullish else 0)
hold_avg_score = np.mean([h["score"] for h in holdings_pred]) if holdings_pred else 0

st.info(f"""
### 📌 综合研判

**大盘信号：** {'🟢 偏多' if market_signal > 0 else '🔴 偏空' if market_signal < 0 else '🟡 震荡'}

**持仓平均评分：** {hold_avg_score:.1f} 分

**建议：**
- {"✅ 大盘偏多，可适当提升仓位，" + ("关注强势板块轮动机会" if hold_avg_score > 0 else "但持仓评分偏低，注意精选标的") if market_signal > 0 else ""}
- {"⚠️ 大盘偏空，控制仓位，减仓弱势持仓" if market_signal < 0 else ""}
- {"🔄 大盘震荡，高抛低吸，控制仓位在50%左右" if market_signal == 0 else ""}

> ⚠️ 以上均为AI基于技术指标的预判，不构成投资建议。市场有风险，投资需谨慎。
> 所有数据来源于akshare/公开接口，分析截止时间为数据获取时间。
""")
