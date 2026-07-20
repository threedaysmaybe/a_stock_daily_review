"""
每日A股复盘模型 - 技术分析模块
MACD、KDJ、RSI、BOLL、均线、形态识别、支撑阻力、预测
"""

import numpy as np
import pandas as pd
from typing import Tuple, Optional

import config as cfg

# ============================================================
# 基础指标计算
# ============================================================

def calc_ma(df: pd.DataFrame, periods: list = None) -> pd.DataFrame:
    """计算移动均线"""
    if periods is None:
        periods = cfg.TECH_PARAMS["ma_periods"]
    result = df.copy()
    for p in periods:
        if len(result) >= p:
            result[f"MA{p}"] = result["close"].rolling(p).mean()
    return result


def calc_macd(df: pd.DataFrame) -> pd.DataFrame:
    """计算MACD"""
    p = cfg.TECH_PARAMS["macd"]
    result = df.copy()
    result["EMA_fast"] = result["close"].ewm(span=p["fast"], adjust=False).mean()
    result["EMA_slow"] = result["close"].ewm(span=p["slow"], adjust=False).mean()
    result["DIF"] = result["EMA_fast"] - result["EMA_slow"]
    result["DEA"] = result["DIF"].ewm(span=p["signal"], adjust=False).mean()
    result["MACD"] = 2 * (result["DIF"] - result["DEA"])
    return result


def calc_kdj(df: pd.DataFrame, n: int = 9) -> pd.DataFrame:
    """计算KDJ"""
    result = df.copy()
    low_min = result["low"].rolling(n).min()
    high_max = result["high"].rolling(n).max()
    rsv = (result["close"] - low_min) / (high_max - low_min) * 100
    rsv = rsv.fillna(50)

    k = rsv.ewm(com=2, adjust=False).mean()
    d = k.ewm(com=2, adjust=False).mean()
    j = 3 * k - 2 * d

    result["K"] = k
    result["D"] = d
    result["J"] = j
    return result


def calc_rsi(df: pd.DataFrame, periods: list = None) -> pd.DataFrame:
    """计算RSI"""
    if periods is None:
        periods = [6, 12, 24]
    result = df.copy()
    delta = result["close"].diff()
    for p in periods:
        gain = delta.clip(lower=0).rolling(p).mean()
        loss = (-delta.clip(upper=0)).rolling(p).mean()
        rs = gain / loss.replace(0, np.nan)
        result[f"RSI{p}"] = 100 - (100 / (1 + rs))
    return result


def calc_boll(df: pd.DataFrame) -> pd.DataFrame:
    """计算布林带"""
    p = cfg.TECH_PARAMS["boll_period"]
    std_mul = cfg.TECH_PARAMS["boll_std"]
    result = df.copy()
    result["BOLL_MID"] = result["close"].rolling(p).mean()
    std = result["close"].rolling(p).std()
    result["BOLL_UP"] = result["BOLL_MID"] + std_mul * std
    result["BOLL_DN"] = result["BOLL_MID"] - std_mul * std
    result["BOLL_WIDTH"] = (result["BOLL_UP"] - result["BOLL_DN"]) / result["BOLL_MID"] * 100
    return result


def calc_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """一次性计算所有技术指标"""
    df = calc_ma(df)
    df = calc_macd(df)
    df = calc_kdj(df, cfg.TECH_PARAMS["kdj_period"])
    df = calc_rsi(df)
    df = calc_boll(df)
    return df


# ============================================================
# 支撑阻力位
# ============================================================

