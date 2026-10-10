"""
每日A股复盘模型 - 技术分析模块
MACD、KDJ、RSI、BOLL、均线、形态识别、支撑阻力、预测
"""

import os
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
    """找关键支撑位和压力位（均线 + 局部波段转折点）。"""
    if df.empty or len(df) < 10:
        return {}

    close = df["close"]
    high = df["high"]
    low = df["low"]
    current = close.iloc[-1]

    # 局部波峰（压力）/ 波谷（支撑）：前后各2天的转折点，记录日期
    pivots_high = []  # (日期, 高点)
    pivots_low = []   # (日期, 低点)
    n = len(df)
    _dates = pd.to_datetime(df["date"]).dt.strftime("%m-%d").tolist()
    for i in range(2, n - 2):
        if high.iloc[i] >= high.iloc[i - 2:i + 3].max():
            pivots_high.append((_dates[i], round(float(high.iloc[i]), 2)))
        if low.iloc[i] <= low.iloc[i - 2:i + 3].min():
            pivots_low.append((_dates[i], round(float(low.iloc[i]), 2)))

    # 均线作为动态支撑/压力
    ma20 = close.rolling(20).mean().iloc[-1] if len(df) >= 20 else current
    ma60 = close.rolling(60).mean().iloc[-1] if len(df) >= 60 else current
    ma250 = close.rolling(250).mean().iloc[-1] if len(df) >= 250 else np.nan  # 数据不足则跳过年线

    supports = []
    resistances = []

    for ma_val, label in [(ma20, "MA20"), (ma60, "MA60"), (ma250, "MA250(年线)")]:
        if not np.isnan(ma_val):
            if ma_val < current:
                supports.append({"price": round(float(ma_val), 2), "label": label, "type": "均线支撑"})
            else:
                resistances.append({"price": round(float(ma_val), 2), "label": label, "type": "均线压力"})

    # 波段低点 → 支撑，波段高点 → 压力（按价格去重，保留日期）
    _low_map = {}
    for _d, p in pivots_low:
        if p < current:
            _low_map.setdefault(p, _d)
    for p in sorted(_low_map.keys(), reverse=True):
        supports.append({"price": p, "label": f"波谷{_low_map[p]}", "type": "关键支撑"})

    _high_map = {}
    for _d, p in pivots_high:
        if p > current:
            _high_map.setdefault(p, _d)
    for p in sorted(_high_map.keys()):
        resistances.append({"price": p, "label": f"波峰{_high_map[p]}", "type": "关键压力"})

    # 支撑从高到低（最近的在最前），压力从低到高
    supports.sort(key=lambda x: x["price"], reverse=True)
    resistances.sort(key=lambda x: x["price"])

    return {
        "current": round(float(current), 2),
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

def predict_next_day(df: pd.DataFrame, fund_df: pd.DataFrame = None, market_emotion: dict = None) -> dict:
    """基于技术指标 + 资金面 + 市场情绪的次日预判。
    fund_df 可选，含 main_net/turnover_rate；market_emotion 可选，含 up_ratio。"""
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

    # 2. RSI（超卖反弹回测无效，只保留超买风险）
    rsi6 = latest.get("RSI6", 50)
    if rsi6 and not np.isnan(rsi6):
        if rsi6 > 70:
            score -= 1
            reasons.append(f"RSI超买(rsi6=%.1f)" % rsi6)
        elif rsi6 > 50:
            score += 0.5
        else:
            score -= 0.5

    # 3. KDJ（超卖/金叉回测反向，只保留超买风险）
    k = latest.get("K", 50)
    d = latest.get("D", 50)
    j = latest.get("J", 50)
    if j and k and d and not np.isnan(j):
        if j > 80:
            score -= 1
            reasons.append(f"KDJ超买(J=%.1f)" % j)

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

    # 4.5 乖离率 / 短期动量（5日涨跌幅）
    if len(df) >= 6:
        close_5ago = df["close"].iloc[-6]
        if close_5ago and close_5ago > 0:
            mom5 = close / close_5ago - 1
            if mom5 > 0.15:
                score += 1  # 动量延续（回测：次日超额 +0.22%，最强正信号）
                reasons.append(f"短期强势({mom5:.1%})，动量延续")
            elif mom5 < -0.10:
                score -= 1  # 超跌但跑输大盘（回测：次日超额 -0.07%）
                reasons.append(f"短期超跌({mom5:.1%})，弱势")

    # 5. 布林带位置（下轨"支撑"回测无效，只保留上轨压力）
    boll_mid = latest.get("BOLL_MID", close)
    boll_up = latest.get("BOLL_UP", close)
    boll_dn = latest.get("BOLL_DN", close)
    if boll_up and boll_dn and boll_mid:
        boll_pct = (close - boll_dn) / (boll_up - boll_dn) * 100 if boll_up != boll_dn else 50
        if boll_pct > 80:
            score -= 1
            reasons.append("布林上轨附近，有压力")

    # 6. 成交量变化
    vol = latest.get("volume", 0)
    prev_vol = prev.get("volume", 0)
    if vol and prev_vol and prev_vol > 0:
        vol_ratio = vol / prev_vol
        if close > prev["close"] and vol_ratio > 1.2:
            score -= 1  # 放量上涨后追高被套（回测：次日超额 -0.08%）
            reasons.append("放量上涨，警惕追高")
        elif close < prev["close"] and vol_ratio > 1.2:
            score -= 1
            reasons.append("放量下跌（量价背离）")
        elif vol_ratio < 0.7:
            reasons.append("缩量（观望情绪浓）")

    # 7. 资金面因子（主力净流入 + 换手率）
    if fund_df is not None and not fund_df.empty:
        try:
            lf = fund_df.iloc[-1]
            main_net = lf.get("main_net", 0)
            if main_net is not None and not (isinstance(main_net, float) and np.isnan(main_net)):
                if main_net > 0:
                    score += 1
                    reasons.append("主力净流入")
                elif main_net < 0:
                    score -= 1
                    reasons.append("主力净流出")
            turnover = lf.get("turnover_rate", 0)
            if turnover is not None and not (isinstance(turnover, float) and np.isnan(turnover)):
                if 3 < turnover < 15:
                    score += 0.5
                    reasons.append(f"换手活跃({turnover:.1f}%)")
                elif turnover > 20:
                    score -= 0.5
                    reasons.append(f"换手过热({turnover:.1f}%)")
        except Exception:  # noqa: BLE001
            pass

    # 8. 市场情绪（A股整体涨跌比，beta 调整）
    if market_emotion:
        up_ratio = market_emotion.get("up_ratio")
        if up_ratio is not None:
            if up_ratio < 0.35:
                score -= 1
                reasons.append(f"市场情绪差(上涨仅{up_ratio:.0%})")
            elif up_ratio > 0.65:
                score += 0.5
                reasons.append(f"市场情绪好(上涨{up_ratio:.0%})")

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


def comprehensive_analysis(df: pd.DataFrame, fund_df: pd.DataFrame = None, sector_pct=None) -> dict:
    """综合分析：K线形态 + 量价 + 资金 + 板块 → 短线/长线预测。"""
    if df.empty or len(df) < 20:
        return {}
    pred = predict_next_day(df, fund_df)
    trend = classify_trend(df)
    patterns = detect_patterns(df)

    close = df["close"]
    latest = float(close.iloc[-1])

    # 量价
    vol5 = df["volume"].tail(5).mean()
    vol20 = df["volume"].tail(20).mean()
    vol_ratio = vol5 / vol20 if vol20 > 0 else 1
    chg5 = latest / float(close.iloc[-6]) - 1 if len(close) >= 6 else 0
    chg20 = latest / float(close.iloc[-21]) - 1 if len(close) >= 21 else 0

    # 均线（长线）
    ma20 = float(close.rolling(20).mean().iloc[-1])
    ma60 = float(close.rolling(60).mean().iloc[-1])

    # 利好利空
    positive, negative = [], []
    if vol_ratio > 1.2 and chg5 > 0:
        positive.append("放量上涨，资金进场")
    elif vol_ratio > 1.2 and chg5 < 0:
        negative.append("放量下跌，有抛压")
    if chg5 > 0.05:
        positive.append(f"近5日强势(+{chg5:.1%})")
    elif chg5 < -0.05:
        negative.append(f"近5日弱势({chg5:.1%})")
    if "多头" in trend.get("short_trend", ""):
        positive.append("短期均线多头")
    if "空头" in trend.get("short_trend", ""):
        negative.append("短期均线空头")
    if patterns:
        for p in patterns:
            if "风险" in p or "上影" in p or "破位" in p:
                negative.append(p)
            else:
                positive.append(p)
    if fund_df is not None and not fund_df.empty:
        last_main = float(fund_df["main_net"].iloc[-1]) if "main_net" in fund_df.columns else 0
        if last_main > 0:
            positive.append("主力净流入")
        elif last_main < 0:
            negative.append("主力净流出")

    sector_note = f"所属板块 {sector_pct:+.2f}%" if sector_pct is not None else "板块数据暂无"

    short_verdict = pred.get("direction", "—")
    long_verdict = "偏多" if latest > ma20 > ma60 else "偏空" if latest < ma20 < ma60 else "震荡"

    return {
        "pred": pred, "trend": trend, "patterns": patterns,
        "vol_ratio": vol_ratio, "chg5": chg5, "chg20": chg20,
        "positive": positive, "negative": negative,
        "sector_note": sector_note, "short_verdict": short_verdict, "long_verdict": long_verdict,
    }


def _load_thresholds() -> dict:
    """读回测阈值（data/thresholds.json），供 technical_verdict 用；不存在则返回空。"""
    try:
        import json as _json
        p = os.path.join(os.environ.get("SC_DATA_ROOT") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "data"), "thresholds.json")
        with open(p, "r", encoding="utf-8") as f:
            return _json.load(f).get("signals", {})
    except Exception:
        return {}


