"""工具函数"""
import math


def safe_num(v, default="—"):
    """防呆：None/NaN/inf → default（默认"—"），否则返回 float 数值。"""
    if v is None:
        return default
    try:
        f = float(v)
        if math.isnan(f) or math.isinf(f):
            return default
        return f
    except (ValueError, TypeError):
        return default


def fmt_cn(num, decimals=2):
    """数字中文格式化：自动转万/亿"""
    n = safe_num(num, None)
    if n is None:
        return "—"

    sign = "-" if n < 0 else ""
    n = abs(n)

    if n >= 1e8:
        return f"{sign}{n/1e8:.{decimals}f}亿"
    elif n >= 1e4:
        return f"{sign}{n/1e4:.{decimals}f}万"
    elif n >= 1000:
        return f"{sign}{n:,.0f}"
    elif n >= 1:
        return f"{sign}{n:.{decimals}f}"
    else:
        return f"{sign}{n:.{max(decimals,4)}f}"


def fmt_pct(num, decimals=2):
    """百分比格式化"""
    n = safe_num(num, None)
    if n is None:
        return "—"
    return f"{n:+.{decimals}f}%"


def fmt_time(ts=None):
    """时间格式化 HH:MM:SS"""
    from datetime import datetime
    if ts is None:
        ts = datetime.now()
    return ts.strftime("%H:%M:%S")


def fmt_mv(num, decimals=2):
    """市值格式化"""
    return fmt_cn(num, decimals)
