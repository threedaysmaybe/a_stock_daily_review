"""
每日A股复盘模型 - 可视化模块
统一生成 plotly 图表，保证风格一致
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
from typing import Optional

import config as cfg

# ============================================================
# 通用样式

def _fmt(v):
    if abs(v) >= 1e8: return f"{v/1e8:.2f}亿"
    elif abs(v) >= 1e4: return f"{v/1e4:.0f}万"
    return f"{v:.0f}"

# ============================================================

FONT_FAMILY = "Microsoft YaHei, SimHei, Arial, sans-serif"

# A股：红涨绿跌
UP_COLOR = cfg.COLORS["red_up"]
DOWN_COLOR = cfg.COLORS["green_down"]

PLOT_BG = "#0F172A"       # 深色背景
PAPER_BG = "#1E293B"
GRID_COLOR = "rgba(255,255,255,0.08)"
TEXT_COLOR = "#94A3B8"
TITLE_COLOR = "#F1F5F9"

# 通用 layout 模板
LAYOUT_DARK = dict(
    font=dict(family=FONT_FAMILY, color=TEXT_COLOR, size=11),
    plot_bgcolor=PLOT_BG,
    paper_bgcolor=PAPER_BG,
    xaxis=dict(
        gridcolor=GRID_COLOR,
        zerolinecolor=GRID_COLOR,
        rangebreaks=[dict(bounds=["sat", "mon"])],  # 跳过周末
        color=TEXT_COLOR,
    ),
    yaxis=dict(
        gridcolor=GRID_COLOR,
        zerolinecolor=GRID_COLOR,
        color=TEXT_COLOR,
    ),
    hovermode="x unified",
    legend=dict(
        font=dict(size=10),
        bgcolor="rgba(0,0,0,0.3)",
        bordercolor="rgba(255,255,255,0.1)",
        borderwidth=1,
    ),
)

# 单图 x 轴配置（跳过周末）
XAXIS_CONFIG = dict(
    gridcolor=GRID_COLOR,
    zerolinecolor=GRID_COLOR,
    color=TEXT_COLOR,
    rangebreaks=[dict(bounds=["sat", "mon"])],
)


# ============================================================
# 1. K线图（含均线+成交量）
# ============================================================

def plot_kline_with_volume(df: pd.DataFrame, title: str = "K线图",
                           ma_lines: list = None, height: int = 600) -> go.Figure:
    """K线图+成交量副图+均线"""
    if df.empty:
        return go.Figure()

    if ma_lines is None:
        ma_lines = [5, 20, 60]

    # 计算均线
    for p in ma_lines:
        df[f"MA{p}"] = df["close"].rolling(p).mean()

    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=[0.7, 0.3],
        subplot_titles=("", ""),
    )

    # K线
    fig.add_trace(go.Candlestick(
        x=df["date"],
        open=df["open"], high=df["high"],
        low=df["low"], close=df["close"],
        name="K线",
        increasing=dict(line=dict(color=UP_COLOR, width=1), fillcolor=UP_COLOR),
        decreasing=dict(line=dict(color=DOWN_COLOR, width=1), fillcolor=DOWN_COLOR),
        showlegend=True,
    ), row=1, col=1)

    # 均线
    ma_colors = {5: "#FFD700", 20: "#60A5FA", 60: "#F87171", 120: "#A78BFA"}
    for p in ma_lines:
        if f"MA{p}" in df.columns:
            fig.add_trace(go.Scatter(
                x=df["date"], y=df[f"MA{p}"],
                mode="lines", name=f"MA{p}",
                line=dict(color=ma_colors.get(p, "#888"), width=1.2),
                opacity=0.8,
            ), row=1, col=1)

    # 成交量（红涨绿跌）
    colors = [UP_COLOR if df["close"].iloc[i] >= df["open"].iloc[i]
              else DOWN_COLOR for i in range(len(df))]
    fig.add_trace(go.Bar(
        x=df["date"], y=df["volume"],
        name="成交量",
        marker=dict(color=colors, opacity=0.5),
        showlegend=True,
    ), row=2, col=1)

    layout_kwargs = {k: v for k, v in LAYOUT_DARK.items() if k not in ("xaxis", "yaxis")}
    fig.update_layout(
        **layout_kwargs,
        title=dict(text=title, font=dict(size=16, color=TITLE_COLOR), x=0.5),
        height=height,
        xaxis_rangeslider_visible=False,
        margin=dict(t=50, l=10, r=10, b=10),
    )
    fig.update_xaxes(XAXIS_CONFIG, row=1, col=1)
    fig.update_xaxes(XAXIS_CONFIG, row=2, col=1)
    fig.update_yaxes(title_text="价格", row=1, col=1)
    fig.update_yaxes(title_text="成交量", row=2, col=1)

    return fig


# ============================================================
# 2. 板块热力图
# ============================================================

def plot_sector_heatmap(sector_df: pd.DataFrame, height: int = 600) -> go.Figure:
    """板块涨跌热力图（treemap）"""
    if sector_df.empty:
        return go.Figure()

    df = sector_df.copy()
    df = df.dropna(subset=["change_pct"])
    # 按涨跌幅从高到低排序
    df = df.sort_values("change_pct", ascending=False).reset_index(drop=True)

    # 生成显示文本：板块名称 + 涨跌幅（两位小数）
    df["display_text"] = df["change_pct"].apply(lambda x: f"{x:+.2f}%")

    fig = go.Figure(go.Treemap(
        labels=df["sector_name"],
        parents=[""] * len(df),
        # 用涨跌幅绝对值 + 偏移量控制大小，正的更大，负的更小
        values=[v + abs(min(df["change_pct"])) + 1 for v in df["change_pct"]],
        text=df["display_text"],
        textposition="middle center",
        textfont=dict(size=14, color="#FFFFFF", family=FONT_FAMILY),
        marker=dict(
            colors=df["change_pct"],
            colorscale=[
                [0, DOWN_COLOR],
                [0.35, "rgba(34,139,34,0.6)"],
                [0.45, "rgba(100,100,100,0.5)"],
                [0.5, "rgba(128,128,128,0.3)"],
                [0.55, "rgba(220,20,60,0.6)"],
                [1, UP_COLOR],
            ],
            cmid=0,
        ),
        hovertemplate="<b>%{label}</b><br>涨跌幅: %{customdata[0]:+.2f}%<extra></extra>",
    ))

    fig.update_layout(
        **LAYOUT_DARK,
        title=dict(text="板块涨跌热力图", font=dict(size=16, color=TITLE_COLOR), x=0.5),
        height=height,
        margin=dict(t=50, l=10, r=10, b=10),
    )
    return fig


# ============================================================
# 3. 板块涨跌排行
# ============================================================

def plot_sector_bar(sector_df: pd.DataFrame, top_n: int = 15, height: int = 500) -> go.Figure:
    """板块涨跌排行水平柱状图"""
    if sector_df.empty:
        return go.Figure()

    df = sector_df.dropna(subset=["change_pct"]).sort_values("change_pct", ascending=True)
    df_top = pd.concat([df.head(top_n), df.tail(top_n)]).drop_duplicates()

    colors = [UP_COLOR if v >= 0 else DOWN_COLOR for v in df_top["change_pct"]]

    fig = go.Figure(go.Bar(
        y=df_top["sector_name"],
        x=df_top["change_pct"],
        orientation="h",
        marker=dict(color=colors, opacity=0.85),
        text=[f"{v:+.2f}%" for v in df_top["change_pct"]],
        textposition="outside",
        textfont=dict(color=TEXT_COLOR, size=10),
        hovertemplate="<b>%{y}</b><br>涨跌幅: %{x:+.2f}%<extra></extra>",
    ))

    fig.update_layout(
        **LAYOUT_DARK,
        title=dict(text=f"板块涨跌排行（Top{top_n}+Bottom{top_n}）", font=dict(size=16, color=TITLE_COLOR), x=0.5),
        height=height,
        xaxis_title="涨跌幅(%)",
        margin=dict(t=50, l=10, r=50, b=10),
    )
    return fig


# ============================================================
# 4. 资金流向图
# ============================================================

def plot_fund_flow_pie(fund_data: dict, title: str = "资金流向分布", height: int = 350) -> go.Figure:
    """资金流向饼图"""
    if not fund_data:
        return go.Figure()

    labels = ["主力净流入", "超大单净流入", "大单净流入", "中单净流入", "小单净流入"]
    values = [
        fund_data.get("main_net_inflow", 0) or 0,
        fund_data.get("super_large_net", 0) or 0,
        fund_data.get("large_net", 0) or 0,
        fund_data.get("mid_net", 0) or 0,
        fund_data.get("small_net", 0) or 0,
    ]

    colors_pie = [UP_COLOR, "#FF6B6B", "#FFA07A", DOWN_COLOR, "#66CDAA"]

    fig = go.Figure(go.Pie(
        labels=labels, values=values,
        marker=dict(colors=colors_pie),
        textfont=dict(family=FONT_FAMILY, size=11),
        hovertemplate="<b>%{label}</b><br>%{value:,.0f} 万<extra></extra>",
    ))

    fig.update_layout(
        **LAYOUT_DARK,
        title=dict(text=title, font=dict(size=14, color=TITLE_COLOR), x=0.5),
        height=height,
        margin=dict(t=40, l=10, r=10, b=10),
    )
    return fig


# ============================================================
# 5. 技术指标图（MACD/KDJ/RSI/BOLL）
# ============================================================

def plot_macd(df: pd.DataFrame, height: int = 300) -> go.Figure:
    """MACD图"""
    if df.empty or "DIF" not in df.columns:
        return go.Figure()

    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.update_xaxes(XAXIS_CONFIG)

    # MACD柱
    colors_macd = [UP_COLOR if v >= 0 else DOWN_COLOR for v in df["MACD"]]
    fig.add_trace(go.Bar(
        x=df["date"], y=df["MACD"],
        name="MACD柱",
        marker=dict(color=colors_macd, opacity=0.6),
    ), secondary_y=False)

    # DIF / DEA
    fig.add_trace(go.Scatter(
        x=df["date"], y=df["DIF"],
        mode="lines", name="DIF",
        line=dict(color="#FFD700", width=1.5),
    ), secondary_y=False)

    fig.add_trace(go.Scatter(
        x=df["date"], y=df["DEA"],
        mode="lines", name="DEA",
        line=dict(color="#60A5FA", width=1.5),
    ), secondary_y=False)

    layout_kwargs = {k: v for k, v in LAYOUT_DARK.items() if k not in ("xaxis", "yaxis")}
    fig.update_layout(
        **layout_kwargs,
        title=dict(text="MACD (12, 26, 9)", font=dict(size=14, color=TITLE_COLOR), x=0.5),
        height=height,
        margin=dict(t=40, l=10, r=10, b=10),
        showlegend=True,
    )
    return fig


def plot_kdj(df: pd.DataFrame, height: int = 300) -> go.Figure:
    """KDJ图"""
    if df.empty or "K" not in df.columns:
        return go.Figure()

    latest_k = df["K"].iloc[-1] if not df.empty else 50
    latest_d = df["D"].iloc[-1] if not df.empty else 50
    latest_j = df["J"].iloc[-1] if not df.empty else 50

    fig = go.Figure()
    fig.update_xaxes(XAXIS_CONFIG)

    fig.add_trace(go.Scatter(x=df["date"], y=df["K"], mode="lines", name=f"K({latest_k:.1f})",
                             line=dict(color="#FFD700", width=1.5)))
    fig.add_trace(go.Scatter(x=df["date"], y=df["D"], mode="lines", name=f"D({latest_d:.1f})",
                             line=dict(color="#60A5FA", width=1.5)))
    fig.add_trace(go.Scatter(x=df["date"], y=df["J"], mode="lines", name=f"J({latest_j:.1f})",
                             line=dict(color="#F87171", width=1.2, dash="dot")))

    fig.update_layout(
        **LAYOUT_DARK,
        title=dict(text="KDJ (9, 3, 3)", font=dict(size=14, color=TITLE_COLOR), x=0.5),
        height=height,
        margin=dict(t=40, l=10, r=10, b=10),
    )
    fig.update_yaxes(range=[0, 100])
    return fig


def plot_rsi(df: pd.DataFrame, height: int = 300) -> go.Figure:
    """RSI图"""
    if df.empty or "RSI6" not in df.columns:
        return go.Figure()

    latest_rsi6 = df["RSI6"].iloc[-1] if not df.empty else 50
    latest_rsi12 = df["RSI12"].iloc[-1] if not df.empty else 50
    latest_rsi24 = df["RSI24"].iloc[-1] if not df.empty else 50

    fig = go.Figure()
    fig.update_xaxes(XAXIS_CONFIG)

    fig.add_trace(go.Scatter(x=df["date"], y=df["RSI6"], mode="lines", name=f"RSI6({latest_rsi6:.1f})",
                             line=dict(color="#60A5FA", width=1.5)))
    fig.add_trace(go.Scatter(x=df["date"], y=df["RSI12"], mode="lines", name=f"RSI12({latest_rsi12:.1f})",
                             line=dict(color="#FFD700", width=1.5)))
    fig.add_trace(go.Scatter(x=df["date"], y=df["RSI24"], mode="lines", name=f"RSI24({latest_rsi24:.1f})",
                             line=dict(color="#F87171", width=1.2, dash="dot")))

    fig.update_layout(
        **LAYOUT_DARK,
        title=dict(text="RSI (6, 12, 24)", font=dict(size=14, color=TITLE_COLOR), x=0.5),
        height=height,
        margin=dict(t=40, l=10, r=10, b=10),
    )
    fig.update_yaxes(range=[0, 100])
    return fig


def plot_boll(df: pd.DataFrame, height: int = 400) -> go.Figure:
    """布林带图"""
    if df.empty or "BOLL_UP" not in df.columns:
        return go.Figure()

    fig = go.Figure()
    fig.update_xaxes(XAXIS_CONFIG)

    # 填充区域
    fig.add_trace(go.Scatter(
        x=pd.concat([df["date"], df["date"][::-1]]),
        y=pd.concat([df["BOLL_UP"], df["BOLL_DN"][::-1]]),
        fill="toself",
        fillcolor="rgba(96,165,250,0.08)",
        line=dict(width=0),
        name="布林带区间",
        showlegend=True,
    ))

    fig.add_trace(go.Scatter(x=df["date"], y=df["BOLL_UP"], mode="lines",
                             line=dict(color="#F87171", width=1, dash="dash"), name="上轨"))
    fig.add_trace(go.Scatter(x=df["date"], y=df["BOLL_MID"], mode="lines",
                             line=dict(color="#FFD700", width=1.5), name="中轨(MA20)"))
    fig.add_trace(go.Scatter(x=df["date"], y=df["BOLL_DN"], mode="lines",
                             line=dict(color="#34D399", width=1, dash="dash"), name="下轨"))
    fig.add_trace(go.Scatter(x=df["date"], y=df["close"], mode="lines",
                             line=dict(color="#E2E8F0", width=1.5), name="收盘价"))

    fig.update_layout(
        **LAYOUT_DARK,
        title=dict(text="BOLL 布林带 (20, 2)", font=dict(size=14, color=TITLE_COLOR), x=0.5),
        height=height,
        margin=dict(t=40, l=10, r=10, b=10),
    )
    return fig


# ============================================================
# 6. 评分仪表盘
# ============================================================

def plot_score_gauge(score: float, title: str = "综合评分", height: int = 250) -> go.Figure:
    """评分仪表盘"""
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=score,
        number=dict(font=dict(size=36, color=TITLE_COLOR), suffix="分"),
        title=dict(text=title, font=dict(size=14, color=TEXT_COLOR)),
        gauge=dict(
            axis=dict(range=[0, 100], tickcolor=TEXT_COLOR, tickfont=dict(size=10)),
            bar=dict(color=UP_COLOR if score >= 60 else "#FFD700" if score >= 40 else DOWN_COLOR, thickness=0.2),
            bgcolor="rgba(255,255,255,0.05)",
            borderwidth=0,
            steps=[
                {"range": [0, 30], "color": "rgba(34,139,34,0.2)"},
                {"range": [30, 50], "color": "rgba(255,215,0,0.15)"},
                {"range": [50, 70], "color": "rgba(255,215,0,0.25)"},
                {"range": [70, 90], "color": "rgba(220,20,60,0.2)"},
                {"range": [90, 100], "color": "rgba(220,20,60,0.3)"},
            ],
            threshold=dict(
                line=dict(color=UP_COLOR, width=2),
                thickness=1, value=score,
            ),
        ),
    ))

    fig.update_layout(
        **LAYOUT_DARK,
        height=height,
        margin=dict(t=50, l=20, r=20, b=10),
    )
    return fig


# ============================================================
# 7. 游资操作分布
# ============================================================

def plot_hot_money_summary(hot_df: pd.DataFrame, height: int = 450) -> go.Figure:
    """游资操作汇总图"""
    if hot_df.empty:
        return go.Figure()

    summary = hot_df.groupby("hot_money_name").agg(
        buy_count=("买入金额", lambda x: (x.notna() & (x > 0)).sum()),
        sell_count=("卖出金额", lambda x: (x.notna() & (x > 0)).sum()),
        total_buy=("买入金额", "sum"),
        total_sell=("卖出金额", "sum"),
    ).reset_index()
    summary["net"] = summary["total_buy"].fillna(0) - summary["total_sell"].fillna(0)

    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=summary["hot_money_name"], x=summary["total_buy"], name="买入",
        orientation="h", text=[_fmt(v) for v in summary["total_buy"]],
        textposition="outside", textfont=dict(color="#DC143C", size=10),
        marker=dict(color=UP_COLOR, opacity=0.8),
        hovertemplate="<b>%{y}</b><br>买入: %{customdata}<extra></extra>",
        customdata=[_fmt(v) for v in summary["total_buy"]],
    ))
    fig.add_trace(go.Bar(
        y=summary["hot_money_name"], x=-summary["total_sell"], name="卖出",
        orientation="h", text=[_fmt(v) for v in summary["total_sell"]],
        textposition="outside", textfont=dict(color="#228B22", size=10),
        marker=dict(color=DOWN_COLOR, opacity=0.8),
        hovertemplate="<b>%{y}</b><br>卖出: %{customdata}<extra></extra>",
        customdata=[_fmt(v) for v in summary["total_sell"]],
    ))
    fig.update_layout(
        **LAYOUT_DARK,
        title=dict(text="游资买卖汇总", font=dict(size=16, color=TITLE_COLOR), x=0.5),
        height=height, barmode="relative",
        xaxis_title="买入 ← → 卖出", margin=dict(t=50, l=10, r=10, b=10),
    )
    return fig


# ============================================================
# 8. 预测区间图
# ============================================================

def plot_prediction_range(df: pd.DataFrame, prediction: dict, height: int = 400) -> go.Figure:
    """预测区间 + 最近K线"""
    if df.empty or not prediction:
        return go.Figure()

    recent = df.tail(30).copy()

    fig = go.Figure()
    fig.update_xaxes(XAXIS_CONFIG)

    fig.add_trace(go.Candlestick(
        x=recent["date"], open=recent["open"], high=recent["high"],
        low=recent["low"], close=recent["close"],
        name="近30日K线",
        increasing=dict(line=dict(color=UP_COLOR, width=1), fillcolor=UP_COLOR),
        decreasing=dict(line=dict(color=DOWN_COLOR, width=1), fillcolor=DOWN_COLOR),
    ))

    # 预测区间
    last_date = recent["date"].iloc[-1]
    next_date = last_date + pd.Timedelta(days=1)
    close = prediction.get("close", recent["close"].iloc[-1])
    rng = prediction.get("range", "")

    if rng and "~" in rng:
        parts = rng.split("~")
        try:
            lo, hi = float(parts[0].strip()), float(parts[1].strip())
            fig.add_shape(type="rect", x0=next_date - pd.Timedelta(hours=12),
                          x1=next_date + pd.Timedelta(hours=12),
                          y0=lo, y1=hi,
                          fillcolor="rgba(255,215,0,0.15)",
                          line=dict(color="#FFD700", width=1, dash="dash"),
                          name="预测区间")
        except (ValueError, IndexError):
            pass

    fig.add_trace(go.Scatter(
        x=[last_date, next_date],
        y=[close, close],
        mode="lines+markers",
        line=dict(color="#FFD700", width=2, dash="dot"),
        marker=dict(size=8, color="#FFD700"),
        name=f'预测方向: {prediction.get("direction", "")}',
    ))

    fig.update_layout(
        **LAYOUT_DARK,
        title=dict(text=f'明日预测: {prediction.get("direction", "")} (置信度: {prediction.get("confidence", 0)}%)',
                   font=dict(size=14, color=TITLE_COLOR), x=0.5),
        height=height,
        margin=dict(t=50, l=10, r=10, b=10),
    )
    return fig
    
    
# ============================================================
# 9. ECharts K线图（支持缩放+拖动）
# ============================================================

def _build_marklines(sr: dict) -> list:
    """把支撑/压力位转成 ECharts markLine 数据"""
    if not sr:
        return []
    lines = []
    for s in sr.get("supports", []):
        lines.append({"yAxis": s["price"], "label": {"formatter": f"支撑 {s['label']} ¥{s['price']}", "color": "#34D399", "fontSize": 10, "position": "end"}})
    for r in sr.get("resistances", []):
        lines.append({"yAxis": r["price"], "label": {"formatter": f"压力 {r['label']} ¥{r['price']}", "color": "#F87171", "fontSize": 10, "position": "end"}})
    return lines

def plot_kline_echarts(df: pd.DataFrame, title: str = "K线图",
                       ma_lines: list = None, height: int = 500,
                       sr_levels: dict = None) -> str:
    """
    生成 ECharts K线图 HTML（支持缩放+拖动）
    返回 HTML 字符串，用 components.html 渲染
    """
    import json
    
    if df.empty:
        return "<div style='color:#94A3B8;text-align:center;padding:40px;'>暂无K线数据</div>"
    
    if ma_lines is None:
        ma_lines = [5, 20, 60]
    
    # 准备数据
    dates = df["date"].dt.strftime("%Y-%m-%d").tolist()
    
    # OHLC 数据 [open, close, low, high]
    ohlc_data = []
    for _, row in df.iterrows():
        ohlc_data.append([
            round(row["open"], 2),
            round(row["close"], 2),
            round(row["low"], 2),
            round(row["high"], 2)
        ])
    
    # 成交量数据
    volume_data = df["volume"].tolist()
    
    # 成交量颜色（红涨绿跌）
    volume_colors = []
    for i, row in df.iterrows():
        if row["close"] >= row["open"]:
            volume_colors.append("#DC143C")
        else:
            volume_colors.append("#228B22")
    
    # 计算均线
    ma_data = {}
    ma_colors = {5: "#FFD700", 20: "#60A5FA", 60: "#F87171"}
    for p in ma_lines:
        ma_data[f"MA{p}"] = df["close"].rolling(p).mean().round(2).tolist()
    
    # 构建 ECharts option
    option = {
        "backgroundColor": "transparent",
        "title": {
            "text": title,
            "left": "center",
            "top": 0,
            "textStyle": {"color": "#F1F5F9", "fontSize": 16, "fontWeight": 600}
        },
        "tooltip": {
            "trigger": "axis",
            "axisPointer": {"type": "cross"},
            "backgroundColor": "rgba(30, 41, 59, 0.92)",
            "borderColor": "#334155",
            "borderWidth": 1,
            "textStyle": {"color": "#E2E8F0", "fontSize": 12}
        },
        "legend": {
            "data": ["K线"] + [f"MA{p}" for p in ma_lines] + ["成交量"],
            "top": 30,
            "textStyle": {"color": "#94A3B8", "fontSize": 11},
            "itemWidth": 12,
            "itemHeight": 8
        },
        "grid": [
            {"left": "5%", "right": "3%", "top": "20%", "height": "52%"},
            {"left": "5%", "right": "3%", "top": "76%", "height": "14%"}
        ],
        "xAxis": [
            {
                "type": "category",
                "data": dates,
                "gridIndex": 0,
                "axisLabel": {"color": "#94A3B8", "fontSize": 10, "interval": 10},
                "axisLine": {"lineStyle": {"color": "#334155"}},
                "splitLine": {"show": False}
            },
            {
                "type": "category",
                "data": dates,
                "gridIndex": 1,
                "axisLabel": {"show": False},
                "axisLine": {"lineStyle": {"color": "#334155"}},
                "splitLine": {"show": False}
            }
        ],
        "yAxis": [
            {
                "scale": True,
                "gridIndex": 0,
                "axisLabel": {"color": "#94A3B8", "fontSize": 10},
                "splitLine": {"lineStyle": {"color": "rgba(255,255,255,0.06)"}}
            },
            {
                "scale": True,
                "gridIndex": 1,
                "axisLabel": {"color": "#94A3B8", "fontSize": 10},
                "splitLine": {"lineStyle": {"color": "rgba(255,255,255,0.06)"}}
            }
        ],
        "dataZoom": [
            {
                "type": "inside",
                "xAxisIndex": [0, 1],
                "start": 0,
                "end": 100,
                "zoomOnMouseWheel": True,
                "moveOnMouseMove": True
            },
            {
                "type": "slider",
                "xAxisIndex": [0, 1],
                "height": 16,
                "bottom": 2,
                "borderColor": "#334155",
                "backgroundColor": "rgba(30, 41, 59, 0.5)",
                "fillerColor": "rgba(212, 168, 83, 0.2)",
                "handleStyle": {"color": "#D4A853", "borderColor": "#D4A853"},
                "textStyle": {"color": "#94A3B8", "fontSize": 10}
            }
        ],
        "series": [
            {
                "name": "K线",
                "type": "candlestick",
                "data": ohlc_data,
                "xAxisIndex": 0,
                "yAxisIndex": 0,
                "itemStyle": {
                    "color": "#DC143C",
                    "color0": "#228B22",
                    "borderColor": "#DC143C",
                    "borderColor0": "#228B22",
                    "borderWidth": 1
                },
                "markLine": {
                    "silent": True,
                    "symbol": "none",
                    "lineStyle": {"color": "#D4A853", "type": "dashed", "width": 1},
                    "data": _build_marklines(sr_levels)
                }
            }
        ]
    }
    
    # 添加均线
    for p in ma_lines:
        option["series"].append({
            "name": f"MA{p}",
            "type": "line",
            "data": ma_data[f"MA{p}"],
            "xAxisIndex": 0,
            "yAxisIndex": 0,
            "smooth": True,
            "showSymbol": False,
            "lineStyle": {
                "width": 1.5,
                "color": ma_colors.get(p, "#888")
            }
        })
    
    # 添加成交量
    option["series"].append({
        "name": "成交量",
        "type": "bar",
        "data": volume_data,
        "xAxisIndex": 1,
        "yAxisIndex": 1,
        "itemStyle": {"color": volume_colors, "opacity": 0.5},
        "barWidth": "60%"
    })
    
    # 序列化为 JSON
    option_json = json.dumps(option, ensure_ascii=False)
    
    return f'''
    <div id="kline-echarts" style="width:100%;height:{height}px;"></div>
    <script src="https://cdn.jsdelivr.net/npm/echarts@5.5.1/dist/echarts.min.js">
    </script>
    <script>
        (function() {{
            var dom = document.getElementById('kline-echarts');
            var chart = echarts.init(dom, 'dark');
            var option = {option_json};
            chart.setOption(option);
            window.addEventListener('resize', function() {{ chart.resize(); }});
        }})();
    </script>
    '''
# ============================================================
# 10. ECharts 技术指标图（支持缩放+拖动）
# ============================================================

def plot_indicator_echarts(df: pd.DataFrame, indicator_type: str, height: int = 280) -> str:
    """
    生成 ECharts 技术指标图（支持缩放+拖动）
    indicator_type: 'MACD', 'KDJ', 'RSI', 'BOLL'
    返回 HTML 字符串，用 components.html 渲染
    """
    import json
    
    if df.empty:
        return "<div style='color:#94A3B8;text-align:center;padding:20px;'>暂无数据</div>"
    
    dates = df["date"].dt.strftime("%Y-%m-%d").tolist()
    
    if indicator_type == "MACD":
        if "DIF" not in df.columns or "DEA" not in df.columns:
            return "<div style='color:#94A3B8;text-align:center;padding:20px;'>MACD 数据缺失</div>"
        
        dif = df["DIF"].round(2).tolist()
        dea = df["DEA"].round(2).tolist()
        macd = df["MACD"].round(2).tolist()
        macd_colors = ["#DC143C" if v >= 0 else "#228B22" for v in macd]
        
        option = {
            "title": {
                "text": "MACD (12, 26, 9)",
                "left": "center",
                "top": 0,
                "textStyle": {"color": "#F1F5F9", "fontSize": 14, "fontWeight": 600}
            },
            "tooltip": {
                "trigger": "axis",
                "axisPointer": {"type": "cross"},
                "backgroundColor": "rgba(30, 41, 59, 0.9)",
                "borderColor": "#334155",
                "textStyle": {"color": "#E2E8F0", "fontSize": 11}
            },
            "legend": {
                "data": ["DIF", "DEA", "MACD"],
                "top": 25,
                "textStyle": {"color": "#94A3B8", "fontSize": 10},
                "itemWidth": 10,
                "itemHeight": 6
            },
            "grid": {"left": "5%", "right": "3%", "top": "18%", "bottom": "8%", "containLabel": True},
            "xAxis": {
                "type": "category",
                "data": dates,
                "axisLabel": {"color": "#94A3B8", "fontSize": 9, "interval": 15},
                "axisLine": {"lineStyle": {"color": "#334155"}},
                "splitLine": {"show": False}
            },
            "yAxis": {
                "scale": True,
                "axisLabel": {"color": "#94A3B8", "fontSize": 9},
                "splitLine": {"lineStyle": {"color": "rgba(255,255,255,0.05)"}}
            },
            "dataZoom": [
                {"type": "inside", "start": 0, "end": 100, "zoomOnMouseWheel": True},
                {"type": "slider", "height": 12, "bottom": 0, "borderColor": "#334155",
                 "backgroundColor": "rgba(30, 41, 59, 0.5)",
                 "fillerColor": "rgba(212, 168, 83, 0.15)",
                 "handleStyle": {"color": "#D4A853"}, "textStyle": {"color": "#94A3B8", "fontSize": 9}}
            ],
            "series": [
                {"name": "DIF", "type": "line", "data": dif, "smooth": True, "showSymbol": False,
                 "lineStyle": {"width": 1.5, "color": "#FFD700"}},
                {"name": "DEA", "type": "line", "data": dea, "smooth": True, "showSymbol": False,
                 "lineStyle": {"width": 1.5, "color": "#60A5FA"}},
                {"name": "MACD", "type": "bar", "data": macd,
                 "itemStyle": {"color": macd_colors, "opacity": 0.6}, "barWidth": "40%"}
            ]
        }
    
    elif indicator_type == "KDJ":
        if "K" not in df.columns or "D" not in df.columns:
            return "<div style='color:#94A3B8;text-align:center;padding:20px;'>KDJ 数据缺失</div>"
        
        k = df["K"].round(1).tolist()
        d = df["D"].round(1).tolist()
        j = df["J"].round(1).tolist()
        
        option = {
            "title": {
                "text": "KDJ (9, 3, 3)",
                "left": "center",
                "top": 0,
                "textStyle": {"color": "#F1F5F9", "fontSize": 14, "fontWeight": 600}
            },
            "tooltip": {
                "trigger": "axis",
                "axisPointer": {"type": "cross"},
                "backgroundColor": "rgba(30, 41, 59, 0.9)",
                "borderColor": "#334155",
                "textStyle": {"color": "#E2E8F0", "fontSize": 11}
            },
            "legend": {
                "data": ["K", "D", "J"],
                "top": 25,
                "textStyle": {"color": "#94A3B8", "fontSize": 10},
                "itemWidth": 10,
                "itemHeight": 6
            },
            "grid": {"left": "5%", "right": "3%", "top": "18%", "bottom": "8%", "containLabel": True},
            "xAxis": {
                "type": "category",
                "data": dates,
                "axisLabel": {"color": "#94A3B8", "fontSize": 9, "interval": 15},
                "axisLine": {"lineStyle": {"color": "#334155"}},
                "splitLine": {"show": False}
            },
            "yAxis": {
                "min": 0, "max": 100,
                "axisLabel": {"color": "#94A3B8", "fontSize": 9},
                "splitLine": {"lineStyle": {"color": "rgba(255,255,255,0.05)"}}
            },
            "dataZoom": [
                {"type": "inside", "start": 0, "end": 100, "zoomOnMouseWheel": True},
                {"type": "slider", "height": 12, "bottom": 0, "borderColor": "#334155",
                 "backgroundColor": "rgba(30, 41, 59, 0.5)",
                 "fillerColor": "rgba(212, 168, 83, 0.15)",
                 "handleStyle": {"color": "#D4A853"}, "textStyle": {"color": "#94A3B8", "fontSize": 9}}
            ],
            "series": [
                {"name": "K", "type": "line", "data": k, "smooth": True, "showSymbol": False,
                 "lineStyle": {"width": 1.5, "color": "#FFD700"}},
                {"name": "D", "type": "line", "data": d, "smooth": True, "showSymbol": False,
                 "lineStyle": {"width": 1.5, "color": "#60A5FA"}},
                {"name": "J", "type": "line", "data": j, "smooth": True, "showSymbol": False,
                 "lineStyle": {"width": 1, "color": "#F87171", "type": "dashed"}}
            ]
        }
    
    elif indicator_type == "RSI":
        if "RSI6" not in df.columns:
            return "<div style='color:#94A3B8;text-align:center;padding:20px;'>RSI 数据缺失</div>"
        
        rsi6 = df["RSI6"].round(1).tolist()
        rsi12 = df["RSI12"].round(1).tolist() if "RSI12" in df.columns else []
        rsi24 = df["RSI24"].round(1).tolist() if "RSI24" in df.columns else []
        
        legend_data = ["RSI6"]
        series = [
            {"name": "RSI6", "type": "line", "data": rsi6, "smooth": True, "showSymbol": False,
             "lineStyle": {"width": 1.5, "color": "#60A5FA"}}
        ]
        if rsi12:
            legend_data.append("RSI12")
            series.append({"name": "RSI12", "type": "line", "data": rsi12, "smooth": True, "showSymbol": False,
                          "lineStyle": {"width": 1.5, "color": "#FFD700"}})
        if rsi24:
            legend_data.append("RSI24")
            series.append({"name": "RSI24", "type": "line", "data": rsi24, "smooth": True, "showSymbol": False,
                          "lineStyle": {"width": 1.2, "color": "#F87171", "type": "dashed"}})
        
        option = {
            "title": {
                "text": "RSI (6, 12, 24)",
                "left": "center",
                "top": 0,
                "textStyle": {"color": "#F1F5F9", "fontSize": 14, "fontWeight": 600}
            },
            "tooltip": {
                "trigger": "axis",
                "axisPointer": {"type": "cross"},
                "backgroundColor": "rgba(30, 41, 59, 0.9)",
                "borderColor": "#334155",
                "textStyle": {"color": "#E2E8F0", "fontSize": 11}
            },
            "legend": {
                "data": legend_data,
                "top": 25,
                "textStyle": {"color": "#94A3B8", "fontSize": 10},
                "itemWidth": 10,
                "itemHeight": 6
            },
            "grid": {"left": "5%", "right": "3%", "top": "18%", "bottom": "8%", "containLabel": True},
            "xAxis": {
                "type": "category",
                "data": dates,
                "axisLabel": {"color": "#94A3B8", "fontSize": 9, "interval": 15},
                "axisLine": {"lineStyle": {"color": "#334155"}},
                "splitLine": {"show": False}
            },
            "yAxis": {
                "min": 0, "max": 100,
                "axisLabel": {"color": "#94A3B8", "fontSize": 9},
                "splitLine": {"lineStyle": {"color": "rgba(255,255,255,0.05)"}}
            },
            "dataZoom": [
                {"type": "inside", "start": 0, "end": 100, "zoomOnMouseWheel": True},
                {"type": "slider", "height": 12, "bottom": 0, "borderColor": "#334155",
                 "backgroundColor": "rgba(30, 41, 59, 0.5)",
                 "fillerColor": "rgba(212, 168, 83, 0.15)",
                 "handleStyle": {"color": "#D4A853"}, "textStyle": {"color": "#94A3B8", "fontSize": 9}}
            ],
            "series": series
        }
    
    elif indicator_type == "BOLL":
        if "BOLL_UP" not in df.columns:
            return "<div style='color:#94A3B8;text-align:center;padding:20px;'>BOLL 数据缺失</div>"
        
        upper = df["BOLL_UP"].round(2).tolist()
        mid = df["BOLL_MID"].round(2).tolist()
        lower = df["BOLL_DN"].round(2).tolist()
        close = df["close"].round(2).tolist()
        
        option = {
            "title": {
                "text": "BOLL 布林带 (20, 2)",
                "left": "center",
                "top": 0,
                "textStyle": {"color": "#F1F5F9", "fontSize": 14, "fontWeight": 600}
            },
            "tooltip": {
                "trigger": "axis",
                "axisPointer": {"type": "cross"},
                "backgroundColor": "rgba(30, 41, 59, 0.9)",
                "borderColor": "#334155",
                "textStyle": {"color": "#E2E8F0", "fontSize": 11}
            },
            "legend": {
                "data": ["上轨", "中轨", "下轨", "收盘价"],
                "top": 25,
                "textStyle": {"color": "#94A3B8", "fontSize": 10},
                "itemWidth": 10,
                "itemHeight": 6
            },
            "grid": {"left": "5%", "right": "3%", "top": "18%", "bottom": "8%", "containLabel": True},
            "xAxis": {
                "type": "category",
                "data": dates,
                "axisLabel": {"color": "#94A3B8", "fontSize": 9, "interval": 15},
                "axisLine": {"lineStyle": {"color": "#334155"}},
                "splitLine": {"show": False}
            },
            "yAxis": {
                "scale": True,
                "axisLabel": {"color": "#94A3B8", "fontSize": 9},
                "splitLine": {"lineStyle": {"color": "rgba(255,255,255,0.05)"}}
            },
            "dataZoom": [
                {"type": "inside", "start": 0, "end": 100, "zoomOnMouseWheel": True},
                {"type": "slider", "height": 12, "bottom": 0, "borderColor": "#334155",
                 "backgroundColor": "rgba(30, 41, 59, 0.5)",
                 "fillerColor": "rgba(212, 168, 83, 0.15)",
                 "handleStyle": {"color": "#D4A853"}, "textStyle": {"color": "#94A3B8", "fontSize": 9}}
            ],
            "series": [
                {"name": "上轨", "type": "line", "data": upper, "smooth": True, "showSymbol": False,
                 "lineStyle": {"width": 1, "color": "#F87171", "type": "dashed"}},
                {"name": "中轨", "type": "line", "data": mid, "smooth": True, "showSymbol": False,
                 "lineStyle": {"width": 1.5, "color": "#FFD700"}},
                {"name": "下轨", "type": "line", "data": lower, "smooth": True, "showSymbol": False,
                 "lineStyle": {"width": 1, "color": "#34D399", "type": "dashed"}},
                {"name": "收盘价", "type": "line", "data": close, "smooth": True, "showSymbol": False,
                 "lineStyle": {"width": 1.5, "color": "#E2E8F0"}}
            ]
        }
    
    else:
        return "<div style='color:#94A3B8;text-align:center;padding:20px;'>不支持的指标类型</div>"
    
    option_json = json.dumps(option, ensure_ascii=False)
    chart_id = f"indicator-{indicator_type.lower()}-{abs(hash(str(df.index[-1])))}"
    
    return f'''
    <div id="{chart_id}" style="width:100%;height:{height}px;"></div>
    <script src="https://cdn.jsdelivr.net/npm/echarts@5.5.1/dist/echarts.min.js">
    </script>
    <script>
        (function() {{
            var dom = document.getElementById('{chart_id}');
            var chart = echarts.init(dom, 'dark');
            var option = {option_json};
            chart.setOption(option);
            window.addEventListener('resize', function() {{ chart.resize(); }});
        }})();
    </script>
    '''
