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

# 空仓记录：记录每天为什么没选股，供次日推送/页面说明原因
EMPTY_LOG = os.path.join(OUTPUT_DIR, "空仓记录.csv")

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


_TRADE_DAY_SET = None
_EMPTY_DAYS_CACHE = None


def _trade_day_set() -> set:
    """交易日历集合（进程内缓存）：优先 output/trade_calendar.txt，其次 akshare。"""
    global _TRADE_DAY_SET
    if _TRADE_DAY_SET is None:
        days = set()
        p = os.path.join(OUTPUT_DIR, "trade_calendar.txt")
        try:
            if os.path.exists(p):
                with open(p, encoding="utf-8") as f:
                    days = {ln.strip() for ln in f if ln.strip()}
        except Exception:  # noqa: BLE001
            days = set()
        if not days:
            try:
                import akshare as ak
                days = set(ak.tool_trade_date_hist_sina()["trade_date"].astype(str))
            except Exception:  # noqa: BLE001
                days = set()
        _TRADE_DAY_SET = days
    return _TRADE_DAY_SET


def _is_trading_day(date_str: str) -> bool:
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    if dt.weekday() >= 5:  # 周六/周日
        return False
    days = _trade_day_set()
    if days:
        return date_str in days
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
    """大盘基准：沪深300指数最新交易日涨幅（真实收盘数据）。

    旧实现读 cache/*.csv 成分股，但该缓存在 2026-08 之后就不再更新，
    导致「大盘涨幅」长期恒为 -0.82%、超额收益全部失真。
    改为直接取沪深300指数日线；取不到时返回 None（页面/推送会省略该行）。
    """
    try:
        import akshare as ak
        idx = ak.stock_zh_index_daily(symbol="sh000300")
        closes = pd.to_numeric(idx["close"], errors="coerce").dropna()
        if len(closes) >= 2:
            return float(closes.iloc[-1] / closes.iloc[-2] - 1)
    except Exception:  # noqa: BLE001
        pass
    try:
        import akshare as ak
        idx = ak.stock_zh_index_daily_em(symbol="sh000300")
        closes = pd.to_numeric(idx["close"], errors="coerce").dropna()
        if len(closes) >= 2:
            return float(closes.iloc[-1] / closes.iloc[-2] - 1)
    except Exception:  # noqa: BLE001
        return None


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
            removed.append({"code": str(row["code"]), "name": str(row.get("name", "")), "ret": None})
    if removed:
        save_watchlist(wl)
    return removed


def verify_prev_selection(date_str: str) -> dict:
    """验证上一个交易日选出的股票，返回 {prev_date, codes, rets, win_rate, avg_ret, prev_is_observe}。

    空仓日的候选也会记录（suggest_buy=False），照样参与验证，
    这样胜率序列不断档，也能评估「避险空仓」是否真的躲过了下跌。
    """
    prev = prev_trading_day(date_str)
    if prev is None:
        return None
    prev_file = os.path.join(OUTPUT_DIR, f"短期选股_{prev.replace('-', '')}.xlsx")
    if not os.path.exists(prev_file):
        return None
    prev_df = pd.read_excel(prev_file)
    codes = prev_df["code"].tolist()
    prev_observe = False
    if "suggest_buy" in prev_df.columns and len(prev_df):
        flags = prev_df["suggest_buy"].astype(str).str.strip().str.lower()
        prev_observe = not flags.isin(["true", "1", "1.0"]).any()
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
        "prev_is_observe": prev_observe,
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


