"""因子数据处理：去极值 + 标准化"""
import numpy as np
import pandas as pd


def winsorize(s: pd.Series, clip_q: float = 0.01) -> pd.Series:
    """上下 clip_q 分位截断去极值"""
    s = s.astype(float)
    lower = s.quantile(clip_q)
    upper = s.quantile(1 - clip_q)
    return s.clip(lower, upper)


def standardize(s: pd.Series, method: str = "zscore") -> pd.Series:
    """标准化：zscore 或 rank(百分位)"""
    if method == "rank":
        return s.rank(pct=True)

    std = s.std()
    if std == 0 or np.isnan(std):
        return pd.Series(0.0, index=s.index)
    return (s - s.mean()) / std


def process_factor(s: pd.Series, clip_q: float = 0.01,
                   method: str = "zscore") -> pd.Series:
    """去极值 -> 标准化"""
    s = winsorize(s, clip_q)
    return standardize(s, method)
