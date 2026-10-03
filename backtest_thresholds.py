"""指数技术信号回测 + 阈值自进化。

用上证指数历史日线，回测超买/超卖/放量/缩量/金叉/量价组合等信号
触发后 T+1/T+3/T+5 的真实涨跌，校准 technical_verdict 用的阈值。

输出：
  data/thresholds.json        —— 阈值 + 回测统计（供 technical_verdict 读取）
  output/指数的回测结论.md    —— 人类可读的报告
"""
import os
import json
from datetime import datetime

import pandas as pd
import numpy as np

import config as cfg
import analyzer as anl

BASE = os.path.dirname(os.path.abspath(__file__))


def _pro():
    import tushare as ts
    return ts.pro_api(cfg.TUSHARE_TOKEN)


def fetch_index_history(years: int = 12) -> pd.DataFrame:
    """拿上证指数历史日线。"""
    pro = _pro()
    end = datetime.now().strftime("%Y%m%d")
    start = f"{datetime.now().year - years}0101"
    df = pro.index_daily(ts_code="000001.SH", start_date=start, end_date=end)
    df = df.sort_values("trade_date").reset_index(drop=True)
    df = df.rename(columns={"vol": "volume", "trade_date": "date"})
    df["date"] = pd.to_datetime(df["date"])
    df = anl.calc_all_indicators(df)
    df["vol_ratio"] = df["volume"].rolling(5).mean() / df["volume"].rolling(20).mean()
    df["chg"] = df["close"].pct_change()
    df["body"] = (df["close"] - df["open"]) / df["open"]  # 实体涨幅
    for n in [1, 3, 5]:
        df[f"fwd_{n}"] = df["close"].shift(-n) / df["close"] - 1
    return df


def _stat(sub: pd.DataFrame) -> dict:
    if len(sub) < 5:
        return {"count": int(len(sub)), "t1": None, "t1_win": None, "t3": None, "t5": None}
    return {
        "count": int(len(sub)),
        "t1": round(float(sub["fwd_1"].mean()) * 100, 2),
        "t1_win": round(float((sub["fwd_1"] > 0).mean()) * 100, 0),
        "t3": round(float(sub["fwd_3"].mean()) * 100, 2),
        "t5": round(float(sub["fwd_5"].mean()) * 100, 2),
    }


def run_backtest() -> dict:
    df = fetch_index_history()
    valid = df[df["fwd_1"].notna()]

    golden = (df["DIF"] > df["DEA"]) & (df["DIF"].shift(1) <= df["DEA"].shift(1))
    dead = (df["DIF"] < df["DEA"]) & (df["DIF"].shift(1) >= df["DEA"].shift(1))

    # 背离检测（近20日，价格极值 vs MACD 极值的位置）
    bottom_div = pd.Series(False, index=df.index)
    top_div = pd.Series(False, index=df.index)
    for i in range(20, len(df)):
        w = df.iloc[i - 19:i + 1]
        c_idx = w["close"].idxmin(); m_idx = w["MACD"].idxmin()
        ch_idx = w["close"].idxmax(); mh_idx = w["MACD"].idxmax()
        if c_idx > m_idx and df.loc[i, "close"] <= w["close"].min() * 1.01:
            bottom_div.iloc[i] = True
        if ch_idx > mh_idx and df.loc[i, "close"] >= w["close"].max() * 0.99:
            top_div.iloc[i] = True
    # 连续3日不创新低
    no_new_low = (df["low"] > df["low"].shift(1)) & (df["low"].shift(1) > df["low"].shift(2)) & (df["low"].shift(2) > df["low"].shift(3))

    result = {
        "asof": df["date"].max().strftime("%Y-%m-%d"),
        "years": 12,
        "signals": {
            # 超买（阈值敏感）
            "overbought_k80": _stat(valid[df["K"] > 80]),
            "overbought_k90": _stat(valid[df["K"] > 90]),
            "overbought_rsi70": _stat(valid[df["RSI6"] > 70]),
            # 超卖（阈值敏感）
            "oversold_k20": _stat(valid[df["K"] < 20]),
            "oversold_k10": _stat(valid[df["K"] < 10]),
            "oversold_rsi30": _stat(valid[df["RSI6"] < 30]),
            # 量（阈值敏感）
            "vol_up_12": _stat(valid[df["vol_ratio"] > 1.2]),
            "vol_up_15": _stat(valid[df["vol_ratio"] > 1.5]),
            "vol_down_08": _stat(valid[df["vol_ratio"] < 0.8]),
            # 金叉死叉
            "golden_all": _stat(valid[golden]),
            "golden_above0": _stat(valid[golden & (df["DIF"] > 0)]),
            "golden_below0": _stat(valid[golden & (df["DIF"] < 0)]),
            "dead_all": _stat(valid[dead]),
            # 量价组合
            "volup_priceup": _stat(valid[(df["vol_ratio"] > 1.2) & (df["chg"] > 0)]),
            "volup_pricedown": _stat(valid[(df["vol_ratio"] > 1.2) & (df["chg"] < 0)]),
            "voldown_priceup": _stat(valid[(df["vol_ratio"] < 0.8) & (df["chg"] > 0)]),
            "voldown_pricedown": _stat(valid[(df["vol_ratio"] < 0.8) & (df["chg"] < 0)]),
            # 判断标准（企稳/滞涨）
            "oversold_above_ma5": _stat(valid[(df["K"] < 20) & (df["close"] > df["close"].rolling(5).mean())]),
            "oversold_vol_down": _stat(valid[(df["K"] < 20) & (df["vol_ratio"] < 0.8)]),
            "volup_smallbody": _stat(valid[(df["vol_ratio"] > 1.2) & (df["chg"] > 0) & (df["body"] < 0.005)]),
            "volup_bigbody": _stat(valid[(df["vol_ratio"] > 1.2) & (df["chg"] > 0) & (df["body"] >= 0.005)]),
            # 背离 + 企稳辅助
            "bottom_div_all": _stat(valid[bottom_div]),
            "bottom_div_vol_down": _stat(valid[bottom_div & (df["vol_ratio"] < 0.8)]),
            "top_div_all": _stat(valid[top_div]),
            "no_new_low_3d": _stat(valid[no_new_low]),
        },
    }
    return result