def technical_verdict(df: pd.DataFrame) -> dict:
    """技术面综合研判：量价 + MACD + KDJ/RSI + 背离，如实摆信号串起来看。

    注意：不做拍脑袋的加权评分（权重未回测，不可信），只统计多/空/中性信号的数量，
    用文字描述多空力量对比，结论仅供参考。
    """
    if df.empty or len(df) < 25:
        return {}
    last = df.iloc[-1]
    prev = df.iloc[-2]
    close = df["close"]
    vol = df["volume"]

    # 回测阈值（data/thresholds.json，由 backtest_thresholds.py 定期更新）
    _th = _load_thresholds()

    def _bt(key):
        s = _th.get(key)
        if not s or s.get("t1") is None:
            return ""
        return f"T+1 {s['t1']:+.2f}% 胜{s['t1_win']:.0f}%、T+5 {s['t5']:+.2f}%"

    # 1. 量价关系（近5日 vs 近20日）
    vol5 = vol.tail(5).mean()
    vol20 = vol.tail(20).mean()
    vol_ratio = vol5 / vol20 if vol20 > 0 else 1
    chg5 = float(close.iloc[-1]) / float(close.iloc[-6]) - 1 if len(close) >= 6 else 0

    bull, bear, neutral = [], [], []

    if vol_ratio > 1.2 and chg5 > 0:
        vol_price = "放量上涨（回测：上证 T+5 平均 +0.83%，偏多；但量比>1.5 过度放量反而转弱）"
        bull.append("放量上涨")
    elif vol_ratio > 1.2 and chg5 < 0:
        vol_price = "放量下跌（回测：T+1 平均 +0.26% 胜率60%，急跌后常有反抽）"
        neutral.append("放量下跌")
    elif vol_ratio < 0.8 and chg5 > 0:
        vol_price = "缩量上涨（回测：T+5 +0.99%，抛压轻，偏多）"
        bull.append("缩量上涨")
    elif vol_ratio < 0.8 and chg5 < 0:
        vol_price = "缩量下跌（回测：T+5 +2.18% 胜率72%，上证最强反弹信号，抛压已枯竭）"
        bull.append("缩量下跌")
    else:
        vol_price = "量价平稳（多空均衡）"
        neutral.append("量价平稳")

    # 2. MACD 趋势动能
    dif, dea = float(last["DIF"]), float(last["DEA"])
    p_dif, p_dea = float(prev["DIF"]), float(prev["DEA"])
    if dif > dea:
        macd_state = "MACD多头（DIF在DEA上方）"
        bull.append("MACD多头")
    else:
        macd_state = "MACD空头（DIF在DEA下方）"
        bear.append("MACD空头")
    if p_dif <= p_dea and dif > dea:
        macd_state += "，刚金叉"
    elif p_dif >= p_dea and dif < dea:
        macd_state += "，刚死叉"

    # 3. KDJ/RSI 短线情绪
    k, rsi = float(last["K"]), float(last["RSI6"])
    if k > 80 or rsi > 70:
        mood = "短线超买（回测：超买后趋势惯性、短期未必回调，仅 K>90 才转弱）"
        neutral.append("超买")
    elif k < 20 or rsi < 30:
        mood = "短线超卖（回测：K<20 后 T+5 +0.59%、K<10 后 +1.31% 胜74%，是反弹信号）"
        bull.append("超卖")
    else:
        mood = "短线情绪中性"
        neutral.append("情绪中性")

    # 4. 背离检测（近20日，价格 vs MACD）
    divergence = None
    tail_close = close.iloc[-20:]
    tail_macd = df["MACD"].iloc[-20:]
    ph_idx = tail_close.idxmax()
    mh_idx = tail_macd.idxmax()
    pl_idx = tail_close.idxmin()
    ml_idx = tail_macd.idxmin()
    if ph_idx > mh_idx and float(close.iloc[-1]) >= float(tail_close.max()) * 0.99:
        divergence = "顶背离（价格新高但MACD动能未跟上，上涨乏力）"
        bear.append("顶背离")
    elif pl_idx > ml_idx and float(close.iloc[-1]) <= float(tail_close.min()) * 1.01:
        if vol_ratio > 1:
            divergence = "底背离（价格新低但MACD企稳，且放量，可能见底）"
            bull.append("放量底背离")
        else:
            divergence = "疑似底背离（量能不足，可能是空头抛压减少而非多头进场，需放量确认）"
            neutral.append("缩量底背离")

    # 5. 总结（定性描述多空力量对比，不打分）
    bull_n, bear_n = len(bull), len(bear)
    if bull_n > bear_n:
        tone = "bull"
        summary = f"多方信号占优（{bull_n} vs {bear_n}）"
    elif bear_n > bull_n:
        tone = "bear"
        summary = f"空方信号占优（{bear_n} vs {bull_n}）"
    else:
        tone = "neutral"
        summary = f"多空信号均衡（{bull_n} vs {bear_n}）"

    # 6. 当前触发的提示（结合数据给建议，带方向标记，便于发现冲突）
    alerts = []  # [{"d": "bull/bear/neutral", "t": "..."}]
    ma5 = float(close.rolling(5).mean().iloc[-1])

    if vol_ratio < 0.8 and chg5 > 0:
        alerts.append({"d": "bull", "t": f"当前缩量上涨：可持有（回测 {_bt('voldown_priceup')} 偏多，且高低位差异不大）。"})
    if vol_ratio > 1.2 and chg5 > 0:
        _body = (float(last["close"]) - float(last["open"])) / float(last["open"])
        if _body < 0.005:
            alerts.append({"d": "bear", "t": f"当前放量滞涨（实体<0.5%）：谨慎、警惕出货（回测：放量+实体<0.5% 后 T+1 -0.17% 胜45%，明显偏弱）。"})
        else:
            alerts.append({"d": "bull", "t": f"当前放量上涨：可持有（回测：放量+实体≥0.5% 后 T+1 +0.32% 胜54%）；若次日冲高回落则警惕。"})
    elif vol_ratio > 1.2 and chg5 < 0:
        alerts.append({"d": "bear", "t": f"当前放量下跌：别追反抽（回测 {_bt('volup_pricedown')}，急跌反抽但抛压未释放完，反抽后可能续跌）。"})
    if k > 80 or rsi > 70:
        _deg = "极度超买" if (k > 90 or rsi > 85) else "超买"
        if k > 90:
            _advice = "追高要小心"
            _dir = "bear"
        else:
            _advice = "短期未必回调，可继续持有"
            _dir = "neutral"
        _bk = "overbought_k90" if k > 90 else "overbought_k80"
        alerts.append({"d": _dir, "t": f"当前{_deg}（K={k:.1f}, RSI={rsi:.1f}）：{_advice}（回测 {_bt(_bk)}）。"})
    if k < 20 or rsi < 30:
        _deg = "极度超卖" if (k < 10 or rsi < 15) else "超卖"
        _advice = "强反弹信号，可关注企稳机会" if k < 10 else "反弹信号，可关注企稳"
        _bk = "oversold_k10" if k < 10 else "oversold_k20"
        _note = f"当前{_deg}（K={k:.1f}, RSI={rsi:.1f}）：{_advice}"
        _note += f"\n· 回测依据：{_bt(_bk)}"
        _note += "\n· 企稳 = 跌势停止，标准（满足再考虑轻仓）："
        _note += f"\n  ① 站回5日线 ¥{ma5:.2f}（回测 {_bt('oversold_above_ma5')}）"
        _note += f"\n  ② 缩量或量价平稳（回测超卖+缩量 {_bt('oversold_vol_down')} 最强，而非放量）"
        _note += "\n  ③ 连续3日不创新低"
        if vol_ratio < 0.8 and chg5 < 0:
            _note += "\n· 当前缩量下跌，抛压已枯竭，反弹概率更高"
        elif vol_ratio > 1.2 and chg5 < 0:
            _note += "\n· 但当前放量下跌，反弹力度或打折"
        alerts.append({"d": "bull", "t": _note})
    if dif > dea and dif < 0:
        alerts.append({"d": "neutral", "t": f"当前零轴下金叉：别单独当买入信号（回测 {_bt('golden_below0')} 几乎无效）。"})
    if p_dif >= p_dea and dif < dea:
        alerts.append({"d": "bear", "t": f"当前刚死叉：别追反抽（回测 {_bt('dead_all')} 短期偏弱）。"})
    if divergence and "疑似底背离" in divergence:
        alerts.append({"d": "bull", "t": f"当前缩量底背离：偏多（回测缩量底背离 {_bt('bottom_div_vol_down')}），缩量本身是企稳特征，别等放量（底背离时极少放量）。"})
    elif divergence and "顶背离" in divergence:
        alerts.append({"d": "neutral", "t": f"当前顶背离：信号弱（回测顶背离后 {_bt('top_div_all')}，几乎无效），别过度解读成卖出信号。"})

    return {
        "vol_ratio": round(vol_ratio, 2),
        "chg5": round(chg5, 4),
        "vol_price": vol_price,
        "macd_state": macd_state,
        "mood": mood,
        "divergence": divergence,
        "bull": bull,
        "bear": bear,
        "neutral": neutral,
        "summary": summary,
        "tone": tone,
        "alerts": alerts,
    }
