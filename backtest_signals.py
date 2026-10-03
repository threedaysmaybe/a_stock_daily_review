"""回测各技术/资金/情绪信号的历史胜率（T+1）。

对每个信号，统计：命中后次日上涨概率（胜率）+ 平均收益 + 超额收益（相对沪深300）。
"""
import time
import numpy as np
import pandas as pd
import tushare as ts

import config as cfg
import analyzer as anl

TOKEN = cfg.TUSHARE_TOKEN


def _signals_of(df: pd.DataFrame) -> pd.DataFrame:
    """在带指标的 df 上逐行打信号标签（1=看多，-1=看空，0=无）。"""
    df = anl.calc_all_indicators(df)
    n = len(df)
    sig = pd.DataFrame(index=df.index)
    for col in ["MACD金叉", "MACD死叉", "RSI超卖", "RSI超买", "KDJ超卖", "KDJ金叉",
                "均线多头", "均线空头", "布林下轨", "布林上轨", "放量上涨", "放量下跌",
                "缩量", "乖离超跌", "乖离过热"]:
        sig[col] = False
    for i in range(1, n):
        r = df.iloc[i]
        p = df.iloc[i - 1]
        close, prev_close = r["close"], p["close"]
        # MACD 金叉/死叉
        if p["DIF"] <= p["DEA"] and r["DIF"] > r["DEA"]:
            sig.iloc[i, sig.columns.get_loc("MACD金叉")] = True
        if p["DIF"] >= p["DEA"] and r["DIF"] < r["DEA"]:
            sig.iloc[i, sig.columns.get_loc("MACD死叉")] = True
        # RSI
        if 0 < r["RSI6"] < 30:
            sig.iloc[i, sig.columns.get_loc("RSI超卖")] = True
        if r["RSI6"] > 70:
            sig.iloc[i, sig.columns.get_loc("RSI超买")] = True
        # KDJ
        if 0 < r["J"] < 20:
            sig.iloc[i, sig.columns.get_loc("KDJ超卖")] = True
        if r["K"] > r["D"] and p["K"] <= p["D"]:
            sig.iloc[i, sig.columns.get_loc("KDJ金叉")] = True
        # 均线
        if close > r["MA5"] > r["MA20"]:
            sig.iloc[i, sig.columns.get_loc("均线多头")] = True
        if close < r["MA5"] < r["MA20"]:
            sig.iloc[i, sig.columns.get_loc("均线空头")] = True
        # 布林
        if r["BOLL_UP"] != r["BOLL_DN"]:
            bp = (close - r["BOLL_DN"]) / (r["BOLL_UP"] - r["BOLL_DN"]) * 100
            if bp < 20:
                sig.iloc[i, sig.columns.get_loc("布林下轨")] = True
            if bp > 80:
                sig.iloc[i, sig.columns.get_loc("布林上轨")] = True
        # 量价
        if prev_close > 0 and p["volume"] > 0:
            vr = r["volume"] / p["volume"]
            if close > prev_close and vr > 1.2:
                sig.iloc[i, sig.columns.get_loc("放量上涨")] = True
            if close < prev_close and vr > 1.2:
                sig.iloc[i, sig.columns.get_loc("放量下跌")] = True
            if vr < 0.7:
                sig.iloc[i, sig.columns.get_loc("缩量")] = True
        # 乖离率（5日）
        if i >= 5:
            c5 = df.iloc[i - 5]["close"]
            if c5 > 0:
                mom = close / c5 - 1
                if mom < -0.10:
                    sig.iloc[i, sig.columns.get_loc("乖离超跌")] = True
                if mom > 0.15:
                    sig.iloc[i, sig.columns.get_loc("乖离过热")] = True
    return sig


def backtest(codes: list, start: str, end: str, idx_code: str = "000300.SH"):
    pro = ts.pro_api(TOKEN)
    # 指数基准（超额收益用）
    idx = pro.index_daily(ts_code=idx_code, start_date=start, end_date=end)
    idx_ret = dict(zip(idx["trade_date"], idx["pct_chg"] / 100))

    agg = {}  # 信号 -> [命中, 胜率分子, 收益和, 超额和]
    for col in ["MACD金叉", "MACD死叉", "RSI超卖", "RSI超买", "KDJ超卖", "KDJ金叉",
                "均线多头", "均线空头", "布林下轨", "布林上轨", "放量上涨", "放量下跌",
                "缩量", "乖离超跌", "乖离过热"]:
        agg[col] = [0, 0, 0.0, 0.0]

    for ci, code in enumerate(codes):
        try:
            df = pro.daily(ts_code=code, start_date=start, end_date=end)
        except Exception:  # noqa: BLE001
            continue
        if df is None or len(df) < 40:
            continue
        df = df.rename(columns={"vol": "volume"})  # Tushare vol → 统一 volume
        df = df.sort_values("trade_date").reset_index(drop=True)
        sig = _signals_of(df)
        dates = df["trade_date"].tolist()
        for i in range(len(df) - 1):
            t = dates[i]
            t1 = dates[i + 1]
            if t1 not in idx_ret:
                continue
            ret = (df.iloc[i + 1]["close"] / df.iloc[i]["close"] - 1) if df.iloc[i]["close"] else 0
            excess = ret - idx_ret[t1]
            for col in agg:
                if sig.iloc[i][col]:
                    agg[col][0] += 1
                    if ret > 0:
                        agg[col][1] += 1
                    agg[col][2] += ret
                    agg[col][3] += excess
        if (ci + 1) % 50 == 0:
            print(f"  已回测 {ci + 1}/{len(codes)} 只")
            time.sleep(0.5)

    rows = []
    for col, (cnt, up, ret_sum, ex_sum) in agg.items():
        if cnt == 0:
            continue
        rows.append({
            "信号": col,
            "命中次数": cnt,
            "次日胜率": f"{up / cnt:.1%}",
            "平均收益": f"{ret_sum / cnt:+.2%}",
            "平均超额": f"{ex_sum / cnt:+.2%}",
        })
    result = pd.DataFrame(rows).sort_values("平均超额", ascending=False)
    return result


if __name__ == "__main__":
    pro = ts.pro_api(TOKEN)
    # 沪深300成分
    w = pro.index_weight(index_code="399300.SZ", start_date="20260801", end_date="20260831")
    codes = w["con_code"].drop_duplicates().tolist()
    print(f"回测股票池：沪深300 共 {len(codes)} 只，最近 6 个月")
    r = backtest(codes, start="20260301", end="20260930")
    print(r.to_string(index=False))
    r.to_csv("output/信号回测_沪深300.csv", index=False, encoding="utf-8-sig")
    print("已保存 output/信号回测_沪深300.csv")