def save_result(result: dict):
    os.makedirs(os.path.join(BASE, "data"), exist_ok=True)
    os.makedirs(os.path.join(BASE, "output"), exist_ok=True)
    with open(os.path.join(BASE, "data", "thresholds.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2, default=str)
    _write_report(result)


def _fmt(s: dict) -> str:
    if s.get("t1") is None:
        return f"样本{s['count']}（太少）"
    return (f"样本{s['count']} | T+1 {s['t1']:+.2f}% 胜{s['t1_win']:.0f}% "
            f"| T+3 {s['t3']:+.2f}% | T+5 {s['t5']:+.2f}%")


def _write_report(result: dict):
    s = result["signals"]
    lines = [
        f"# 上证指数技术信号回测结论",
        f"",
        f"- 数据截至：{result['asof']}",
        f"- 样本：上证指数近 {result['years']} 年日线",
        f"- 方法：统计每个信号触发后 T+1 / T+3 / T+5 的平均涨跌幅和 T+1 胜率",
        f"",
        f"## 超买（追高）",
        f"- K>80：{_fmt(s['overbought_k80'])}",
        f"- K>90：{_fmt(s['overbought_k90'])}",
        f"- RSI6>70：{_fmt(s['overbought_rsi70'])}",
        f"",
        f"## 超卖（抄底）",
        f"- K<20：{_fmt(s['oversold_k20'])}",
        f"- K<10：{_fmt(s['oversold_k10'])}",
        f"- RSI6<30：{_fmt(s['oversold_rsi30'])}",
        f"",
        f"## 放量 / 缩量",
        f"- 量比>1.2：{_fmt(s['vol_up_12'])}",
        f"- 量比>1.5：{_fmt(s['vol_up_15'])}",
        f"- 量比<0.8：{_fmt(s['vol_down_08'])}",
        f"",
        f"## 金叉 / 死叉",
        f"- 金叉（全部）：{_fmt(s['golden_all'])}",
        f"- 金叉（零轴上）：{_fmt(s['golden_above0'])}",
        f"- 金叉（零轴下）：{_fmt(s['golden_below0'])}",
        f"- 死叉（全部）：{_fmt(s['dead_all'])}",
        f"",
        f"## 量价组合",
        f"- 放量上涨：{_fmt(s['volup_priceup'])}",
        f"- 放量下跌：{_fmt(s['volup_pricedown'])}",
        f"- 缩量上涨：{_fmt(s['voldown_priceup'])}",
        f"- 缩量下跌：{_fmt(s['voldown_pricedown'])}",
        f"",
        f"> 注意：以上是上证指数的回测结论，指数有均值回归特性；个股不适用。",
    ]
    with open(os.path.join(BASE, "output", "指数的回测结论.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


if __name__ == "__main__":
    r = run_backtest()
    save_result(r)
    print(f"回测完成，数据截至 {r['asof']}")
    for k, v in r["signals"].items():
        if v.get("t1") is not None:
            print(f"  {k}: T+1 {v['t1']:+.2f}% 胜{v['t1_win']:.0f}% T+5 {v['t5']:+.2f}%")
