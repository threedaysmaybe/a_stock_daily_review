"""外围市场风险信号。

9:00 推送，综合三类「先于 A股」的信号：
  - 美股昨晚收盘（领先约 4-5 小时）
  - 日韩昨天收盘（历史走势）
  - 日韩当天开盘表现（8:00 开盘，9:00 已交易 1 小时，领先 A股 30 分钟）
"""
import akshare as ak
import numpy as np


def _last_ret(series) -> float:
    """最近两个非 0 收盘价的涨跌（0/NaN 视为无效）。"""
    s = series.replace(0, np.nan).dropna()
    if len(s) < 2:
        return None
    return float(s.iloc[-1] / s.iloc[-2] - 1)


def _today_open_ret(df) -> float:
    """当天开盘价相对昨日收盘的涨跌（日韩当天开盘表现）。"""
    close = df["close"].replace(0, np.nan).dropna()
    if len(close) < 1:
        return None
    op = float(df.iloc[-1].get("open", 0))
    if op <= 0:
        return None
    return float(op / close.iloc[-1] - 1)


def get_overseas_signal() -> dict:
    """获取外围信号：美股昨晚收盘 + 日韩昨天收盘 + 日韩当天开盘。失败字段忽略。"""
    sig = {}
    # 美股昨晚收盘
    try:
        sig["us_nasdaq"] = _last_ret(ak.index_us_stock_sina(symbol=".IXIC")["close"])
    except Exception:  # noqa: BLE001
        pass
    try:
        sig["us_sp500"] = _last_ret(ak.index_us_stock_sina(symbol=".INX")["close"])
    except Exception:  # noqa: BLE001
        pass
    # 日韩（新浪环球指数，key 为中文名）：昨天收盘 + 当天开盘
    for name, key in [("首尔综合指数", "kr"), ("日经225指数", "jp")]:
        try:
            df = ak.index_global_hist_sina(symbol=name)
            sig[f"{key}_prev"] = _last_ret(df["close"])   # 昨日收盘涨跌
            sig[f"{key}_open"] = _today_open_ret(df)       # 今日开盘涨跌
        except Exception:  # noqa: BLE001
            pass
    return sig if sig else None


def overseas_risk(sig: dict) -> bool:
    """综合外围风险：美股昨晚大跌 或 日韩当天开盘大跌 → 空仓。

    美股回测：跌超 2% A股次日 -0.66%、跌超 3% -1.51%。
    日韩当天开盘跌超 2% 同理（领先 A股 30 分钟）。
    """
    if not sig:
        return False
    us = min([v for k, v in sig.items() if k.startswith("us_") and v is not None] or [0.0])
    asia_open = min([v for k, v in sig.items() if k.endswith("_open") and v is not None] or [0.0])
    return us < -0.02 or asia_open < -0.02
