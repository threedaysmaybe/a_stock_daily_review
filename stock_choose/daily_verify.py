"""每日验证 + 动态股票池。

每天收盘后：
  1. 验证上一个交易日选出的股票，今天的真实胜率 + 组合涨幅 + 大盘对比
  2. 更新股票池：弱股（今日跌超阈值）移除，新股（今日选出）加入

输出：
  output/验证记录.csv —— 每天一行（日期/胜率/组合涨幅/大盘/超额）
  output/股票池.csv   —— 当前持仓关注列表
"""
import os
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from stock_choose.strategy.patterns import fetch_history

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")

# 淘汰参数默认值（可被 config.yaml 的 watchlist 段覆盖）
WATCHLIST_DEFAULTS = {
    "excess_base": 0.03,          # 超额阈值基准（情绪差时：跑输大盘 3% 淘汰）
    "excess_tightest": 0.01,      # 超额阈值最严（情绪极好时：跑输大盘 1% 淘汰）
    "cumulative_drop": -0.08,     # 累计跌幅淘汰阈值（从加入日起，捕捉阴跌）
    "weak_up_ratio": 0.4,         # 情绪分下限（up_ratio 低于此 → 最宽松）
}


def load_watchlist_config() -> dict:
    """从 config.yaml 读淘汰参数，缺省用默认值。"""
    cfg = dict(WATCHLIST_DEFAULTS)
    try:
        import yaml
        with open(os.path.join(BASE_DIR, "config.yaml"), encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        wl_cfg = data.get("watchlist") or {}
        if isinstance(wl_cfg, dict):
            for k in cfg:
                if k in wl_cfg:
                    cfg[k] = wl_cfg[k]
    except Exception:  # noqa: BLE001
        pass
    return cfg


def dynamic_excess_threshold(up_ratio, cfg=None) -> float:
    """超额收益淘汰阈值（去弱留强）。

    个股今日涨幅 - 大盘涨幅 < 此阈值 → 视为「相对弱」，淘汰。
    情绪越好阈值越严（跑输大盘一点点就淘汰）：
    excess_base（情绪差，下限）~ excess_tightest（情绪极好）。
    """
    cfg = cfg or load_watchlist_config()
    base = float(cfg["excess_base"])
    tightest = float(cfg["excess_tightest"])
    weak = float(cfg["weak_up_ratio"])
    if up_ratio is None:
        return -base
    score = max(0.0, min(1.0, (up_ratio - weak) / (1.0 - weak)))
    return -(base - (base - tightest) * score)


def _is_trading_day(date_str: str) -> bool:
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    if dt.weekday() >= 5:
        return False
    try:
        import akshare as ak
        cal = ak.tool_trade_date_hist_sina()
        return date_str in set(cal["trade_date"].astype(str))
    except Exception:  # noqa: BLE001
        return True


def prev_trading_day(date_str: str) -> str:
    """找上一个交易日。"""
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    for i in range(1, 30):
        d = (dt - timedelta(days=i)).strftime("%Y-%m-%d")
        if _is_trading_day(d):
            return d
    return None


def get_today_returns(codes: list) -> dict:
    """拉取每只股票最新交易日涨跌幅（真实数据）。"""
    rets = {}
    for code in codes:
        try:
            h = fetch_history(code, days=10)
            if h is not None and len(h) >= 2:
                rets[code] = float(h["close"].iloc[-1] / h["close"].iloc[-2] - 1)
        except Exception:  # noqa: BLE001
            pass
    return rets


def get_today_prices(codes: list) -> dict:
    """拉取每只股票最新交易日收盘价（真实数据，用于累计跌幅）。"""
    prices = {}
    for code in codes:
        try:
            h = fetch_history(code, days=10)
            if h is not None and len(h) >= 1:
                prices[code] = float(h["close"].iloc[-1])
        except Exception:  # noqa: BLE001
            pass
    return prices


def get_market_avg() -> float:
    """用缓存沪深300成分股算今日等权平均涨幅（大盘基准）。"""
    import glob
    files = glob.glob(os.path.join(BASE_DIR, "cache", "*.csv"))
    rets = []
    for f in files:
        try:
            df = pd.read_csv(f).tail(3)
            if len(df) >= 2:
                rets.append(df["close"].iloc[-1] / df["close"].iloc[-2] - 1)
        except Exception:  # noqa: BLE001
            pass
    return float(np.mean(rets)) if rets else None


def load_watchlist() -> pd.DataFrame:
    path = os.path.join(OUTPUT_DIR, "股票池.csv")
    if os.path.exists(path):
        df = pd.read_csv(path)
        # 兼容旧格式：无「移除日期」列则补空
        if "移除日期" not in df.columns:
            df["移除日期"] = ""
        if "加入价" not in df.columns:
            df["加入价"] = ""
        # CSV 空值读成 NaN，转回空字符串（否则「活跃」判断失效）
        df["移除日期"] = df["移除日期"].fillna("").astype(str)
        return df
    return pd.DataFrame(columns=["code", "name", "加入日期", "移除日期", "加入价"])


def save_watchlist(df: pd.DataFrame):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    df.to_csv(os.path.join(OUTPUT_DIR, "股票池.csv"), index=False, encoding="utf-8-sig")


def remove_misjudged(prev_date: str, today: str) -> list:
    """外围风险复盘：撤掉前一天推的票（加入日期=prev_date 且未移除）。

    只撤前一天（prev_date）刚推、误判的票，更早的票不动。
    返回被撤下的 code 列表。
    """
    wl = load_watchlist()
    removed = []
    for idx, row in wl.iterrows():
        joined = str(row.get("加入日期", "")).strip()
        gone = str(row.get("移除日期", "")).strip()
        if joined == prev_date and gone == "":
            wl.at[idx, "移除日期"] = today
            removed.append(str(row["code"]))
    if removed:
        save_watchlist(wl)
    return removed


def verify_prev_selection(date_str: str) -> dict:
    """验证上一个交易日选出的股票，返回 {prev_date, codes, rets, win_rate, avg_ret}。"""
    prev = prev_trading_day(date_str)
    if prev is None:
        return None
    prev_file = os.path.join(OUTPUT_DIR, f"短期选股_{prev.replace('-', '')}.xlsx")
    if not os.path.exists(prev_file):
        return None
    prev_df = pd.read_excel(prev_file)
    codes = prev_df["code"].tolist()
    rets = get_today_returns(codes)
    arr = np.array([v for v in rets.values() if v is not None])
    if len(arr) == 0:
        return None
    return {
        "prev_date": prev,
        "codes": codes,
        "rets": rets,
        "win_rate": float((arr > 0).mean()),
        "avg_ret": float(arr.mean()),
        "n": len(arr),
    }


def update_watchlist(date_str: str, today_codes: list, today_names: dict, up_ratio=None, market_avg=None) -> dict:
    """更新股票池（幂等：同一天多次运行结果一致）。

    淘汰逻辑（去弱留强）：
    - 绝对底线：单日跌幅 < -3% 必淘汰
    - 相对弱：跑输大盘超动态阈值（情绪好更严）→ 淘汰
    - 累计跌幅（从加入日起）< -8% → 淘汰
    - 被淘汰的票，之后再进 top20 可重新加入
    """
    wl = load_watchlist()
    wl["code"] = wl["code"].astype(str)

    all_codes = list(set(wl["code"].tolist()) | set(today_codes)) if len(wl) else list(today_codes)
    rets = get_today_returns(all_codes)
    prices = get_today_prices(all_codes)

    wl_cfg = load_watchlist_config()
    excess_th = dynamic_excess_threshold(up_ratio, wl_cfg)
    cum_th = float(wl_cfg["cumulative_drop"])

    # 1) 移除：昨天及更早加入的活跃股票（今天才加入的从明天起验证）
    if len(wl):
        active = (wl["移除日期"].astype(str).str.strip().eq("")) & \
                 (wl["加入日期"].astype(str).str.strip() != date_str)
        for idx in wl.index:
            if not active.loc[idx]:
                continue
            code = wl.at[idx, "code"]
            r = rets.get(code)
            if r is None:
                continue
            # 去弱留强：跑输大盘超动态阈值（回测：相对弱的继续跑输，该淘汰）
            # 不用绝对跌幅淘汰——回测证明单日跌超-3%短期反弹（超跌反弹，该留）
            if market_avg is not None and (r - market_avg) < excess_th:
                wl.at[idx, "移除日期"] = date_str
                continue
            # 累计跌幅超阈值（阴跌）
            entry_price = pd.to_numeric(wl.at[idx, "加入价"], errors="coerce")
            cur_price = prices.get(code)
            if pd.notna(entry_price) and entry_price > 0 and cur_price is not None:
                cum = cur_price / entry_price - 1
                if cum < cum_th:
                    wl.at[idx, "移除日期"] = date_str

    # 2) 新增 / 重新加入：今天 top20 里的
    wl_codes = set(wl["code"].tolist())
    active_codes = set(wl.loc[wl["移除日期"].astype(str).str.strip().eq(""), "code"]) if len(wl) else set()
    new_rows = []
    for code in today_codes:
        code = str(code)
        if code in active_codes:
            continue  # 已活跃，跳过
        cur_price = prices.get(code)
        if code in wl_codes:
            # 之前被移除的票 → 重新加入（今天刚移除的不立即重入）
            idx = wl.index[wl["code"] == code][0]
            removed_date = str(wl.at[idx, "移除日期"]).strip()
            if removed_date == date_str:
                continue
            wl.at[idx, "移除日期"] = ""
            wl.at[idx, "加入日期"] = date_str
            if cur_price is not None:
                wl.at[idx, "加入价"] = cur_price
        else:
            new_rows.append({"code": code, "name": today_names.get(code, code),
                             "加入日期": date_str, "移除日期": "", "加入价": cur_price})
    if new_rows:
        wl = pd.concat([wl, pd.DataFrame(new_rows)], ignore_index=True)

    save_watchlist(wl)

    # 3) 计算推送标记
    added, removed, kept = [], [], []
    for _, row in wl.iterrows():
        code = row["code"]
        joined = str(row["加入日期"]).strip()
        removed_date = str(row["移除日期"]).strip()
        if joined == date_str:
            added.append({"code": code, "name": row["name"], "ret": rets.get(code)})
        elif removed_date == date_str:
            removed.append({"code": code, "name": row["name"], "ret": rets.get(code)})
        elif removed_date == "":
            kept.append({"code": code, "name": row["name"], "ret": rets.get(code)})

    return {"added": added, "removed": removed, "kept": kept, "watchlist_df": wl}


def append_verify_record(date_str: str, verify: dict, market_avg: float):
    """追加一行验证记录。"""
    path = os.path.join(OUTPUT_DIR, "验证记录.csv")
    record = {
        "日期": date_str,
        "前日": verify["prev_date"],
        "胜率": round(verify["win_rate"], 4),
        "上涨数": int(verify["win_rate"] * verify["n"]),
        "总数": verify["n"],
        "组合涨幅": round(verify["avg_ret"], 4),
        "大盘涨幅": round(market_avg, 4) if market_avg is not None else "",
        "超额": round(verify["avg_ret"] - market_avg, 4) if market_avg is not None else "",
    }
    df = pd.DataFrame([record])
    if os.path.exists(path):
        # 同一天重复跑：更新当天记录，而不是新增重复日期
        old = pd.read_csv(path)
        old = old[old["日期"].astype(str) != date_str]
        df = pd.concat([old, df], ignore_index=True)
        df.to_csv(path, index=False, encoding="utf-8-sig")
    else:
        df.to_csv(path, index=False, encoding="utf-8-sig")


def load_verify_records() -> pd.DataFrame:
    """读验证记录（用于画胜率曲线）。"""
    path = os.path.join(OUTPUT_DIR, "验证记录.csv")
    if os.path.exists(path):
        return pd.read_csv(path)
    return pd.DataFrame()


def format_winrate_chart(records: pd.DataFrame, n: int = 15) -> str:
    """最近 n 个交易日的胜率 ASCII 柱状图（微信可直接显示，无需图床）。"""
    if records is None or records.empty:
        return "（暂无胜率记录）"
    recent = records.tail(n)
    lines = []
    for _, row in recent.iterrows():
        win = float(row["胜率"])
        bar_len = int(win * 10 + 0.5)  # 四舍五入到整数格
        bar = "█" * bar_len + "░" * (10 - bar_len)
        lines.append(f"{str(row['日期'])[-5:]} {bar} {win:.0%}")
    return "\n".join(lines)


def _clean_str(v) -> str:
    """NaN/None 转空字符串。"""
    if v is None or (isinstance(v, float) and v != v):
        return ""
    return str(v)


def _fmt_ret(r) -> str:
    return f"{r:+.2%}" if r is not None else "N/A"


def format_daily_message(date_str: str, top, sentiment: dict, verify: dict,
                         market_avg: float, changes: dict) -> str:
    """合并后的完整推送（Markdown 表格，微信可正确渲染）。"""
    up_ratio = sentiment.get("up_ratio")
    up_str = f"{up_ratio:.0%}" if up_ratio is not None else "N/A"

    lines = [
        f"**每日量化选股 · {date_str}**",
        "",
        f"市场情绪：{sentiment.get('level', '')}｜上涨 {up_str}｜{sentiment.get('advice', '')}",
    ]

    # 外围风险提示（美股昨晚 + 日韩当天开盘）
    if sentiment.get("overseas_risk"):
        ov = sentiment.get("overseas") or {}
        us_parts, open_parts = [], []
        for k, label in [("us_nasdaq", "纳指"), ("us_sp500", "标普")]:
            if ov.get(k) is not None:
                us_parts.append(f"{label} {ov[k]:+.2%}")
        for k, label in [("kr_open", "韩国开盘"), ("jp_open", "日经开盘")]:
            if ov.get(k) is not None:
                open_parts.append(f"{label} {ov[k]:+.2%}")
        us_str = "、".join(us_parts) if us_parts else "无"
        open_str = "、".join(open_parts) if open_parts else "无"
        lines.append(f"⚠️ 外围风险：美股[{us_str}]，日韩开盘[{open_str}]，建议空仓")

    # 明日参考阈值（分市场，第二天不开电脑时自己判断）
    lines.append("")
    lines.append("**明日参考（任一触发建议别买）：**")
    lines.append("")
    lines.append("| 市场 | 阈值 |")
    lines.append("|------|------|")
    lines.append("| 美股收盘 | 跌超 2% |")
    lines.append("| 韩国开盘 | 跌超 2% |")
    lines.append("| 日经开盘 | 跌超 2% |")

    def _append_group(title: str, df):
        lines.append("")
        lines.append(f"**{title}：**")
        lines.append("")
        lines.append("| 排名 | 名称 | 代码 | 得分 | 看多 | 风险 |")
        lines.append("|:---:|:---|:---|:---:|:---|:---|")
        for _, row in df.iterrows():
            sign = "+" if row.get("final_score", 0) >= 0 else ""
            pos = _clean_str(row.get("pos_tags", ""))
            risk = _clean_str(row.get("risk_tags", ""))
            code = str(row["code"]).split(".")[0]  # 去掉 .SZ/.SH 后缀
            lines.append(f"| {int(row['rank'])} | {row['name']} | {code} | {sign}{row['final_score']:.2f} | {pos} | {risk} |")

    # 今日精选 Top20，分「主板」和「创业板/科创板」两组（空仓时跳过）
    if top is None or len(top) == 0:
        lines.append("")
        lines.append("**今日精选：空仓（外围风险），今日不选股**")
    else:
        top20 = top.head(20)
        is_cyb = top20["code"].astype(str).str.startswith(("300", "301", "688"))
        main_top = top20[~is_cyb]
        cyb_top = top20[is_cyb]
        _append_group("今日精选·主板", main_top)
        if len(cyb_top):
            _append_group("今日精选·创业板/科创板", cyb_top)

    if verify is not None:
        win = verify["win_rate"]
        up = int(win * verify["n"])
        lines.append("")
        lines.append(f"**昨日({verify['prev_date']})选股表现：**")
        lines.append("")
        lines.append("| 指标 | 数值 |")
        lines.append("|:---|:---:|")
        lines.append(f"| 胜率 | {win:.0%}（{up}/{verify['n']} 上涨）|")
        lines.append(f"| 组合涨幅 | {verify['avg_ret']:+.2%} |")
        if market_avg is not None:
            lines.append(f"| 大盘涨幅 | {market_avg:+.2%} |")
            lines.append(f"| 超额 | {verify['avg_ret'] - market_avg:+.2%} |")
        lines.append("")
        lines.append("**近15日胜率曲线：**")
        lines.append("```")
        lines.append(format_winrate_chart(load_verify_records()))
        lines.append("```")

    # 股票池：Markdown 表格（+新增 / ~~删除线~~ / 空格保留）
    added = changes.get("added", [])
    kept = changes.get("kept", [])
    removed = changes.get("removed", [])
    total = len(added) + len(kept) + len(removed)

    def _is_cyb(code):
        return str(code).startswith(("300", "301", "688"))

    def _pool_rows(items):
        out = ["| 名称 | 代码 | 今日涨幅 |", "|:---|:---|:---:|"]
        for name, code, ret, status in items:
            code_short = str(code).split(".")[0]
            if status == "add":
                label = f"🔴+{name}"
            elif status == "del":
                label = f"🟢~~{name}~~"
            else:
                label = name
            out.append(f"| {label} | {code_short} | {_fmt_ret(ret)} |")
        return out

    all_items = []
    for a in added:
        all_items.append((a["name"], a["code"], a["ret"], "add"))
    for k in kept:
        all_items.append((k["name"], k["code"], k["ret"], "keep"))
    for r in removed:
        all_items.append((r["name"], r["code"], r["ret"], "del"))

    main = [x for x in all_items if not _is_cyb(x[1])]
    cyb = [x for x in all_items if _is_cyb(x[1])]

    lines.append("")
    lines.append(f"**股票池·主板（{len(main)} 只）：**")
    lines.append("")
    lines.extend(_pool_rows(main))
    if cyb:
        lines.append("")
        lines.append(f"**股票池·创业板/科创板（{len(cyb)} 只）：**")
        lines.append("")
        lines.extend(_pool_rows(cyb))

    return "\n".join(lines)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=None, help="日期 YYYY-MM-DD（默认今天）")
    args = parser.parse_args()
    date_str = args.date or datetime.now().strftime("%Y-%m-%d")

    verify = verify_prev_selection(date_str)
    if verify is None:
        print(f"[验证] 无上一个交易日的选股结果，跳过")
    else:
        market_avg = get_market_avg()
        append_verify_record(date_str, verify, market_avg)
        print(f"[验证] 昨日({verify['prev_date']})胜率 {verify['win_rate']:.0%} "
              f"({int(verify['win_rate']*verify['n'])}/{verify['n']}) 组合 {verify['avg_ret']:+.2%} "
              f"大盘 {market_avg:+.2%}")
