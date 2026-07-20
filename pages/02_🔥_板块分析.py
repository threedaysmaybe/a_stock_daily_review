"""
页面2：板块分析 — 行业热力图 + 涨跌排行 + 资金流向
"""

import streamlit as st
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config as cfg
from utils.formatters import fmt_dataframe
from utils.helpers import fmt_cn
import data_fetcher as df_
import visualizer as viz
import pandas as pd
from datetime import datetime, timedelta

st.set_page_config(page_title="板块分析", page_icon="🔥", layout="wide")

st.title("🔥 板块分析")
st.caption(f"数据更新时间：{pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}")

# ============================================================
# 获取行业板块数据
# ============================================================
with st.spinner("正在获取行业板块数据..."):
    sector_df = df_.get_sector_spot()

if sector_df.empty:
    st.error("无法获取板块数据")
    st.stop()

# ============================================================
# 获取概念板块数据
# ============================================================
with st.spinner("正在获取概念板块数据..."):
    concept_df = df_.get_concept_spot()

# ============================================================
# 获取近5日历史板块数据
# ============================================================
def get_history_data(data_type="sector", days=10):
    """获取历史板块数据（返回所有可用日期）"""
    data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
    history_data = []
    
    if not os.path.exists(data_dir):
        return history_data
    
    # 获取所有日期目录，按日期排序（最新的在前）
    date_dirs = [d for d in os.listdir(data_dir) if os.path.isdir(os.path.join(data_dir, d)) and d.isdigit()]
    date_dirs.sort(reverse=True)
    
    file_name = "sectors.csv" if data_type == "sector" else "concept_sectors.csv"
    collected = 0
    
    for date_str in date_dirs:
        file_path = os.path.join(data_dir, date_str, file_name)
        if os.path.exists(file_path):
            try:
                df = pd.read_csv(file_path, encoding="utf-8-sig")
                if not df.empty:
                    # 兼容列名
                    if "板块" in df.columns:
                        df = df.rename(columns={"板块": "sector_name"})
                    if "涨跌幅" in df.columns:
                        df = df.rename(columns={"涨跌幅": "change_pct"})
                    if "change_pct" in df.columns:
                        df["change_pct"] = pd.to_numeric(df["change_pct"], errors="coerce").fillna(0)
                    if "sector_name" not in df.columns and len(df.columns) > 0:
                        df["sector_name"] = df.iloc[:, 0]
                    
                    display_date = date_str[:4] + "-" + date_str[4:6] + "-" + date_str[6:8]
                    df["trade_date"] = display_date
                    history_data.append(df)
                    collected += 1
                    if collected >= days:
                        break
            except Exception as e:
                print(f"读取 {date_str} 失败: {e}")
                continue
    
    return history_data


# ============================================================
# Tab 切换：行业板块 / 概念板块
# ============================================================
tab1, tab2 = st.tabs(["🏢 行业板块", "💡 概念板块"])

