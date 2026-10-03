"""选股决策：量化选股 / 涨停股分析 / 明日预测 三合一，统一入口。"""
import streamlit as st
import sys
import os
import json
import warnings
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
warnings.filterwarnings("ignore")

import config as cfg
import data_fetcher as df_
import data_manager as dm
import analyzer as anl
import visualizer as viz
import pandas as pd
import numpy as np
from datetime import datetime
from utils.formatters import fmt_dataframe
from utils.helpers import fmt_cn
from utils.ui import inject_css, conclusion
import streamlit.components.v1 as components

st.set_page_config(page_title="选股决策", page_icon="🎯", layout="wide")
inject_css()
st.title("🎯 选股决策")
st.caption(f"交易日：{(st.session_state.get('_trading_day') or pd.Timestamp.now()).strftime('%Y-%m-%d')} | 选股 + 涨停 + 预测，一站式决策")

tab_quant, tab_limit, tab_predict = st.tabs(["📊 量化选股", "🐉 涨停股分析", "🔮 明日预测"])


# ============================================================
# Tab 1: 量化选股（原 09 页）
# ============================================================
with tab_quant:
    from data.tushare_provider import TushareProvider
    from strategy.scoring import score_stocks

    def _filter_limit(df: pd.DataFrame) -> pd.DataFrame:
        df = df[~df["is_st"].fillna(False).astype(bool)]
        if "pct_change" in df.columns:
            pct = pd.to_numeric(df["pct_change"], errors="coerce").fillna(0)
            lim = np.where(df["code"].astype(str).str.startswith(("30", "68")), 20.0,
                           np.where(df["code"].astype(str).str.startswith(("8", "4", "9")), 30.0, 10.0))
            df = df[~((pct >= lim - 0.5))]
        return df

    @st.cache_data(ttl=3600)
    def run_pick(date_str: str):
        provider = TushareProvider({}, cfg.TUSHARE_TOKEN)
        df = provider.fetch(date_str)
        if df is None or df.empty:
            return None, None, 0
        df = _filter_limit(df)
        scored = score_stocks(df, cfg.STOCK_PICK_FACTORS, clip_q=0.01, method="zscore", min_coverage=0.5)
        top = scored.head(cfg.STOCK_PICK_TOP_N).copy()
        top.index.name = "code"
        top = top.reset_index()
        if "name" in df.columns:
            top["name"] = top["code"].map(df["name"])
        return top, df, len(scored)

    st.subheader("📊 量化选股")
    col_date, col_btn = st.columns([2, 1])
    with col_date:
        date_str = st.text_input("交易日（YYYY-MM-DD）", value=datetime.now().strftime("%Y-%m-%d"), key="quant_date")
    with col_btn:
        st.write("")
        st.write("")
        run = st.button("🔄 跑选股", type="primary", use_container_width=True, key="quant_run")

    if run:
        with st.spinner("拉取全市场数据 + 多因子打分..."):
            try:
                top, df, n = run_pick(date_str.strip())
                if top is None:
                    st.warning("该日期无数据（可能休市）。请确认是交易日。")
                else:
                    st.success(f"全市场 {n} 只参与打分，选出 Top {len(top)}")
                    _top1 = top.iloc[0]
                    conclusion(f"今日首选：<b>{_top1['name']}</b>（{_top1['code']}）",
                               f"综合得分 <b>{_top1['total_score']:.2f}</b>，从全市场 {n} 只中排名第 1。",
                               tone="bull")
                    show = top[["rank", "name", "code", "total_score"]].copy()
                    show["code"] = show["code"].astype(str).str.split(".").str[0]
                    show.columns = ["排名", "名称", "代码", "得分"]
                    st.dataframe(show, use_container_width=True, hide_index=True)
                    st.caption("因子：换手率 / 量比 / 流通市值 / 主力净流入 / 20日动量 / 乖离率")
            except Exception as e:  # noqa: BLE001
                st.error(f"选股失败：{e}")