def append_verify_record(date_str: str, verify: dict, market_avg: float, note: str = "",
                         prev_date: str = ""):
    """追加一行验证记录。

    verify 为 None 时（前一日空仓/无结果文件）也写一行：胜率等留空、写明说明，
    这样「验证记录」和「胜率曲线」里不会出现无解释的缺口。
    """
    path = os.path.join(OUTPUT_DIR, "验证记录.csv")
    if verify is None:
        record = {
            "日期": date_str,
            "前日": prev_date,
            "前日类型": "无验证",
            "胜率": "",
            "上涨数": "",
            "总数": "",
            "组合涨幅": "",
            "大盘涨幅": "",
            "超额": "",
            "说明": note or "前一日无选股结果（空仓或未跑），无胜率",
        }
    else:
        record = {
            "日期": date_str,
            "前日": verify["prev_date"],
            "前日类型": "空仓观察" if verify.get("prev_is_observe") else "建仓",
            "胜率": round(verify["win_rate"], 4),
            "上涨数": int(verify["win_rate"] * verify["n"]),
            "总数": verify["n"],
            "组合涨幅": round(verify["avg_ret"], 4),
            "大盘涨幅": round(market_avg, 4) if market_avg is not None else "",
            "超额": round(verify["avg_ret"] - market_avg, 4) if market_avg is not None else "",
            "说明": "",
        }
    df = pd.DataFrame([record])
    if os.path.exists(path):
        # 同一天重复跑：更新当天记录，而不是新增重复日期
        old = pd.read_csv(path)
        if "前日类型" not in old.columns:
            old["前日类型"] = "建仓"  # 历史记录统一按建仓口径
        if "说明" not in old.columns:
            old["说明"] = ""
        old = old[old["日期"].astype(str) != date_str]
        df = pd.concat([old, df], ignore_index=True)
        df.to_csv(path, index=False, encoding="utf-8-sig")
    else:
        df.to_csv(path, index=False, encoding="utf-8-sig")


def load_verify_records() -> pd.DataFrame:
    """读验证记录（用于画胜率曲线）。"""
    path = os.path.join(OUTPUT_DIR, "验证记录.csv")
    if not os.path.exists(path):
        return pd.DataFrame()
    df = pd.read_csv(path)
    for col, default in (("前日类型", "建仓"), ("说明", "")):
        if col not in df.columns:
            df[col] = default
    return df


def record_empty_day(date_str: str, reason: str, level: str = ""):
    """记录空仓日及原因（同一天重复跑覆盖旧行）。"""
    try:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        df = pd.DataFrame(columns=["日期", "原因", "情绪"])
        if os.path.exists(EMPTY_LOG):
            try:
                df = pd.read_csv(EMPTY_LOG)
            except Exception:  # noqa: BLE001
                pass
        df = df[df["日期"].astype(str).str.strip() != date_str]
        df.loc[len(df)] = [date_str, reason or "", level or ""]
        df.to_csv(EMPTY_LOG, index=False, encoding="utf-8-sig")
    except Exception:  # noqa: BLE001 —— 只读环境静默失败
        pass


def get_empty_reason(date_str: str) -> str:
    """查某天的空仓原因（没有记录返回空字符串）。"""
    if not date_str:
        return ""
    try:
        if os.path.exists(EMPTY_LOG):
            df = pd.read_csv(EMPTY_LOG)
            row = df[df["日期"].astype(str).str.strip() == date_str]
            if len(row):
                return str(row.iloc[0].get("原因", "") or "").strip()
    except Exception:  # noqa: BLE001
        pass
    return ""


def _empty_day_set() -> set:
    """空仓日集合。

    来源一：空仓记录.csv（近期记录）；
    来源二：反推「短期选股_YYYYMMDD.xlsx 存在但 0 行」的历史空仓日
    （旧版本空仓日不记录原因，靠这个也能正确标注「前日空仓」）。
    """
    global _EMPTY_DAYS_CACHE
    if _EMPTY_DAYS_CACHE is not None:
        return _EMPTY_DAYS_CACHE
    days = set()
    try:
        if os.path.exists(EMPTY_LOG):
            df = pd.read_csv(EMPTY_LOG)
            days |= {str(x).strip() for x in df["日期"].astype(str)}
    except Exception:  # noqa: BLE001
        pass
    try:
        import glob
        for f in glob.glob(os.path.join(OUTPUT_DIR, "短期选股_*.xlsx")):
            stem = os.path.basename(f).replace("短期选股_", "").replace(".xlsx", "")
            if not (len(stem) == 8 and stem.isdigit()):
                continue
            try:
                if len(pd.read_excel(f)) == 0:
                    days.add(f"{stem[:4]}-{stem[4:6]}-{stem[6:]}")
            except Exception:  # noqa: BLE001
                continue
    except Exception:  # noqa: BLE001
        pass
    _EMPTY_DAYS_CACHE = days
    return days


def _last_trading_day_on_or_before(date_str: str) -> str:
    """<= date_str 的最近交易日。"""
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    for i in range(0, 40):
        d = (dt - timedelta(days=i)).strftime("%Y-%m-%d")
        if _is_trading_day(d):
            return d
    return date_str


