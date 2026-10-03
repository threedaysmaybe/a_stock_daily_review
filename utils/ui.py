"""共享 UI 组件 — 统一视觉层次：结论卡片 + 区块标题 + 全局样式。"""
import streamlit as st

# 涨跌颜色（深色主题下用亮色更醒目）
UP = "#ef4444"      # 涨（红）
DOWN = "#22c55e"    # 跌（绿）
ACCENT = "#3B82F6"  # 强调（蓝）
WARN = "#f59e0b"    # 警告（橙）

_CSS = """
<style>
/* 标题层次 */
h1 { font-size: 1.7rem !important; font-weight: 800 !important; }
h2 {
    font-size: 1.25rem !important; font-weight: 700 !important;
    border-left: 4px solid #3B82F6; padding-left: 10px; margin-top: 1.2rem;
}
h3 { font-size: 1.05rem !important; font-weight: 600 !important; color: #CBD5E1 !important; }

/* metric 数字更醒目 */
[data-testid="stMetricValue"] { font-size: 1.5rem !important; font-weight: 800 !important; }
[data-testid="stMetricLabel"] { font-size: 0.78rem !important; color: #94A3B8 !important; }
[data-testid="stMetricDelta"] { font-size: 0.9rem !important; }

/* 结论卡片：突出核心判断 */
.conclusion-card {
    background: linear-gradient(135deg, #1E293B, #111827);
    border: 1px solid #334155;
    border-left: 5px solid #3B82F6;
    border-radius: 10px;
    padding: 14px 20px;
    margin: 6px 0 18px 0;
}
.conclusion-card.bull { border-left-color: #ef4444; background: linear-gradient(135deg, #2a1a1e, #111827); }
.conclusion-card.bear { border-left-color: #22c55e; background: linear-gradient(135deg, #12261c, #111827); }
.conclusion-card .c-title { font-size: 1.15rem; font-weight: 800; color: #F1F5F9; margin-bottom: 5px; }
.conclusion-card .c-body { font-size: 0.95rem; color: #CBD5E1; line-height: 1.6; }
.conclusion-card .c-body b { color: #F1F5F9; }

/* 涨跌文字 */
.up { color: #ef4444; font-weight: 700; }
.down { color: #22c55e; font-weight: 700; }
.muted { color: #64748B; font-size: 0.85rem; }
</style>
"""


def inject_css():
    """注入全局样式（每个页面开头调用一次）。"""
    st.markdown(_CSS, unsafe_allow_html=True)


def conclusion(title: str, body: str, tone: str = "neutral"):
    """结论卡片：突出页面核心判断。
    tone: bull(看多红) / bear(看空绿) / neutral(中性蓝)
    """
    cls = {"bull": "bull", "bear": "bear"}.get(tone, "")
    st.markdown(
        f'<div class="conclusion-card {cls}">'
        f'<div class="c-title">{title}</div>'
        f'<div class="c-body">{body}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def pct_color(v):
    """涨跌值 → 红/绿 class。"""
    try:
        v = float(v)
    except (TypeError, ValueError):
        return "muted"
    if v > 0:
        return "up"
    if v < 0:
        return "down"
    return "muted"
