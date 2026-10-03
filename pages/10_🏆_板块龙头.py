"""板块龙头股：每个行业市值前 5 的龙头，每日更新。"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import pandas as pd

import config as cfg
import data_fetcher as df_
from utils.ui import inject_css, conclusion

st.set_page_config(page_title="板块龙头", page_icon="🏆", layout="wide")
inject_css()
st.title("🏆 板块龙头股")
st.caption("每个行业取「总市值前 5」作为龙头，龙头会随市值变化自动更新（今年是龙头，明年可能换人）")

with st.spinner("拉取各行业龙头股..."):
    leaders = df_.get_industry_leaders(5)

if leaders.empty:
    st.warning("龙头股数据暂不可用（可能休市或数据源异常）")
else:
    conclusion(f"覆盖 <b>{leaders['industry'].nunique()}</b> 个行业，共 <b>{len(leaders)}</b> 只龙头",
               f"数据日期 {leaders['trade_date'].iloc[0]}，按总市值排序取各行业前 5 名。"
               f"市值 = 市场公认的行业地位代理指标。",
               tone="neutral")

    # 行业筛选
    industries = sorted(leaders["industry"].unique())
    sel_ind = st.multiselect("筛选行业（可多选，不选=全部）", industries, default=[])

    view = leaders[leaders["industry"].isin(sel_ind)] if sel_ind else leaders

    # 板块涨跌（Tushare 自己算的申万行业涨跌，与龙头 industry 同一套分类，能完美匹配）
    _ind_pct = {}
    try:
        _ind_pct = df_.get_industry_pct()
    except Exception:
        pass

    # 按行业分组显示（同一行业的龙头放一起 + 板块分析）
    _ind_list = sorted(view["industry"].unique())
    st.caption(f"共 {len(_ind_list)} 个行业，每个行业按总市值列前 5")
    for _i, industry in enumerate(_ind_list):
        group = view[view["industry"] == industry]
        with st.expander(f"🏢 {industry}（{len(group)}只）", expanded=(_i == 0)):
            # 板块概览指标
            _avg_pct = pd.to_numeric(group["pct_chg"], errors="coerce").mean()
            _avg_turn = pd.to_numeric(group["turnover_rate"], errors="coerce").mean()
            _tot_mv = pd.to_numeric(group["total_mv"], errors="coerce").sum() / 1e4
            _sector_pct = _ind_pct.get(industry)
            _m = st.columns(4)
            _m[0].metric("板块涨跌", f"{_sector_pct:+.2f}%" if _sector_pct is not None else "—",
                         delta_color="inverse")
            _m[1].metric("龙头均涨跌", f"{_avg_pct:+.2f}%", delta_color="inverse")
            _m[2].metric("龙头均换手", f"{_avg_turn:.2f}%")
            _m[3].metric("龙头总市值", f"{_tot_mv:.0f}亿")
            # 资金认可度 / 强弱判断
            if _avg_pct > 2:
                _verdict = "🟢 板块强势，龙头领涨，资金认可度高"
            elif _avg_pct < -2:
                _verdict = "🔴 板块弱势，龙头领跌，资金回避"
            else:
                _verdict = "🟡 板块分化，龙头震荡，观望"
            st.caption(_verdict)

            # 龙头股表格
            show = group.copy()
            show["code"] = show["ts_code"].astype(str).str.split(".").str[0]
            show["总市值(亿)"] = (pd.to_numeric(show["total_mv"], errors="coerce") / 1e4).round(0)
            show["涨跌幅%"] = pd.to_numeric(show["pct_chg"], errors="coerce").round(2)
            show["换手率%"] = pd.to_numeric(show["turnover_rate"], errors="coerce").round(2)
            show = show[["name", "code", "总市值(亿)", "涨跌幅%", "换手率%"]]
            show.columns = ["龙头", "代码", "总市值(亿)", "涨跌幅%", "换手率%"]
            st.dataframe(show, hide_index=True, use_container_width=True)

    st.caption("💡 龙头股 = 行业的「风向标」，板块异动时先看龙头反应；龙头走弱往往预示板块退潮。")
