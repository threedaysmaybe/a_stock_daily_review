"""精确技术形态因子（基于真实历史 K 线，数据源：akshare 新浪接口）。

两个核心形态：
  1. 涨停回调不破：近期涨停后，回调洗盘最低价未跌破涨停起始线（涨停板战法）
  2. 底部放量：近期显著放量（>2 倍均量）且价格处于相对底部（疑似主力进场）

数据真实：所有 K 线来自 akshare 新浪前复权日线，无任何模拟数据。
"""
import time

import numpy as np
import pandas as pd

from stock_choose.strategy import indicators

try:
    import akshare as ak
    AK_AVAILABLE = True
except ImportError:
    AK_AVAILABLE = False


def limit_pct(code: str) -> float:
    """涨停幅度：主板 10%，创业板/科创板 20%。"""
    num = code.split(".")[0]
    if num.startswith(("300", "301", "688", "689")):
        return 0.20
    return 0.10


def to_sina_symbol(code: str) -> str:
    """问财代码(600519.SH) → 新浪代码(sh600519)。"""
    num = code.split(".")[0]
    return f"sh{num}" if num.startswith("6") else f"sz{num}"


def fetch_history(code: str, days: int = 120) -> pd.DataFrame:
    """拉取历史前复权日线（真实数据）。返回 DataFrame，含 open/high/low/close/volume。"""
    if not AK_AVAILABLE:
        raise RuntimeError("未安装 akshare")
    df = ak.stock_zh_a_daily(symbol=to_sina_symbol(code), adjust="qfq")
    df = df.tail(days).reset_index(drop=True)
    return df


def detect_limit_up(df: pd.DataFrame, code: str) -> pd.Series:
    """返回每天是否涨停的布尔序列（真实涨停价判定）。"""
    lp = limit_pct(code)
    prev_close = df["close"].shift(1)
    pct = (df["close"] - prev_close) / prev_close
    return pct >= lp - 0.005  # 0.5% 容差，兼容四舍五入


def is_pullback_not_break(df: pd.DataFrame, code: str, window: int = 10) -> bool:
    """涨停回调不破：近 window 天内出现涨停，涨停后回调最低价未跌破涨停起始线。

    涨停起始线 = 涨停当日开盘价（保守取开盘价）。
    """
    if len(df) < 5:
        return False

    limit_days = detect_limit_up(df, code)
    for i in range(max(1, len(df) - window), len(df) - 1):
        if not limit_days.iloc[i]:
            continue
        start_line = df["open"].iloc[i]  # 涨停起始线
        after = df.iloc[i + 1:]
        after_high = after["high"].max()
        after_low = after["low"].min()
        # 涨停后冲高（突破涨停收盘价），且回调最低不破起始线
        if after_high > df["close"].iloc[i] and after_low >= start_line * 0.99:
            return True
    return False


def is_bottom_volume(df: pd.DataFrame, code: str, window: int = 20) -> bool:
    """底部放量：近 window 天内出现放量（>2 倍前 20 日均量），且价格处于相对底部。

    底部判定：放量当日收盘价相对近 60 天最高价回撤 > 25%。
    """
    if len(df) < 40:
        return False

    vol = df["volume"]
    # 前 20 日均量（滚动）
    ma20_vol = vol.rolling(20).mean()
    # 近 60 天最高收盘价
    high_60 = df["close"].rolling(60).max()

    for i in range(max(20, len(df) - window), len(df)):
        if pd.isna(ma20_vol.iloc[i]):
            continue
        # 放量：成交量 >= 2 倍前 20 日均量
        if vol.iloc[i] >= 2.0 * ma20_vol.iloc[i - 1]:
            # 底部：放量日收盘价相对近 60 天高点回撤 > 25%
            if high_60.iloc[i] > 0 and df["close"].iloc[i] / high_60.iloc[i] <= 0.75:
                return True
    return False


def is_volume_shrink_pullback(df: pd.DataFrame, code: str, window: int = 10) -> bool:
    """缩量回调：涨停后回调时成交量显著萎缩（健康洗盘，非出货）。"""
    if len(df) < 5:
        return False
    limit_days = detect_limit_up(df, code)
    for i in range(max(1, len(df) - window), len(df) - 1):
        if not limit_days.iloc[i]:
            continue
        limit_vol = df["volume"].iloc[i]
        after = df.iloc[i + 1:]
        # 涨停后回调（最低价跌破涨停收盘），且回调期最大量 < 涨停日量的 60%（缩量洗盘）
        if after["low"].min() < df["close"].iloc[i] and after["volume"].max() < 0.6 * limit_vol:
            return True
    return False


def is_volume_upper_shadow(df: pd.DataFrame, window: int = 10) -> bool:
    """放量上影线（风险提示）：近期放量且收长上影线，冲高回落，疑似主力出货。"""
    if len(df) < 25:
        return False
    vol = df["volume"]
    ma20 = vol.rolling(20).mean()
    upper_shadow = df["high"] - df[["open", "close"]].max(axis=1)
    body = (df["close"] - df["open"]).abs()
    rng = df["high"] - df["low"]

    for i in range(max(20, len(df) - window), len(df)):
        if pd.isna(ma20.iloc[i - 1]):
            continue
        # 放量：>= 1.5 倍前 20 日均量
        if vol.iloc[i] < 1.5 * ma20.iloc[i - 1]:
            continue
        # 长上影线：上影线占比 > 40% 且上影线 > 实体
        if rng.iloc[i] > 0 and upper_shadow.iloc[i] / rng.iloc[i] > 0.4 \
                and upper_shadow.iloc[i] > body.iloc[i]:
            return True
    return False


def is_ma_bullish(df: pd.DataFrame) -> bool:
    """均线多头排列：5日 > 10日 > 20日均线。"""
    if len(df) < 20:
        return False
    ma5 = df["close"].rolling(5).mean().iloc[-1]
    ma10 = df["close"].rolling(10).mean().iloc[-1]
    ma20 = df["close"].rolling(20).mean().iloc[-1]
    return bool(ma5 > ma10 > ma20)


def detect_patterns(code: str, days: int = 120, window: int = 10,
                    retry: int = 3) -> dict:
    """拉取历史 K 线并检测形态（真实数据）。

    返回：
      正面：涨停回调不破 / 底部放量 / 缩量回调 / 均线多头
      风险：放量上影线
    """
    for attempt in range(retry):
        try:
            df = fetch_history(code, days)
            result = {
                "涨停回调不破": bool(is_pullback_not_break(df, code, window)),
                "底部放量": bool(is_bottom_volume(df, code)),
                "缩量回调": bool(is_volume_shrink_pullback(df, code, window)),
                "均线多头": bool(is_ma_bullish(df)),
                "放量上影线": bool(is_volume_upper_shadow(df, window)),
            }
            # 技术指标（复用同一份日线，避免重复拉取）
            result.update(indicators.detect_indicators(df))
            return result
        except Exception as e:  # noqa: BLE001
            if attempt == retry - 1:
                return {"error": str(e)}
            time.sleep(1)
    return {"error": "拉取失败"}