def _disp_width(s: str) -> int:
    """显示宽度（中文/全角算 2 格），用于等宽对齐。"""
    return sum(2 if ord(ch) > 0x2E80 else 1 for ch in s)


def _pad(s: str, width: int) -> str:
    """右侧补空格到指定显示宽度。"""
    return s + " " * max(0, width - _disp_width(s))


def _rpad(s: str, width: int) -> str:
    """左侧补空格到指定显示宽度（右对齐）。"""
    return " " * max(0, width - _disp_width(s)) + s


BAR_W = 5       # 柱宽（ASCII：# 实心 / - 空心，任何字体都是 1 格）
TEXT_W = 8      # 文本列宽（"没有胜率" = 4 个汉字 = 8 格，最宽者）
CELL_W = 5 + 1 + BAR_W + 1 + TEXT_W  # 日期 + 空格 + 柱 + 空格 + 文本 = 20


def _day_cell(ds: str, row, empty_days: set) -> str:
    """单日单元格：`MM-DD ###--   60%`，文本右对齐到最宽（没有胜率也显示）。

    柱的含义（全部 ASCII，任何字体宽度一致）：
      ###--  有胜率
      -----  没有胜率（前一日空仓，无可验证股票）
      .....  没有胜率（当日没跑选股）
      =====  没有胜率（休市）
    """
    key = ds[5:]
    bar = "-" * BAR_W
    text = "没有胜率"
    if not _is_trading_day(ds):
        text, bar = "休市", "=" * BAR_W
    elif row is not None:
        win = pd.to_numeric(row.get("胜率"), errors="coerce")
        if not pd.isna(win):
            win = float(win)
            filled = int(win * BAR_W + 0.5)
            bar = "#" * filled + "-" * (BAR_W - filled)
            obs = str(row.get("前日类型") or "").strip() == "空仓观察"
            text = f"{win:.0%}" + ("*" if obs else "")
    else:
        prev = prev_trading_day(ds)
        if not (prev and prev in empty_days):
            bar = "." * BAR_W  # 当日没跑
    return f"{key} {bar} {_rpad(text, TEXT_W)}"


def _month_days(year: int, month: int, until: str) -> list:
    """某月要显示的日期列表（自然日，截止到 until；未来日期不显示）。"""
    import calendar as _cal
    end_day = _cal.monthrange(year, month)[1]
    out = []
    for day in range(1, end_day + 1):
        ds = f"{year:04d}-{month:02d}-{day:02d}"
        if ds > until:
            break
        out.append(ds)
    return out


def format_winrate_chart(records: pd.DataFrame, n: int = None, until: str = None) -> str:
    """胜率展示：上个月 / 本月 两列对照 + 年内更早交易日的平均胜率。

    单元格含义（柱宽 5，文本右对齐到「没有胜率」的宽度）：
      10-15 ####-      80%   正常建仓日胜率
      10-16 -----       0%   胜率为 0%（真跌了，不是"无胜率"）
      11-20 ###--      60%*  前一日空仓，观察名单按"假设买入"验证（* 标注）
      11-03 ----- 没有胜率   前一日空仓，无可验证股票
      10-08 ..... 没有胜率   当日没跑选股
      10-01 =====     休市   周末/节假日
    """
    if records is None or records.empty:
        return "（暂无胜率记录）"
    recs = records.copy()
    recs["日期"] = recs["日期"].astype(str).str.strip()
    by_date = {r["日期"]: r for _, r in recs.iterrows()}
    empty_days = _empty_day_set()

    last = (until or recs["日期"].max()).strip()
    end_dt = datetime.strptime(last, "%Y-%m-%d")
    cur_y, cur_m = end_dt.year, end_dt.month
    prev_y, prev_m = (cur_y - 1, 12) if cur_m == 1 else (cur_y, cur_m - 1)

    left = _month_days(prev_y, prev_m, last)
    right = _month_days(cur_y, cur_m, last)

    def cell(ds):
        return _day_cell(ds, by_date.get(ds), empty_days)

    head = _pad(f"{prev_m}月", CELL_W) + " " + f"{cur_m}月"
    sep = "=" * (CELL_W * 2 + 1)
    lines = [head, sep]
    for i in range(max(len(left), len(right))):
        a = cell(left[i]) if i < len(left) else " " * CELL_W
        b = cell(right[i]) if i < len(right) else ""
        lines.append((_pad(a, CELL_W) + " " + b).rstrip())

    # 年内更早交易日（上月之前）：只给平均胜率，没跑/空仓不计入
    earlier_start = f"{cur_y:04d}-01-01"
    earlier_end = f"{prev_y:04d}-{prev_m:02d}-01"
    wins = []
    for ds, row in by_date.items():
        if earlier_start <= ds < earlier_end:
            w = pd.to_numeric(row.get("胜率"), errors="coerce")
            if not pd.isna(w):
                wins.append(float(w))
    lines.append("")
    lines.append("###-- 胜率　* =空仓观察日（按假设买入验证）")
    lines.append("----- 没有胜率(前日空仓)　..... 没有胜率(当日未跑)　===== 没有胜率(休市)")
    earlier_end_disp = (datetime(prev_y, prev_m, 1) - timedelta(days=1)).strftime("%Y-%m-%d")
    if wins:
        avg = sum(wins) / len(wins)
        up = sum(1 for w in wins if w >= 0.5)
        lines.append(
            f"本年更早交易日（{earlier_start} ~ {earlier_end_disp}）平均胜率：{avg:.0%}"
            f"（{len(wins)} 个交易日有胜率，{up} 天过半上涨）"
        )
    else:
        lines.append(
            f"本年更早交易日（{earlier_start} ~ {earlier_end_disp}）：没有胜率（无有效记录）"
        )
    return "\n".join(lines)


