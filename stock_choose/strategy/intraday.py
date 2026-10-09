"""分时因子（基于真实分钟数据，akshare 新浪接口）。

从分时分钟数据提取日内微观结构特征：
  1. 多空强度：收盘价 vs 分时均价线（均价=累计成交额/累计成交量，全天成本线）
  2. 抛压占比：下跌分钟的量能占比（放量下跌=抛压大）
  3. 尾盘异动：尾盘30分钟走势（缩量拉升=诱多嫌疑，跳水=出货风险）

数据真实：分钟数据来自 akshare 新浪接口。注意新浪分钟数据仅保留最近几个交易日，
无法做长期历史回测，只能用进化闭环（每日 IC）校准参数。
"""
import time

import numpy as np
import pandas as pd

try:
    import akshare as ak
    AK_AVAILABLE = True
except ImportError:
    AK_AVAILABLE = False


def to_sina_symbol(code: str) -> str:
    num = code.split(".")[0]
    return f"sh{num}" if num.startswith("6") else f"sz{num}"


def fetch_intraday(code: str, period: str = "1") -> pd.DataFrame:
    """拉当天分时分钟数据（真实数据）。"""
    df = ak.stock_zh_a_minute(symbol=to_sina_symbol(code), period=period, adjust="")
    if df is None or df.empty:
        return None
    df["day"] = pd.to_datetime(df["day"])  # 新浪返回字符串，转 datetime
    # 数值列转 float（新浪返回字符串，pandas3 不自动转换）
    for col in ["open", "high", "low", "close", "volume", "amount"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    today = df["day"].dt.date.max()
    return df[df["day"].dt.date == today].reset_index(drop=True)


def intraday_features(code: str, retry: int = 2) -> dict:
    """计算分时特征，返回 {'多空强度','抛压占比','尾盘涨幅','尾盘量能'}。"""
    if not AK_AVAILABLE:
        return {}
    for attempt in range(retry):
        try:
            df = fetch_intraday(code)
            if df is None or len(df) < 30:
                return {}
            # 分时均价线（vwap）
            cum_amount = df["amount"].cumsum()
            cum_volume = df["volume"].cumsum()
            vwap = cum_amount / cum_volume.replace(0, np.nan)

            close = df["close"].iloc[-1]
            strength = close / vwap.iloc[-1] - 1  # 多空强度（正=收盘在均价上方）

            # 抛压占比
            df = df.copy()
            df["ret"] = df["close"].pct_change()
            down_vol = df.loc[df["ret"] < 0, "volume"].sum()
            up_vol = df.loc[df["ret"] > 0, "volume"].sum()
            total = down_vol + up_vol
            down_ratio = down_vol / total if total > 0 else 0.5

            # 尾盘异动（最后30分钟）
            tail = df.tail(30)
            tail_ret = tail["close"].iloc[-1] / tail["close"].iloc[0] - 1
            tail_vol = tail["volume"].mean() / (df["volume"].mean() + 1e-9)

            return {
                "多空强度": float(strength),
                "抛压占比": float(down_ratio),
                "尾盘涨幅": float(tail_ret),
                "尾盘量能": float(tail_vol),
            }
        except Exception:  # noqa: BLE001
            time.sleep(1)
    return {}


def intraday_signals(code: str) -> dict:
    """分时信号（布尔）：多方占优 / 抛压过大 / 尾盘诱多 / 尾盘跳水。"""
    f = intraday_features(code)
    if not f:
        return {}

    signals = {}
    if f["多空强度"] > 0.003:          # 收盘价高于分时均价 0.3%
        signals["多方占优"] = True
    if f["抛压占比"] > 0.6:            # 下跌量能占比 > 60%
        signals["抛压过大"] = True
    if f["尾盘涨幅"] > 0.01 and f["尾盘量能"] < 0.8:   # 尾盘缩量拉升 = 诱多
        signals["尾盘诱多"] = True
    if f["尾盘涨幅"] < -0.02:          # 尾盘跳水
        signals["尾盘跳水"] = True
    return signals
