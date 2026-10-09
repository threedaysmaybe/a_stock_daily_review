"""经典技术指标（MACD/KDJ/RSI/BOLL）+ 均线乖离，基于真实日线 K 线计算。

所有指标用 pandas 实现，不依赖 TA-Lib。
"""
import numpy as np
import pandas as pd


def compute_macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    """MACD：返回 (dif, dea, macd, 金叉bool序列, 死叉bool序列)。"""
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    dif = ema_fast - ema_slow
    dea = dif.ewm(span=signal, adjust=False).mean()
    macd = (dif - dea) * 2
    golden = (dif > dea) & (dif.shift(1) <= dea.shift(1))
    death = (dif < dea) & (dif.shift(1) >= dea.shift(1))
    return dif, dea, macd, golden, death


def compute_kdj(df: pd.DataFrame, n: int = 9):
    """KDJ：返回 (k, d, j, 金叉bool序列)。"""
    low_n = df["low"].rolling(n).min()
    high_n = df["high"].rolling(n).max()
    rsv = (df["close"] - low_n) / (high_n - low_n).replace(0, np.nan) * 100
    rsv = rsv.fillna(50)
    k = rsv.ewm(com=2, adjust=False).mean()
    d = k.ewm(com=2, adjust=False).mean()
    j = 3 * k - 2 * d
    golden = (k > d) & (k.shift(1) <= d.shift(1))
    return k, d, j, golden


def compute_rsi(close: pd.Series, n: int = 14) -> pd.Series:
    """RSI（Wilder 平滑）。"""
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / n, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / n, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - 100 / (1 + rs)
    return rsi.fillna(50)


def compute_boll(close: pd.Series, n: int = 20):
    """布林带：返回 (中轨, 上轨, 下轨)。"""
    mid = close.rolling(n).mean()
    std = close.rolling(n).std()
    upper = mid + 2 * std
    lower = mid - 2 * std
    return mid, upper, lower


def detect_indicators(df: pd.DataFrame, lookback: int = 5) -> dict:
    """检测技术指标信号（真实日线），返回信号 dict。"""
    if len(df) < 30:
        return {}
    close = df["close"]

    _, _, _, macd_golden, macd_death = compute_macd(close)
    _, _, j, kdj_golden = compute_kdj(df)
    rsi = compute_rsi(close)
    mid, upper, _ = compute_boll(close)

    ma5 = close.rolling(5).mean().iloc[-1]
    ma20 = close.rolling(20).mean().iloc[-1]
    last_close = close.iloc[-1]

    return {
        # 技术指标信号（近 lookback 日出现过金叉/死叉）
        "MACD金叉": bool(macd_golden.iloc[-lookback:].any()),
        "MACD死叉": bool(macd_death.iloc[-lookback:].any()),
        "KDJ金叉": bool(kdj_golden.iloc[-lookback:].any()),
        "KDJ超买": bool(j.iloc[-1] > 100),
        "KDJ超卖": bool(j.iloc[-1] < 0),
        "RSI超买": bool(rsi.iloc[-1] > 70),
        "RSI超卖": bool(rsi.iloc[-1] < 30),
        "BOLL站上中轨": bool(last_close > mid.iloc[-1]),
        "BOLL突破上轨": bool(last_close > upper.iloc[-1]),
        # 均线乖离
        "超买乖离": bool(last_close / ma5 - 1 > 0.08),   # 高于5日线8%以上
        "均线破位": bool(last_close < ma20),              # 跌破20日线
    }