def find_support_resistance(df: pd.DataFrame) -> dict:
    """找关键支撑位和压力位"""
    if df.empty:
        return {}

    close = df["close"]
    high = df["high"]
    low = df["low"]

    current = close.iloc[-1]
    ma20 = close.rolling(20).mean().iloc[-1] if len(df) >= 20 else current
    ma60 = close.rolling(60).mean().iloc[-1] if len(df) >= 60 else current
    ma120 = close.rolling(120).mean().iloc[-1] if len(df) >= 120 else current

    # 近期高点（压力位）
    recent_high = high.tail(20).max()
    all_time_high = high.max()

    # 近期低点（支撑位）
    recent_low = low.tail(20).min()
    all_time_low = low.min()

    supports = []
    resistances = []

    for ma_val, label in [(ma20, "MA20"), (ma60, "MA60"), (ma120, "MA120")]:
        if not np.isnan(ma_val):
            if ma_val < current:
                supports.append({"price": round(ma_val, 2), "label": label, "type": "均线支撑"})
            else:
                resistances.append({"price": round(ma_val, 2), "label": label, "type": "均线压力"})

    supports.append({"price": round(recent_low, 2), "label": "近20日低点", "type": "关键支撑"})
    resistances.append({"price": round(recent_high, 2), "label": "近20日高点", "type": "关键压力"})

    # 排序：支撑从高到低，压力从低到高
    supports.sort(key=lambda x: x["price"], reverse=True)
    resistances.sort(key=lambda x: x["price"])

    return {
        "current": round(current, 2),
        "supports": supports[:3],
        "resistances": resistances[:3],
    }


# ============================================================
# 趋势判断
# ============================================================

def classify_trend(df: pd.DataFrame) -> dict:
    """多周期趋势判断"""
    if df.empty or len(df) < 60:
        return {"trend": "数据不足", "strength": "-", "signal": "中性"}

    df = calc_all_indicators(df)
    close = df["close"]

    # 短周期（5/10/20日）
    short_ma5 = close.rolling(5).mean().iloc[-1]
    short_ma10 = close.rolling(10).mean().iloc[-1]
    short_ma20 = close.rolling(20).mean().iloc[-1]
    short_current = close.iloc[-1]

    if short_current > short_ma5 > short_ma10 > short_ma20:
        short_trend = "多头排列"
        short_signal = "🟢 强势"
    elif short_current > short_ma20:
        short_trend = "短期偏多"
        short_signal = "🟢 偏多"
    elif short_current < short_ma5 < short_ma10 < short_ma20:
        short_trend = "空头排列"
        short_signal = "🔴 弱势"
    elif short_current < short_ma20:
        short_trend = "短期偏空"
        short_signal = "🔴 偏空"
    else:
        short_trend = "震荡整理"
        short_signal = "🟡 震荡"

    # 中周期（20/60日）
    ma20 = close.rolling(20).mean().iloc[-1]
    ma60 = close.rolling(60).mean().iloc[-1]

    if not np.isnan(ma20) and not np.isnan(ma60):
        if ma20 > ma60:
            mid_trend = "多头"
            mid_signal = "🟢 中期向好"
        else:
            mid_trend = "空头"
            mid_signal = "🔴 中期偏弱"
    else:
        mid_trend = "数据不足"
        mid_signal = "—"

    # MACD信号
    if "DIF" in df.columns and "DEA" in df.columns:
        dif = df["DIF"].iloc[-1]
        dea = df["DEA"].iloc[-1]
        prev_dif = df["DIF"].iloc[-2] if len(df) >= 2 else dif
        prev_dea = df["DEA"].iloc[-2] if len(df) >= 2 else dea

        if dif > dea:
            if dif > 0:
                macd_signal = "🟢 多头强势"
            else:
                macd_signal = "🟡 空头反弹"
            if prev_dif <= prev_dea:  # 金叉
                macd_signal += " ⚡金叉"
        else:
            if dif < 0:
                macd_signal = "🔴 空头强势"
            else:
                macd_signal = "🟡 多头回调"
            if prev_dif >= prev_dea:  # 死叉
                macd_signal += " ⚡死叉"
    else:
        macd_signal = "—"

    return {
        "short_trend": short_trend,
        "short_signal": short_signal,
        "mid_trend": mid_trend,
        "mid_signal": mid_signal,
        "macd_signal": macd_signal,
        "sr_levels": find_support_resistance(df),
    }


# ============================================================
# 形态识别
# ============================================================

