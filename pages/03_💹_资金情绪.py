"""
页面3：资金情绪 — 主力/机构/散户资金流向 + 市场情绪
"""

import streamlit as st
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config as cfg
from utils.formatters import fmt_dataframe, render_merged_table
from utils.helpers import fmt_cn
from utils.ui import inject_css, conclusion
import data_fetcher as df_
import visualizer as viz
import pandas as pd
import json
from streamlit_sortables import sort_items

st.set_page_config(page_title="资金情绪", page_icon="💹", layout="wide")
inject_css()


def _load_hot_order() -> list:
    """加载已保存的游资顺序。"""
    try:
        p = os.path.join(os.environ.get("SC_DATA_ROOT") or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"), "hot_money_order.json")
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save_hot_order(order: list):
    """保存游资顺序。"""
    try:
        p = os.path.join(os.environ.get("SC_DATA_ROOT") or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"), "hot_money_order.json")
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(order, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

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

if not sentiment:
    st.warning("市场情绪数据暂不可用（可能休市或数据源异常）")

if sentiment:
    st.subheader("🎯 市场情绪仪表盘")

    cols = st.columns(6)
    cols[0].metric("上涨家数", sentiment.get("up_count", 0))
    cols[1].metric("下跌家数", sentiment.get("down_count", 0))
    cols[2].metric("上涨占比", f"{sentiment.get('up_ratio', 0):.1f}%")
    cols[3].metric("涨停家数", sentiment.get("zt_count", 0))
    _zha = sentiment.get("zha_rate")
    cols[4].metric("炸板率", f"{_zha:.1f}%" if _zha else "—（无数据）")
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

    # 结论卡片
    _up = sentiment.get("up_count", 0)
    _down = sentiment.get("down_count", 0)
    _ratio = sentiment.get("up_ratio", 0) or 0
    _tone = "neutral"
    if _ratio > 65:
        _tone = "bull"
    elif _ratio < 40:
        _tone = "bear"
    conclusion(f"情绪结论：{sent_label}",
               f"上涨 <b>{_up}</b> / 下跌 <b>{_down}</b>（占比 {_ratio:.1f}%），"
               f"涨停 <b>{sentiment.get('zt_count', 0)}</b> 家，成交 <b>{sentiment.get('total_amount', 0):.0f}</b> 亿。",
               tone=_tone)

    # 涨跌比进度条
    up_ratio = sentiment.get("up_ratio", 50) / 100
    st.progress(up_ratio, text=f"上涨占比：{up_ratio*100:.1f}%")

    # 成交额历史分位分析
    _amt = sentiment.get("total_amount", 0) or 0
    try:
        _idx = df_.get_index_kline("000001")
        if _idx is not None and not _idx.empty and "amount" in _idx.columns and _idx["amount"].notna().any():
            _amts = _idx["amount"].dropna()
            _cur = _amts.iloc[-1]
            _pct_rank = int((_amts <= _cur).sum() / len(_amts) * 100)
            _min_a = _amts.min()
            _max_a = _amts.max()
            _avg_a = _amts.mean()
            if _pct_rank <= 20:
                _amt_verdict = "处于历史低位区，交投清淡，可能接近阶段底部（但也可能是阴跌无量）。"
            elif _pct_rank >= 80:
                _amt_verdict = "处于历史高位区，交投活跃，注意情绪过热后的降温风险。"
            else:
                _amt_verdict = "处于历史中位区，量能正常。"
            st.info(
                f"**成交额分位**：上证今日成交 <b>{_cur:.0f}</b> 亿，"
                f"在近 {len(_amts)} 日里排<b>前 {_pct_rank}%</b> 分位（区间 {_min_a:.0f} ~ {_max_a:.0f} 亿，均值 {_avg_a:.0f} 亿）。"
                f"{_amt_verdict}"
            )
    except Exception:  # noqa: BLE001
        pass

st.divider()

# 全市场资金流向
st.subheader("📊 全市场资金流向")
with st.spinner("正在获取资金流向数据..."):
    fund_df = df_.get_market_fund_flow()

if not fund_df.empty:
    _fig_fund = viz.plot_fund_flow_trend(fund_df)
    if _fig_fund is not None:
        st.plotly_chart(_fig_fund, use_container_width=True)
    st.dataframe(fmt_dataframe(fund_df), hide_index=True, use_container_width=True)
else:
    st.info("暂无全市场资金流向数据")

# ============================================================
# 北向资金（沪深港通，Tushare）
# ============================================================
st.subheader("🌏 北向资金（沪深港通）")
with st.spinner("正在获取北向资金..."):
    nb_df = df_.get_northbound(days=10)

if nb_df is not None and not nb_df.empty:
    nb_df = nb_df.sort_values("trade_date")
    # 转数值（Tushare 返回字符串类型，且单位百万元 → 亿元）
    nb_df["north_money"] = pd.to_numeric(nb_df["north_money"], errors="coerce") / 100
    nb_df["south_money"] = pd.to_numeric(nb_df["south_money"], errors="coerce") / 100
    nb_df["当日净流入"] = nb_df["north_money"].diff()
    latest = nb_df.iloc[-1]
    net = latest.get("当日净流入", 0)
    net = 0 if pd.isna(net) else net
    north = latest.get("north_money", 0)
    north = 0 if pd.isna(north) else north
    south = latest.get("south_money", 0)
    south = 0 if pd.isna(south) else south
    cols = st.columns(3)
    cols[0].metric("当日北向净流入(亿)", f"{net:.2f}",
                   delta="流入" if net > 0 else "流出", delta_color="inverse")
    cols[1].metric("北向累计(亿)", f"{north:.2f}")
    cols[2].metric("南向累计(亿)", f"{south:.2f}")
    _nb_show = nb_df.tail(10)[["trade_date", "当日净流入", "north_money", "south_money"]].copy()
    _nb_show.columns = ["日期", "当日净流入(亿)", "北向累计(亿)", "南向累计(亿)"]
    _fig_nb = viz.plot_northbound_trend(nb_df)
    if _fig_nb is not None:
        st.plotly_chart(_fig_nb, use_container_width=True)
    st.dataframe(fmt_dataframe(_nb_show), hide_index=True, use_container_width=True)
else:
    st.info("暂无北向资金数据")

# （持仓股资金流向已删除：东财个股资金流接口不稳定，且与上方全市场资金流重复）

# 操作建议
st.subheader("💡 资金面解读")
st.info("""
**判断逻辑：**
- 🟢 **主力流入 + 散户流出** = 机构吸筹，可能后续拉升
- 🔴 **主力流出 + 散户流入** = 主力出货，散户接盘，谨慎
- 🟡 **主力/散户同向** = 趋势延续信号，顺势而为
- ⚪ **缩量横盘** = 多空观望，等待方向选择
""")

# ============================================================
# 游资龙虎榜追踪（原 06 页面合并进来）
# ============================================================
st.divider()
st.subheader("🕵️ 游资龙虎榜追踪")

days_options = [5, 10, 15, 20, 25, 30]
selected_days = st.selectbox("统计天数", options=days_options, index=1)

with st.spinner(f"正在获取龙虎榜数据（近{selected_days}日）..."):
    hot_df = df_.get_hot_money_trades(days=selected_days)

if hot_df.empty:
    st.warning(f"近{selected_days}日未发现目标游资交易记录，或数据源暂时不可用。")
    st.info("可能原因：近期非交易日 / 目标游资未上榜 / 数据源延迟。请在工作日收盘后查看。")
else:
    st.subheader(f"📊 游资近{selected_days}日买卖汇总")
    fig_summary = viz.plot_hot_money_summary(hot_df)
    st.plotly_chart(fig_summary, use_container_width=True)

    available_hot = hot_df["hot_money_name"].unique().tolist()
    # 按已保存顺序重排（新游资排后面）
    _saved = _load_hot_order()
    if _saved:
        available_hot = [n for n in _saved if n in available_hot] + [n for n in available_hot if n not in _saved]
    # 拖拽排序
    st.caption("👇 拖拽调整游资顺序（影响下方「筛选游资」和「操作风格分析」的顺序）")
    ordered_hot = sort_items(available_hot, header="", key="hot_money_sort")
    if ordered_hot and ordered_hot != available_hot:
        _save_hot_order(ordered_hot)
    selected_hot = st.multiselect("筛选游资", ordered_hot, default=ordered_hot[:5])
    filtered_df = hot_df[hot_df["hot_money_name"].isin(selected_hot)] if selected_hot else hot_df

    # 游资顺序映射（拖拽后的顺序，用于排序）
    _order = {name: i for i, name in enumerate(ordered_hot)}

    # 同一天同一只票合并成一条
    _daily = df_.merge_hot_money_daily(filtered_df)
    st.subheader("📋 游资交易明细（同天同票已合并，日期/游资已合并单元格）")
    if not _daily.empty:
        _d = _daily.copy()
        _d["_ord"] = _d["hot_money_name"].map(_order).fillna(9999)
        _d = _d.sort_values(["trade_date", "_ord"], ascending=[False, True]).reset_index(drop=True)
        _show = _d[["trade_date", "hot_money_name", "股票名称", "股票代码", "买入金额", "卖出金额", "净额"]]
        st.markdown(
            render_merged_table(_show, merge_cols=["trade_date", "hot_money_name"], color_cols=["净额"]),
            unsafe_allow_html=True,
        )

    # 游资持仓与清仓（推算）
    _pos = df_.get_hot_money_positions(filtered_df)
    if not _pos.empty:
        _holding = _pos[_pos["状态"] == "持仓中"]
        _cleared = _pos[_pos["状态"].isin(["已清仓", "疑似清仓"])]

        st.subheader("💼 游资当前持仓")
        if not _holding.empty:
            _h = _holding.copy()
            _h["首次买入"] = _h["首次买入"].astype(str).str[4:6] + "-" + _h["首次买入"].astype(str).str[6:8]
            _h["最近操作"] = _h["最近操作"].astype(str).str[4:6] + "-" + _h["最近操作"].astype(str).str[6:8]
            _h["_ord"] = _h["hot_money_name"].map(_order).fillna(9999)
            _h = _h.sort_values("_ord").reset_index(drop=True)
            st.markdown(
                render_merged_table(
                    _h[["hot_money_name", "股票名称", "股票代码", "净持仓(万)", "首次买入", "最近操作", "持仓天数", "期间涨幅%"]],
                    merge_cols=["hot_money_name"], color_cols=["净持仓(万)"],
                ),
                unsafe_allow_html=True,
            )
        else:
            st.caption("当前无游资持仓（均在近 N 日内清仓）。")

        st.subheader("🚪 最近清仓")
        if not _cleared.empty:
            _c = _cleared.copy()
            _c["清仓日"] = _c["最近操作"].astype(str).str[4:6] + "-" + _c["最近操作"].astype(str).str[6:8]
            _c["首次买入"] = _c["首次买入"].astype(str).str[4:6] + "-" + _c["首次买入"].astype(str).str[6:8]
            _c["_ord"] = _c["hot_money_name"].map(_order).fillna(9999)
            _c = _c.sort_values("_ord").reset_index(drop=True)
            st.markdown(
                render_merged_table(
                    _c[["hot_money_name", "股票名称", "股票代码", "状态", "清仓日", "持仓天数", "期间涨幅%"]],
                    merge_cols=["hot_money_name"],
                ),
                unsafe_allow_html=True,
            )
        else:
            st.caption("近 N 日内无清仓记录。")

        st.caption("⚠️ 持仓/清仓是推算：龙虎榜只披露买卖前5营业部，小额单抓不到。"
                   "卖出≥买入=已清仓；剩余<买入5%=疑似清仓。"
                   "净持仓单位=万元；期间涨幅=最近收盘/首次买入日收盘-1（价格涨幅，非盈亏）。"
                   "持仓天数0=当日买卖(T+0)，或买入发生在统计窗口外、只看到卖出。")

    st.subheader("🔍 游资操作风格分析")
    for name in selected_hot if selected_hot else available_hot[:5]:
        name_df = hot_df[hot_df["hot_money_name"] == name]
        _name_daily = df_.merge_hot_money_daily(name_df)
        with st.expander(f"🕵️ {name} — 近{selected_days}日操作（{len(_name_daily)}笔）",
                         expanded=(name == (selected_hot[0] if selected_hot else available_hot[0]))):
            total_buy = name_df["买入金额"].sum() if "买入金额" in name_df.columns else 0
            total_sell = name_df["卖出金额"].sum() if "卖出金额" in name_df.columns else 0
            net = total_buy - total_sell
            cols = st.columns(4)
            cols[0].metric("操作笔数", len(_name_daily))
            cols[1].metric("累计买入", fmt_cn(total_buy) if total_buy else "0")
            cols[2].metric("累计卖出", fmt_cn(total_sell) if total_sell else "0")
            cols[3].metric("净买入", fmt_cn(net) if net else "0",
                           delta="净额" if net > 0 else "净卖出" if net < 0 else "平衡",
                           delta_color="inverse")
            st.dataframe(
                fmt_dataframe(_name_daily[["trade_date", "股票名称", "股票代码", "买入金额", "卖出金额", "净额"]]),
                hide_index=True, use_container_width=True,
            )
            stock_list = [str(x) for x in name_df["股票名称"].unique() if str(x) not in ("", "nan", "None", "<NA>")]
            st.caption(f"**操作标的：**{', '.join(stock_list)}" if stock_list else "**操作标的：**无")
            if net > 10000:
                st.success("🟢 整体偏激进买入，看好后市")
            elif net < -10000:
                st.error("🔴 整体偏卖出，注意风险")
            else:
                st.info("🟡 买卖平衡，短线调仓")

    st.divider()
    st.subheader("🔮 游资明日操作预测")
    st.caption("基于游资近5日操作方向、仓位变化和标的特征推断，不构成投资建议。")
    for name in selected_hot if selected_hot else available_hot[:6]:
        name_df = hot_df[hot_df["hot_money_name"] == name]
        total_buy = name_df["买入金额"].sum() if "买入金额" in name_df.columns else 0
        total_sell = name_df["卖出金额"].sum() if "卖出金额" in name_df.columns else 0
        net = total_buy - total_sell
        days_active = name_df["trade_date"].nunique()
        if days_active >= 3 and net > 5000:
            pred = "📈 活跃做多，预计继续加仓热门题材"
        elif net > 0:
            pred = "📈 偏多，可能逢低加仓"
        elif net < 0 and days_active >= 2:
            pred = "📉 减仓为主，明日可能继续出货"
        elif days_active == 0:
            pred = "😴 近5日无操作，可能在观望"
        else:
            pred = "🔄 短线调仓，操作方向不明确"
        st.write(f"**{name}**：{pred}")