# ============================================================
# Tab 2: 涨停股分析（原 04 页，去掉建仓建议）
# ============================================================
with tab_limit:
    if "_dragon_analyzed" not in st.session_state:
        st.session_state._dragon_analyzed = {}
    if "_dragon_loaded" not in st.session_state:
        st.session_state._dragon_loaded = False

    def parse_pct(val):
        if pd.isna(val) or val is None:
            return np.nan
        try:
            if isinstance(val, (int, float)):
                return float(val)
            return float(str(val).strip().replace("%", "").replace(" ", ""))
        except Exception:
            return np.nan

    def format_time(val):
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

    def render_stock_card(row):
        name = row.get("名称", "")
        code = row.get("代码", "")
        change_pct = parse_pct(row.get("涨跌幅", 0))
        if np.isnan(change_pct):
            change_pct = 0
        first_time = row.get("首次封板时间", "")
        is_blown = row.get("炸板次数", 0) > 0
        time_str = format_time(first_time)
        color = "#DC143C" if change_pct >= 0 else "#228B22"
        tags = []
        if is_blown:
            tags.append("炸板")
        if time_str and time_str not in ["00:00:00", "0:00:00"]:
            tags.append(time_str)
        tags_text = " | ".join(tags) if tags else ""
        st.markdown(f'''
        <div style="background:#1E293B;border-radius:8px;padding:10px 12px;min-height:85px;height:85px;
                    border-left:4px solid {color};border:1px solid #334155;display:flex;flex-direction:column;
                    justify-content:space-between;margin:4px 0;">
            <div style="display:flex;justify-content:space-between;align-items:center;">
                <span style="font-weight:bold;font-size:17px;color:#FFFFFF;">{name}</span>
                <span style="color:{color};font-weight:bold;font-size:16px;">{change_pct:+.2f}%</span>
            </div>
            <div><span style="font-size:12px;color:#94A3B8;">{code}</span>
            <span style="font-size:12px;color:#64748B;margin-left:8px;">{tags_text}</span></div>
        </div>''', unsafe_allow_html=True)

    def render_ladder_board(df):
        if df.empty or "连板数" not in df.columns:
            st.info("暂无连板数据")
            return
        board_groups = {}
        for _, row in df.iterrows():
            boards = int(row.get("连板数", 1))
            board_groups.setdefault(boards, []).append(row)
        max_board = max(board_groups.keys())
        st.subheader("📊 连板天梯")
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
                row_stocks = stocks[i:i + cols_per_row]
                cols = st.columns(cols_per_row)
                for j, stock in enumerate(row_stocks):
                    with cols[j]:
                        render_stock_card(stock)
            st.divider()

    limit_up_df = st.session_state.get("_limit_up_df")
    if limit_up_df is None or limit_up_df.empty:
        with st.spinner("正在获取涨停板数据..."):
            limit_up_df = df_.get_limit_up_stocks()
            st.session_state["_limit_up_df"] = limit_up_df

    if limit_up_df.empty:
        st.warning("今日暂无涨停板数据（可能为非交易日）")
    else:
        _max_b = int(limit_up_df["连板数"].max()) if "连板数" in limit_up_df.columns else 0
        conclusion(f"今日涨停 <b>{len(limit_up_df)}</b> 家，最高 <b>{_max_b} 连板</b>",
                   "涨停家数反映情绪热度，连板高度反映题材持续性。",
                   tone="bull" if len(limit_up_df) >= 50 else "neutral")
        col1, col2, col3, col4, col5 = st.columns(5)
        col1.metric("📈 涨停家数", len(limit_up_df))
        if "连板数" in limit_up_df.columns:
            col2.metric("🏆 最高连板", f"{limit_up_df['连板数'].max()}连板")
            col3.metric("📌 连板股数", len(limit_up_df[limit_up_df["连板数"] > 1]))
            if "炸板次数" in limit_up_df.columns:
                blown_count = len(limit_up_df[limit_up_df["炸板次数"] > 0])
                col4.metric("💥 炸板率", f"{blown_count / len(limit_up_df) * 100:.1f}%")
            if "一字板" in limit_up_df.columns:
                col5.metric("🔒 一字板", len(limit_up_df[limit_up_df["一字板"] == True]))

        # 一次性分析所有涨停股
        if not st.session_state._dragon_loaded:
            with st.spinner("正在分析所有涨停股技术指标..."):
                progress_bar = st.progress(0, text="分析进度")
                total = len(limit_up_df)
                for idx, (_, row) in enumerate(limit_up_df.iterrows()):
                    code = str(row.get("代码", "")).zfill(6)
                    name = row.get("名称", "")
                    local_k = dm.load_local(f"stock_{code}.csv")
                    kdf = local_k if (local_k is not None and not (hasattr(local_k, 'empty') and local_k.empty)) else df_.get_stock_kline(code, days=120)
                    if not kdf.empty:
                        kdf = anl.calc_all_indicators(kdf)
                        pred = anl.predict_next_day(kdf)
                        trend = anl.classify_trend(kdf)
                        sr = anl.calc_stop_loss_take_profit(kdf, "中等")
                        st.session_state._dragon_analyzed[code] = {"kline": kdf, "pred": pred, "trend": trend, "sr": sr, "name": name}
                    progress_bar.progress((idx + 1) / total, text=f"分析中 ({idx+1}/{total}) {name}")
                progress_bar.empty()
                st.session_state._dragon_loaded = True
                # 不调用 st.rerun()（在 tabs 里会触发 DeltaGenerator 异常），结果已存 _dragon_analyzed，直接继续渲染

        render_ladder_board(limit_up_df)

        with st.expander("📊 查看完整涨停板数据"):
            ddf = limit_up_df.copy()
            display_cols = ["代码", "名称", "涨跌幅", "所属行业", "连板数", "炸板次数", "首次封板时间", "最后封板时间"]
            available_cols = [c for c in display_cols if c in ddf.columns]
            if "一字板" in ddf.columns:
                available_cols.append("一字板")
            ddf_display = ddf[available_cols].copy()
            for col in ddf_display.columns:
                if "封板时间" in str(col):
                    ddf_display[col] = ddf_display[col].apply(format_time)
                elif "涨跌幅" in str(col):
                    ddf_display[col] = ddf_display[col].apply(parse_pct)
                elif "一字板" in str(col):
                    ddf_display[col] = ddf_display[col].apply(lambda x: "✅" if x else "")
            st.dataframe(ddf_display, hide_index=True, use_container_width=True, height=400)

        st.subheader("🔍 涨停股技术分析")
        stock_options = [f"{str(r.get('代码','')).zfill(6)} — {r.get('名称','')} ({r.get('连板数',1)}连板)" for _, r in limit_up_df.iterrows()]
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
                rt = st.session_state.get("_realtime_cache", {}).get(code, {})
                lu_row = None
                _lu = st.session_state.get("_limit_up_df")
                if _lu is not None and not _lu.empty and "代码" in _lu.columns:
                    _mask = _lu["代码"].astype(str).str.zfill(6) == code
                    if _mask.any():
                        lu_row = _lu[_mask].iloc[0]

                def _f(v):
                    try:
                        return float(v)
                    except (TypeError, ValueError):
                        return 0

                latest_close = kdf["close"].iloc[-1] if not kdf.empty else 0
                price = rt.get("price", 0) or (_f(lu_row.get("最新价")) if lu_row is not None else 0) or latest_close
                change_pct = rt.get("change_pct", 0) or (_f(lu_row.get("涨跌幅")) if lu_row is not None else 0)
                amount = rt.get("amount", 0) or (_f(lu_row.get("成交额")) if lu_row is not None else 0)
                turnover = rt.get("turnover", 0) or (_f(lu_row.get("换手率")) if lu_row is not None else 0)
                pe = rt.get("pe", 0)
                pb = rt.get("pb", 0)
                total_mv = rt.get("total_mv", 0) or (_f(lu_row.get("总市值")) if lu_row is not None else 0)

                st.subheader(f"📊 {name} ({code}) 实时行情")
                metric_cols = st.columns(6)
                metric_cols[0].metric("最新价", f"{price:.2f}" if price else "—")
                metric_cols[1].metric("涨跌幅", f"{change_pct:+.2f}%" if change_pct else "—", delta_color="inverse")
                metric_cols[2].metric("成交额", fmt_cn(amount) if amount else "—")
                metric_cols[3].metric("换手率", f"{turnover:.2f}%" if turnover else "—")
                metric_cols[4].metric("PE/PB", f"{pe:.1f}/{pb:.1f}" if pe else "—")
                metric_cols[5].metric("总市值", fmt_cn(total_mv) if total_mv else "—")

                st.subheader("📈 K线图")
                kline_html = viz.plot_kline_echarts(kdf, title=f"{name}({code}) · 日K线", height=500)
                components.html(kline_html, height=530)

                st.subheader("🔧 技术指标")
                ind_type = st.radio("选择指标", ["MACD", "KDJ", "RSI", "BOLL"], horizontal=True, key="dragon_indicator")
                ind_html = viz.plot_indicator_echarts(kdf, ind_type, height=280)
                components.html(ind_html, height=310)

                st.subheader("📋 趋势研判")
                trend_cols = st.columns(4)
                trend_cols[0].info(f"**短期趋势**\n\n{trend.get('short_signal', '—')}")
                trend_cols[1].info(f"**中期趋势**\n\n{trend.get('mid_signal', '—')}")
                trend_cols[2].info(f"**MACD信号**\n\n{trend.get('macd_signal', '—')}")
                patterns = anl.detect_patterns(kdf)
                trend_cols[3].warning(f"**K线形态**\n\n" + "\n".join(patterns)) if patterns else trend_cols[3].info("**K线形态**\n\n无明显形态")

                st.subheader("🔮 明日预测")
                pred_cols = st.columns(3)
                pred_cols[0].metric("预测方向", pred.get("direction", "—"))
                pred_cols[1].metric("置信度", f"{pred.get('confidence', 0)}%")
                pred_cols[2].metric("波动区间", pred.get("range", "—"))
                if pred.get("reasons"):
                    with st.expander("📝 预测依据"):
                        for reason in pred["reasons"]:
                            st.caption(f"• {reason}")

                if sr:
                    st.subheader("🎯 止盈止损位")
                    sr_cols = st.columns(5)
                    sr_cols[0].error(f"**止损（严格）**\n¥{sr.get('stop_loss_tight', '—')}")
                    sr_cols[1].warning(f"**止损（宽松）**\n¥{sr.get('stop_loss_loose', '—')}")
                    sr_cols[2].success(f"**止盈1**\n¥{sr.get('take_profit_1', '—')}")
                    sr_cols[3].success(f"**止盈2**\n¥{sr.get('take_profit_2', '—')}")
                    sr_cols[4].info(f"**建议仓位**\n{sr.get('suggested_position', '—')}")
                    st.caption("⚠️ 止盈止损是基于近期波动率（ATR）估算的参考位，不是精确预测。涨停股波动剧烈，结合分时承接执行。")