def detect_patterns(df: pd.DataFrame) -> list:
    """检测K线形态"""
    patterns = []
    if df.empty or len(df) < 3:
        return patterns

    o, h, l, c = df["open"], df["high"], df["low"], df["close"]
    body = abs(c - o)
    upper_shadow = h - np.maximum(c, o)
    lower_shadow = np.minimum(c, o) - l

    i = -1  # 最新一根K线

    # 十字星
    if body.iloc[i] < (h.iloc[i] - l.iloc[i]) * 0.1:
        patterns.append("🔸 十字星 — 多空均衡，变盘信号")

    # 锤子线（下影线>实体2倍，实体小）
    if lower_shadow.iloc[i] > body.iloc[i] * 2 and body.iloc[i] > 0:
        patterns.append("🔨 锤子线 — 下方承接力强，看涨反转")

    # 射击之星（上影线>实体2倍）
    if upper_shadow.iloc[i] > body.iloc[i] * 2 and body.iloc[i] > 0:
        patterns.append("⭐ 射击之星 — 上方压力重，看跌反转")

    # 吞没形态
    if len(df) >= 2:
        prev_body = abs(c.iloc[-2] - o.iloc[-2])
        curr_body = abs(c.iloc[-1] - o.iloc[-1])
        if c.iloc[-2] < o.iloc[-2] and c.iloc[-1] > o.iloc[-1] and curr_body > prev_body * 1.5:
            patterns.append("🔥 看涨吞没 — 强烈反转信号")

    # 三连阳/三连阴
    if len(df) >= 3:
        last3 = c.tail(3)
        if last3.iloc[0] < last3.iloc[1] < last3.iloc[2]:
            patterns.append("☀️ 三连阳 — 多头动能累积")
        elif last3.iloc[0] > last3.iloc[1] > last3.iloc[2]:
            patterns.append("🌧️ 三连阴 — 空头动能持续")

    return patterns


# ============================================================
# 明日预测
# ============================================================

def predict_next_day(df: pd.DataFrame) -> dict:
    """基于技术指标的次日预判"""
    if df.empty or len(df) < 20:
        return {"direction": "数据不足", "confidence": 0, "range": ""}

    df = calc_all_indicators(df)
    if df.empty or len(df) < 2:
        return {"direction": "数据不足", "confidence": 0, "range": ""}

    latest = df.iloc[-1]
    prev = df.iloc[-2]
    close = latest["close"]

    score = 0
    reasons = []

    # 1. MACD
    dif = latest.get("DIF", 0)
    dea = latest.get("DEA", 0)
    prev_dif = prev.get("DIF", 0)
    prev_dea = prev.get("DEA", 0)

    if dif > dea:
        score += 1
        reasons.append("MACD多头排列")
        if prev_dif <= prev_dea:
            score += 1
            reasons.append("MACD金叉形成")
    else:
        score -= 1
        reasons.append("MACD空头排列")

    # 2. RSI
    rsi6 = latest.get("RSI6", 50)
    if rsi6 and not np.isnan(rsi6):
        if rsi6 < 30:
            score += 1
            reasons.append(f"RSI超卖(rsi6=%.1f)" % rsi6)
        elif rsi6 > 70:
            score -= 1
            reasons.append(f"RSI超买(rsi6=%.1f)" % rsi6)
        elif rsi6 > 50:
            score += 0.5
        else:
            score -= 0.5

    # 3. KDJ
    k = latest.get("K", 50)
    d = latest.get("D", 50)
    j = latest.get("J", 50)
    if j and k and d and not np.isnan(j):
        if j < 20:
            score += 1
            reasons.append(f"KDJ超卖(J=%.1f)" % j)
        elif j > 80:
            score -= 1
            reasons.append(f"KDJ超买(J=%.1f)" % j)
        if k > d:
            score += 0.5
            reasons.append("KDJ金叉")

    # 4. 均线
    ma5 = latest.get("MA5", close)
    ma20 = latest.get("MA20", close)
    if ma5 and ma20 and not np.isnan(ma5) and not np.isnan(ma20):
        if close > ma5 > ma20:
            score += 1
            reasons.append("短中期均线多头排列")
        elif close < ma5 < ma20:
            score -= 1
            reasons.append("短中期均线空头排列")

    # 5. 布林带位置
    boll_mid = latest.get("BOLL_MID", close)
    boll_up = latest.get("BOLL_UP", close)
    boll_dn = latest.get("BOLL_DN", close)
    if boll_up and boll_dn and boll_mid:
        boll_pct = (close - boll_dn) / (boll_up - boll_dn) * 100 if boll_up != boll_dn else 50
        if boll_pct < 20:
            score += 1
            reasons.append("布林下轨附近，有支撑")
        elif boll_pct > 80:
            score -= 1
            reasons.append("布林上轨附近，有压力")

    # 6. 成交量变化
    vol = latest.get("volume", 0)
    prev_vol = prev.get("volume", 0)
    if vol and prev_vol and prev_vol > 0:
        vol_ratio = vol / prev_vol
        if close > prev["close"] and vol_ratio > 1.2:
            score += 1
            reasons.append("放量上涨（量价配合好）")
        elif close < prev["close"] and vol_ratio > 1.2:
            score -= 1
            reasons.append("放量下跌（量价背离）")
        elif vol_ratio < 0.7:
            reasons.append("缩量（观望情绪浓）")

    # 综合判断
    if score >= 3:
        direction = "📈 看涨"
        confidence = min(abs(score) / 6 * 100, 90)
    elif score >= 1:
        direction = "📈 偏强震荡"
        confidence = min(abs(score) / 6 * 100, 65)
    elif score >= -1:
        direction = "📊 横盘整理"
        confidence = 50
    elif score >= -3:
        direction = "📉 偏弱震荡"
        confidence = min(abs(score) / 6 * 100, 65)
    else:
        direction = "📉 看跌"
        confidence = min(abs(score) / 6 * 100, 90)

    # 预估波动区间
    atr = (df["high"] - df["low"]).tail(14).mean()
    if atr and not np.isnan(atr):
        upper = round(close + atr * 1.5, 2)
        lower = round(close - atr * 1.5, 2)
        range_str = f"{lower} ~ {upper}"
    else:
        range_str = "无法估计"

    return {
        "direction": direction,
        "confidence": round(confidence, 1),
        "range": range_str,
        "score": round(score, 1),
        "reasons": reasons[:6],
        "close": round(close, 2),
        "atr": round(atr, 2) if atr and not np.isnan(atr) else 0,
    }