def _clean_str(v) -> str:
    """NaN/None 转空字符串。"""
    if v is None or (isinstance(v, float) and v != v):
        return ""
    return str(v)


def _fmt_ret(r) -> str:
    return f"{r:+.2%}" if r is not None else "N/A"


def format_daily_message(date_str: str, top, sentiment: dict, verify: dict,
                         market_avg: float, changes: dict,
                         verify_none_reason: str = "",
                         verify_none_date: str = "") -> str:
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

    # 今日精选 Top20，分「主板」和「创业板/科创板」两组（空仓日改为观察名单）
    _pos_n = int(sentiment.get("pos_n") or 0)
    _is_empty_day = (top is None) or (len(top) == 0) or (_pos_n <= 0)
    if _is_empty_day:
        reason = sentiment.get("empty_reason") or "未给出"
        lines.append("")
        lines.append(f"**今日精选：空仓（{reason}），今日不建仓**")
        if top is not None and len(top):
            obs = "、".join(
                f"{row['name']}({str(row['code']).split('.')[0]})"
                for _, row in top.head(10).iterrows()
            )
            lines.append("")
            lines.append(f"观察名单（仅记录，不建议买入，次日仍计入验证）：{obs}")
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
        if verify.get("prev_is_observe"):
            lines.append(f"**昨日({verify['prev_date']})空仓观察名单表现（若买入的假设收益）：**")
        else:
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
        lines.append("**胜率（上月 / 本月，* = 空仓观察）：**")
        lines.append("```")
        lines.append(format_winrate_chart(load_verify_records(), until=date_str))
        lines.append("```")
    else:
        if verify_none_reason:
            tip = f"（{verify_none_date} 空仓：{verify_none_reason}，无可验证股票）" if verify_none_date \
                else f"（空仓：{verify_none_reason}，无可验证股票）"
        else:
            tip = "（昨日未选股或无记录）"
        lines.append("")
        lines.append(f"**昨日选股表现：无{tip}**")
        # 仍然展示最近一次有效验证，避免"整段消失、什么都看不到"
        recs = load_verify_records()
        if recs is not None and len(recs):
            try:
                last = recs.iloc[-1]
                lw = float(last["胜率"])
                ln = int(float(last["总数"]))
                lines.append("")
                lines.append(
                    f"最近一次验证（{last['日期']} 验证 {last['前日']}）："
                    f"胜率 {lw:.0%}（{int(lw * ln)}/{ln} 上涨），"
                    f"组合 {float(last['组合涨幅']):+.2%}"
                )
            except Exception:  # noqa: BLE001
                pass
        lines.append("")
        lines.append("**胜率（上月 / 本月，* = 空仓观察）：**")
        lines.append("```")
        lines.append(format_winrate_chart(recs, until=date_str))
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
    if total == 0:
        lines.append("**股票池：空（暂无活跃标的）**")
    else:
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