# ============================================================
# Tab 3: 明日预测（原 07 页）
# ============================================================
with tab_predict:
    _local_pf = dm.load_portfolio()

    st.subheader("📊 大盘明日预判")
    index_predictions = {}
    with st.spinner("正在分析大盘指数..."):
        for name, code in cfg.INDICES.items():
            df = df_.get_index_kline(code)
            if not df.empty:
                df = anl.calc_all_indicators(df)
                pred = anl.predict_next_day(df)
                trend = anl.classify_trend(df)
                index_predictions[name] = {"prediction": pred, "trend": trend}

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

    bullish = sum(1 for d in index_predictions.values() if "看涨" in d["prediction"].get("direction", "") or "偏强" in d["prediction"].get("direction", ""))
    bearish = sum(1 for d in index_predictions.values() if "看跌" in d["prediction"].get("direction", "") or "偏弱" in d["prediction"].get("direction", ""))
    if bullish > bearish:
        st.success(f"🎯 大盘综合判断：偏多（{bullish}/{len(index_predictions)}看涨）")
    elif bearish > bullish:
        st.error(f"🎯 大盘综合判断：偏空（{bearish}/{len(index_predictions)}看跌）")
    else:
        st.info("🎯 大盘综合判断：震荡")

    st.subheader("🌏 外围市场")
    with st.spinner("获取美股/日韩信号..."):
        try:
            import overseas as ov
            sig = ov.get_overseas_signal()
            if sig:
                cols = st.columns(4)
                cols[0].metric("纳指", f"{(sig.get('us_nasdaq') or 0)*100:+.2f}%")
                cols[1].metric("标普500", f"{(sig.get('us_sp500') or 0)*100:+.2f}%")
                cols[2].metric("韩国开盘", f"{(sig.get('kr_open') or 0)*100:+.2f}%")
                cols[3].metric("日经开盘", f"{(sig.get('jp_open') or 0)*100:+.2f}%")
                if ov.overseas_risk(sig):
                    st.error("⚠️ 外围风险：美股或日韩大跌，建议谨慎")
                else:
                    st.success("✅ 外围平稳")
            else:
                st.caption("外围数据暂不可用")
        except Exception:
            st.caption("外围数据获取失败")

    st.subheader("🔥 板块明日预判")
    with st.spinner("正在分析板块走势..."):
        sector_df = df_.get_sector_spot()
    if not sector_df.empty:
        top5 = sector_df.head(5)
        bottom5 = sector_df.tail(5)
        col_t, col_b = st.columns(2)
        with col_t:
            st.write("**🟢 强势板块（可能延续）**")
            for _, row in top5.iterrows():
                pct = row.get("change_pct", 0)
                note = "⚠️ 短期过热" if pct > 3 else "趋势延续" if pct > 1 else "温和上涨"
                st.write(f"🔥 **{row.get('sector_name','')}**：{pct:+.2f}% — {note}")
        with col_b:
            st.write("**🔴 弱势板块（可能反弹/续跌）**")
            for _, row in bottom5.iterrows():
                pct = row.get("change_pct", 0)
                note = "💡 超跌" if pct < -3 else "弱势延续" if pct < -1 else "小幅调整"
                st.write(f"📉 **{row.get('sector_name','')}**：{pct:+.2f}% — {note}")

    st.subheader("💼 持仓股明日预测")
    # 用 session_state 缓存，避免每次 rerun（切tab/拖拽排序）重复跑 31 只股票的循环
    _pf_key = "|".join(sorted(_local_pf.keys()))
    if st.session_state.get("holdings_pred_key") == _pf_key and "holdings_pred" in st.session_state:
        holdings_pred = st.session_state["holdings_pred"]
    else:
        holdings_pred = []
        _emotion = None
        try:
            _sent = df_.get_market_sentiment()
            if _sent and _sent.get("up_ratio") is not None:
                _emotion = {"up_ratio": _sent["up_ratio"] / 100}
        except Exception:
            _emotion = None

        for code, name in _local_pf.items():
            with st.spinner(f"正在分析 {name}({code})..."):
                df = df_.get_stock_kline(code)
                if df.empty:
                    continue
                df = anl.calc_all_indicators(df)
                fund_df = df_.get_stock_fund_factors(code)
                pred = anl.predict_next_day(df, fund_df if not fund_df.empty else None, _emotion)
                realtime = df_.get_stock_realtime(code)
                holdings_pred.append({
                    "code": code, "name": name,
                    "price": realtime.get("price", df["close"].iloc[-1]) if realtime else df["close"].iloc[-1],
                    "change_pct": realtime.get("change_pct", 0) if realtime else 0,
                    "direction": pred.get("direction", "—"),
                    "confidence": pred.get("confidence", 0),
                    "range": pred.get("range", "—"),
                    "score": pred.get("score", 0),
                })
        st.session_state["holdings_pred"] = holdings_pred
        st.session_state["holdings_pred_key"] = _pf_key

    if holdings_pred:
        pred_df = pd.DataFrame(holdings_pred)
        st.dataframe(fmt_dataframe(pred_df), hide_index=True, use_container_width=True)
        pred_df_sorted = pred_df.sort_values("score", ascending=False)
        st.subheader("📈 持仓股评分排行")
        for _, row in pred_df_sorted.iterrows():
            score = row["score"]
            bar_len = int(max(0, min(100, score + 5)) * 0.5)
            bar_color = "#DC143C" if score > 3 else "#FFD700" if score > 0 else "#228B22"
            st.write(f"**{row['name']}**({row['code']}) — {row['direction']} | 评分：{score:.1f}")
            st.markdown(f'<div style="background:{bar_color};height:6px;width:{bar_len}%;border-radius:3px;"></div>', unsafe_allow_html=True)
        best = pred_df_sorted.iloc[0]
        worst = pred_df_sorted.iloc[-1]
        conclusion(f"持仓预测：最看好 <b>{best['name']}</b>（评分 {best['score']:.1f}）",
                   f"最谨慎 <b>{worst['name']}</b>（评分 {worst['score']:.1f}）。评分越高次日越看好。",
                   tone="bull" if best["score"] > 3 else "neutral")

    # 综合操作建议（统一出口）
    st.subheader("📋 明日操作建议")
    market_signal = 1 if bullish > bearish else (-1 if bearish > bullish else 0)
    hold_avg_score = np.mean([h["score"] for h in holdings_pred]) if holdings_pred else 0
    conclusion(
        "操作建议："
        + ("🟢 大盘偏多，可适当提升仓位" if market_signal > 0 else "🔴 大盘偏空，控制仓位" if market_signal < 0 else "🟡 大盘震荡，高抛低吸"),
        f"持仓平均评分 <b>{hold_avg_score:.1f}</b> 分。"
        + ("持仓评分偏低，注意精选标的。" if hold_avg_score <= 0 else "持仓整体偏强，可关注强势板块轮动。"),
        tone="bull" if market_signal > 0 else ("bear" if market_signal < 0 else "neutral"),
    )
    st.caption("⚠️ 以上为 AI 基于技术指标的预判，不构成投资建议。市场有风险，投资需谨慎。")