# ============================================================
# 止盈止损 & 仓位建议
# ============================================================

def calc_stop_loss_take_profit(df: pd.DataFrame, risk_tolerance: str = "中等") -> dict:
    """计算止盈止损位和仓位建议"""
    if df.empty:
        return {}

    close = df["close"].iloc[-1]
    atr = (df["high"] - df["low"]).tail(14).mean()
    if np.isnan(atr) or atr == 0:
        atr = close * 0.03

    sr = find_support_resistance(df)

    # 止损位：最近支撑位下方
    if sr and sr.get("supports"):
        stop_loss = min(s["price"] for s in sr["supports"])
    else:
        stop_loss = close * 0.95

    # 根据风险偏好调整
    risk_mult = {"保守": 1.0, "中等": 1.5, "激进": 2.0}
    mult = risk_mult.get(risk_tolerance, 1.5)

    stop_loss_tight = round(close - atr * mult, 2)
    stop_loss_loose = round(stop_loss, 2)

    # 止盈位：最近压力位
    if sr and sr.get("resistances"):
        take_profit_1 = round(close + atr * 2, 2)
        take_profit_2 = round(sr["resistances"][0]["price"], 2)
        take_profit_3 = round(close + atr * 4, 2)
    else:
        take_profit_1 = round(close * 1.05, 2)
        take_profit_2 = round(close * 1.10, 2)
        take_profit_3 = round(close * 1.15, 2)

    # 仓位建议
    trend = classify_trend(df)
    trend_score = 0
    if "多头" in trend.get("short_trend", ""):
        trend_score += 2
    elif "空头" in trend.get("short_trend", ""):
        trend_score -= 2
    if "多头" in trend.get("mid_trend", ""):
        trend_score += 1
    elif "空头" in trend.get("mid_trend", ""):
        trend_score -= 1

    if risk_tolerance == "保守":
        base_position = 30 + trend_score * 10
    elif risk_tolerance == "激进":
        base_position = 60 + trend_score * 15
    else:
        base_position = 45 + trend_score * 10

    position_advice = max(10, min(80, base_position))

    return {
        "stop_loss_tight": stop_loss_tight,
        "stop_loss_loose": stop_loss_loose,
        "take_profit_1": take_profit_1,
        "take_profit_2": take_profit_2,
        "take_profit_3": take_profit_3,
        "risk_tolerance": risk_tolerance,
        "suggested_position": f"{position_advice:.0f}%",
        "atr": round(atr, 2),
    }