with tab1:
    up_count = len(sector_df[sector_df["change_pct"] > 0])
    down_count = len(sector_df[sector_df["change_pct"] < 0])
    avg_pct = sector_df["change_pct"].mean()

    cols = st.columns(4)
    cols[0].metric("板块总数", len(sector_df))
    cols[1].metric("上涨板块", up_count, delta=f"占比{up_count/len(sector_df)*100:.0f}%")
    cols[2].metric("下跌板块", down_count, delta=f"占比{down_count/len(sector_df)*100:.0f}%")
    cols[3].metric("平均涨跌", f"{avg_pct:+.2f}%")

    st.divider()
    
    # ---- 🔍 今日热点 + 近5日每日TOP5（同一行） ----
    col_left, col_right = st.columns(2)
    
    with col_left:
        st.subheader("🔍 今日热点行业板块")
        top_sectors = sector_df.head(5)
        if not top_sectors.empty:
            for _, row in top_sectors.iterrows():
                name = row.get("sector_name", "")
                pct = row.get("change_pct", 0)
                color = "#DC143C" if pct >= 0 else "#228B22"
                st.markdown(f"""
                <div style="background:#1E293B;border-radius:6px;padding:8px 12px;margin:4px 0;border-left:3px solid {color};display:flex;justify-content:space-between;">
                    <span style="color:#F1F5F9;font-size:14px;">{name}</span>
                    <span style="color:{color};font-weight:bold;font-size:14px;">{pct:+.2f}%</span>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.caption("暂无数据")
    
    with col_right:
        st.subheader("📅 近5日每日TOP5")
        history = get_history_data(data_type="sector", days=10)
        if history:
            history = history[:5]
            
            date_labels = []
            rank_data = {i: [] for i in range(1, 6)}
            
            # 收集所有板块名称
            all_names = []
            for df in history:
                top5 = df.nlargest(5, "change_pct")
                all_names.extend(top5["sector_name"].tolist())
            
            # 去重并分配颜色
            unique_names = list(dict.fromkeys(all_names))
            colors = [
                "#FF6B6B", "#4ECDC4", "#45B7D1", "#96CEB4", "#FFEAA7",
                "#DDA0DD", "#98D8C8", "#F7DC6F", "#BB8FCE", "#85C1E9",
                "#F1948A", "#82E0AA", "#F8C471", "#73C6B6", "#E59866",
            ]
            color_map = {}
            for i, name in enumerate(unique_names):
                color_map[name] = colors[i % len(colors)]
            
            for df in history:
                date_label = df["trade_date"].iloc[0] if "trade_date" in df.columns else "—"
                date_labels.append(date_label)
                top5 = df.nlargest(5, "change_pct")
                names = top5["sector_name"].tolist()
                while len(names) < 5:
                    names.append("—")
                for rank in range(1, 6):
                    rank_data[rank].append(names[rank-1])
            
            st.markdown("""
            <style>
            .rank-table {
                width: 100%;
                border-collapse: collapse;
                font-size: 13px;
            }
            .rank-table th {
                background: #334155;
                color: #F1F5F9;
                padding: 6px 8px;
                text-align: center;
                border: 1px solid #475569;
            }
            .rank-table td {
                padding: 6px 8px;
                text-align: center;
                border: 1px solid #475569;
                color: #E2E8F0;
                font-weight: bold;
            }
            .rank-table .rank-label {
                color: #94A3B8;
                font-weight: bold;
            }
            .rank-table .rank-1 { color: #FFD700; }
            .rank-table .rank-2 { color: #C0C0C0; }
            .rank-table .rank-3 { color: #CD7F32; }
            </style>
            """, unsafe_allow_html=True)
            
            html = '<table class="rank-table"><tr><th>排名</th>'
            for date in date_labels:
                html += f'<th>{date}</th>'
            html += '</tr>'
            
            rank_emojis = {1: "🥇", 2: "🥈", 3: "🥉", 4: "4", 5: "5"}
            for rank in range(1, 6):
                rank_class = f"rank-{rank}" if rank <= 3 else ""
                html += f'<tr><td class="rank-label">{rank_emojis[rank]}</td>'
                for name in rank_data[rank]:
                    if name == "—":
                        html += f'<td class="{rank_class}" style="color:#475569;">—</td>'
                    else:
                        color = color_map.get(name, "#FFFFFF")
                        html += f'<td class="{rank_class}" style="color:{color};">{name}</td>'
                html += '</tr>'
            html += '</table>'
            st.markdown(html, unsafe_allow_html=True)
        else:
            st.caption("暂无历史数据，请运行「更新数据」")

    st.divider()

    st.subheader("🗺️ 行业板块涨跌热力图")
    fig_heat = viz.plot_sector_heatmap(sector_df)
    st.plotly_chart(fig_heat, use_container_width=True)

    st.subheader("📋 行业板块涨跌排行")
    top_n = st.slider("显示数量", 5, 30, 15, key="industry_top_n")
    fig_bar = viz.plot_sector_bar(sector_df, top_n=top_n)
    st.plotly_chart(fig_bar, use_container_width=True)

    st.subheader("📊 完整数据表")
    display_df = sector_df[["sector_name", "change_pct", "up_count", "down_count", "top_stock"]].copy()
    display_df.columns = ["板块名称", "涨跌幅", "上涨家数", "下跌家数", "领涨股"]
    st.dataframe(
        display_df.style.format({"涨跌幅": "{:+.2f}%"}),
        hide_index=True,
        use_container_width=True,
        height=600,
    )

with tab2:
    if concept_df.empty:
        st.info("暂无概念板块数据")
    else:
        up_count = len(concept_df[concept_df["change_pct"] > 0])
        down_count = len(concept_df[concept_df["change_pct"] < 0])
        avg_pct = concept_df["change_pct"].mean()

        cols = st.columns(4)
        cols[0].metric("概念总数", len(concept_df))
        cols[1].metric("上涨概念", up_count, delta=f"占比{up_count/len(concept_df)*100:.0f}%")
        cols[2].metric("下跌概念", down_count, delta=f"占比{down_count/len(concept_df)*100:.0f}%")
        cols[3].metric("平均涨跌", f"{avg_pct:+.2f}%")

        st.divider()
        
        # ---- 🔍 今日热点 + 近5日每日TOP5（同一行） ----
        col_left, col_right = st.columns(2)
        
        with col_left:
            st.subheader("🔍 今日热点概念板块")
            top_concepts = concept_df.head(5)
            if not top_concepts.empty:
                for _, row in top_concepts.iterrows():
                    name = row.get("sector_name", "")
                    pct = row.get("change_pct", 0)
                    color = "#DC143C" if pct >= 0 else "#228B22"
                    st.markdown(f"""
                    <div style="background:#1E293B;border-radius:6px;padding:8px 12px;margin:4px 0;border-left:3px solid {color};display:flex;justify-content:space-between;">
                        <span style="color:#F1F5F9;font-size:14px;">{name}</span>
                        <span style="color:{color};font-weight:bold;font-size:14px;">{pct:+.2f}%</span>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.caption("暂无数据")
        
        with col_right:
            st.subheader("📅 近5日每日TOP5")
            history = get_history_data(data_type="concept", days=10)
            if history:
                history = history[:5]
                
                date_labels = []
                rank_data = {i: [] for i in range(1, 6)}
                
                # 收集所有板块名称
                all_names = []
                for df in history:
                    top5 = df.nlargest(5, "change_pct")
                    all_names.extend(top5["sector_name"].tolist())
                
                # 去重并分配颜色
                unique_names = list(dict.fromkeys(all_names))
                colors = [
                    "#FF6B6B", "#4ECDC4", "#45B7D1", "#96CEB4", "#FFEAA7",
                    "#DDA0DD", "#98D8C8", "#F7DC6F", "#BB8FCE", "#85C1E9",
                    "#F1948A", "#82E0AA", "#F8C471", "#73C6B6", "#E59866",
                ]
                color_map = {}
                for i, name in enumerate(unique_names):
                    color_map[name] = colors[i % len(colors)]
                
                for df in history:
                    date_label = df["trade_date"].iloc[0] if "trade_date" in df.columns else "—"
                    date_labels.append(date_label)
                    top5 = df.nlargest(5, "change_pct")
                    names = top5["sector_name"].tolist()
                    while len(names) < 5:
                        names.append("—")
                    for rank in range(1, 6):
                        rank_data[rank].append(names[rank-1])
                
                st.markdown("""
                <style>
                .rank-table {
                    width: 100%;
                    border-collapse: collapse;
                    font-size: 13px;
                }
                .rank-table th {
                    background: #334155;
                    color: #F1F5F9;
                    padding: 6px 8px;
                    text-align: center;
                    border: 1px solid #475569;
                }
                .rank-table td {
                    padding: 6px 8px;
                    text-align: center;
                    border: 1px solid #475569;
                    color: #E2E8F0;
                    font-weight: bold;
                }
                .rank-table .rank-label {
                    color: #94A3B8;
                    font-weight: bold;
                }
                .rank-table .rank-1 { color: #FFD700; }
                .rank-table .rank-2 { color: #C0C0C0; }
                .rank-table .rank-3 { color: #CD7F32; }
                </style>
                """, unsafe_allow_html=True)
                
                html = '<table class="rank-table"><tr><th>排名</th>'
                for date in date_labels:
                    html += f'<th>{date}</th>'
                html += '</tr>'
                
                rank_emojis = {1: "🥇", 2: "🥈", 3: "🥉", 4: "4", 5: "5"}
                for rank in range(1, 6):
                    rank_class = f"rank-{rank}" if rank <= 3 else ""
                    html += f'<tr><td class="rank-label">{rank_emojis[rank]}</td>'
                    for name in rank_data[rank]:
                        if name == "—":
                            html += f'<td class="{rank_class}" style="color:#475569;">—</td>'
                        else:
                            color = color_map.get(name, "#FFFFFF")
                            html += f'<td class="{rank_class}" style="color:{color};">{name}</td>'
                    html += '</tr>'
                html += '</table>'
                st.markdown(html, unsafe_allow_html=True)
            else:
                st.caption("暂无历史数据，请运行「更新数据」")

        st.divider()

        st.subheader("🗺️ 概念板块涨跌热力图")
        fig_heat = viz.plot_sector_heatmap(concept_df)
        st.plotly_chart(fig_heat, use_container_width=True)

        st.subheader("📋 概念板块涨跌排行")
        top_n = st.slider("显示数量", 5, 30, 15, key="concept_top_n")
        fig_bar = viz.plot_sector_bar(concept_df, top_n=top_n)
        st.plotly_chart(fig_bar, use_container_width=True)

        st.subheader("📊 完整数据表")
        display_df = concept_df[["sector_name", "change_pct", "up_count", "down_count", "top_stock"]].copy()
        display_df.columns = ["概念名称", "涨跌幅", "上涨家数", "下跌家数", "领涨股"]
        st.dataframe(
            display_df.style.format({"涨跌幅": "{:+.2f}%"}),
            hide_index=True,
            use_container_width=True,
            height=600,
        )

# ============================================================
# 页脚
# ============================================================
st.divider()
st.caption("⚠️ 以上分析仅供研究参考，不构成投资建议。市场有风险，投资需谨慎。")