"""量化选股主入口：短期表(每天) + 长期表(每周)。

短期表：截面因子加权 + 形态/技术指标/分时信号加减分
长期表：估值/质量/成长因子加权
"""
import argparse
import os
import sys
from datetime import datetime

import pandas as pd
import yaml

from stock_choose import daily_verify
from stock_choose.data.wencai_provider import WencaiProvider
from stock_choose.data.eastmoney_provider import EastmoneyProvider
from stock_choose.data.tushare_provider import TushareProvider
from stock_choose.push.pusher import format_long_message, push_serverchan
from stock_choose.strategy import evolution, intraday, patterns, sector, overseas
from stock_choose.strategy.scoring import score_stocks

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def load_config(path: str) -> dict:
    if not os.path.isabs(path):
        path = os.path.join(BASE_DIR, path)
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def apply_gates(df, gates_cfg: dict):
    g = gates_cfg
    if g.get("exclude_st") and "is_st" in df.columns:
        # is_st 可能有 NaN（分批查询 join 时缺失），fillna(False) 再取反
        df = df[~df["is_st"].fillna(False).astype(bool)]
    if g.get("roe_min", 0) > 0 and "roe" in df.columns:
        df = df[df["roe"] >= g["roe_min"]]
    if g.get("max_turnover", 0) > 0 and "turnover" in df.columns:
        df = df[df["turnover"] <= g["max_turnover"]]
    if "float_market_cap" in df.columns:
        lo = g.get("min_market_cap", 0)
        hi = g.get("max_market_cap", 0)
        if lo and lo > 0:
            df = df[df["float_market_cap"] >= lo]
        if hi and hi > 0:
            df = df[df["float_market_cap"] <= hi]
    return df


def filter_limit(df: pd.DataFrame) -> pd.DataFrame:
    """过滤今日涨停/跌停的票（次日买不进/卖不出）。

    涨停幅度：主板 10%、创业板/科创板(300/301/688) 20%、ST 5%。
    """
    if "pct_change" not in df.columns:
        return df
    pct = df["pct_change"]
    is_st = df.get("is_st", pd.Series(False, index=df.index)).fillna(False).astype(bool)

    def lim_for(code, st):
        if st:
            return 5.0      # ST 涨停 5%
        c = str(code).split(".")[0]
        return 20.0 if c.startswith(("300", "301", "688")) else 10.0

    limits = pd.Series([lim_for(c, st) for c, st in zip(df.index, is_st)], index=df.index)
    # pct_change 是百分数（1.44=1.44%），涨停阈值也是百分数（10/20/5），容差 0.5%
    limit_up = pct >= limits - 0.5
    # 只过滤涨停（回测：涨停次日追高跑输）；不过滤跌停（回测：跌停次日反弹）
    return df[~limit_up]


def position_size(level: str) -> int:
    """市场情绪 → 持仓数量（强满仓、中性减半、弱轻仓）。"""
    return {"偏强": 20, "中性": 10, "偏弱": 5}.get(level, 10)


def judge_sentiment(up_ratio, top_score, s_cfg: dict) -> dict:
    strong_up = s_cfg.get("strong_up_ratio", 0.6)
    strong_score = s_cfg.get("strong_top_score", 1.0)
    weak_up = s_cfg.get("weak_up_ratio", 0.4)
    weak_score = s_cfg.get("weak_top_score", 0.5)
    if up_ratio is None:
        return {"level": "未知", "advice": "数据不足", "up_ratio": None, "top_score": top_score}
    if up_ratio >= strong_up and top_score >= strong_score:
        level, advice = "偏强", "可以建仓"
    elif up_ratio < weak_up or top_score < weak_score:
        level, advice = "偏弱", "建议观望，暂不建仓"
    else:
        level, advice = "中性", "轻仓试探"
    return {"level": level, "advice": advice, "up_ratio": up_ratio, "top_score": top_score}


def detect_all_signals(codes: list) -> dict:
    """对候选池检测信号：形态+技术指标（日线）+ 分时（分钟）。"""
    signals_map = {}
    for i, code in enumerate(codes):
        sig = patterns.detect_patterns(code)          # 形态 + 技术指标
        sig.update(intraday.intraday_signals(code))   # 分时
        signals_map[code] = sig
        if (i + 1) % 10 == 0:
            print(f"      已检测 {i + 1}/{len(codes)}")
    return signals_map


def apply_signal_adjust(top, signals_map: dict, signal_weights: dict):
    """信号加减分：按 signal_weights 的正负自动分类（正权重=正面，负权重=风险）。"""
    def calc(code):
        sig = signals_map.get(code, {})
        pos = [t for t, w in signal_weights.items() if w > 0 and sig.get(t)]
        risk = [t for t, w in signal_weights.items() if w < 0 and sig.get(t)]
        adjust = sum(signal_weights.get(t, 0) for t in pos + risk)
        return pd.Series({"signal_score": adjust, "pos_tags": " ".join(pos), "risk_tags": " ".join(risk)})

    top = top.copy()
    info = top["code"].apply(calc)
    top["signal_score"] = info["signal_score"]
    top["pos_tags"] = info["pos_tags"]
    top["risk_tags"] = info["risk_tags"]
    top["final_score"] = top["total_score"] + top["signal_score"]
    top["rank"] = top["final_score"].rank(ascending=False, method="first").astype(int)
    return top.sort_values("final_score", ascending=False)


def run_short(cfg: dict, date: str, push: bool = True):
    """短期表：截面因子 + 信号加减分。"""
    st = cfg["short_term"]
    factor_cfg = dict(st["factors"])
    candidate_cfg = dict(st.get("candidate_factors", {}))
    scoring_cfg = cfg["scoring"]

    # 因子 mask：数据源拿不到的因子 weight 设 0（接口/配置保留，恢复数据源可重新启用）
    masked = set(st.get("masked_factors", []))
    for name in masked:
        if name in factor_cfg:
            factor_cfg[name]["weight"] = 0
        if name in candidate_cfg:
            candidate_cfg[name]["weight"] = 0

    # 进化权重覆盖（含之前收纳的候选因子、退役移除）
    factor_cfg = evolution.load_override(factor_cfg)

    print("[短期] 查询 Tushare 全市场数据（正式 + 候选因子）...")
    all_cfg = {**factor_cfg, **candidate_cfg}
    token = st.get("tushare_token", "")
    provider = TushareProvider(all_cfg, token)
    # 财务因子（季度数据）每周一更新，其余天读缓存
    df = provider.fetch(date, update_finance=is_weekly_update_day(date))
    if df is None or df.empty:
        raise RuntimeError(f"{date} 无全市场数据（休市或 Tushare 数据尚未更新），请确认日期或稍后再试")

    # 概念情绪因子：Tushare 拿不到概念数据，mask 掉（不计算）
    # df["sector_heat"] = sector.compute_sector_heat(df)

    up_ratio = float((df["pct_change"] > 0).mean()) if "pct_change" in df.columns else None
    all_factor_cols = [c for c in all_cfg.keys() if c in df.columns]

    # 进化闭环：算 IC（所有因子）+ 存快照（所有因子）
    prev_date, prev_df = evolution.find_prev_snapshot(date)
    if prev_df is not None:
        evolution.record_ic(date, evolution.compute_ic(prev_df, df, all_factor_cols))
    evolution.save_snapshot(df, all_factor_cols, date)

    # 候选因子自动收纳 / 正式因子自动退役（每周一执行）
    if is_weekly_update_day(date):
        pool_result = evolution.update_factor_pool(factor_cfg, candidate_cfg)
        if pool_result["activated"] or pool_result["deactivated"]:
            print(f"[进化] 收纳候选因子 {pool_result['activated']}，退役 {pool_result['deactivated']}")
            factor_cfg = evolution.load_override(dict(st["factors"]))

    factor_cols = [c for c in factor_cfg.keys() if c in df.columns]

    print(f"[短期] 门槛过滤（共 {len(df)} 只）...")
    df = apply_gates(df, st["gates"])
    df = filter_limit(df)  # 涨跌停过滤（次日买不进/卖不出）
    print(f"[短期] 涨跌停过滤后（共 {len(df)} 只）...")

    print("[短期] 截面因子打分 ...")
    scored = score_stocks(
        df[factor_cols], factor_cfg,
        clip_q=scoring_cfg.get("clip_quantile", 0.01),
        method=scoring_cfg.get("standardize", "zscore"),
        min_coverage=scoring_cfg.get("min_factor_coverage", 0.5),
    )

    top_n = scoring_cfg.get("top_n", 20)
    top = scored.head(top_n).copy()
    top.index.name = "code"
    top = top.reset_index()
    top.insert(1, "name", top["code"].map(df["name"]))

    # 信号检测（候选池）+ 加减分
    pattern_pool = scoring_cfg.get("pattern_pool", 50)
    pool_codes = scored.head(pattern_pool).index.tolist()
    print(f"[短期] 检测 {len(pool_codes)} 只候选池的形态/指标/分时信号 ...")
    signals_map = detect_all_signals(pool_codes)
    top = apply_signal_adjust(top, signals_map, st["signal_weights"])

    # 市场情绪
    sentiment = judge_sentiment(up_ratio, float(top["final_score"].mean()), cfg.get("sentiment", {}))

    # 外围风险：美股大跌 → 空仓（美股跌通常次日传导亚太/A股）
    overseas_sig = overseas.get_overseas_signal()
    risk = overseas.overseas_risk(overseas_sig)
    sentiment["overseas_risk"] = risk
    sentiment["overseas"] = overseas_sig

    # 仓位管理：外围风险→空仓，否则情绪→持仓数量（强20、中性10、弱5）
    pos_n = 0 if risk else position_size(sentiment["level"])
    top = top.head(pos_n)
    if len(top):
        top["rank"] = top["final_score"].rank(ascending=False, method="first").astype(int)

    # 输出
    out_path = os.path.join(BASE_DIR, "output", f"短期选股_{date.replace('-', '')}.xlsx")
    top.to_excel(out_path, index=False)
    print(f"[短期] 已保存：{out_path}")
    print(top[["rank", "name", "code", "total_score", "signal_score", "final_score", "pos_tags", "risk_tags"]].to_string(index=False))

    if is_weekly_update_day(date) and evolution.update_weights(factor_cfg):
        print("[进化] 权重已根据近期 IC 自动调整（每周）")
    return top, sentiment


def run_long(cfg: dict, date: str, push: bool = True):
    """长期表：估值/质量/成长因子。"""
    lt = cfg["long_term"]
    factor_cfg = lt["factors"]
    scoring_cfg = cfg["scoring"]

    print("[长期] 查询问财全市场数据 ...")
    provider = WencaiProvider(factor_cfg)
    df = provider.fetch()

    print(f"[长期] 剔除 ST（共 {len(df)} 只）...")
    if "is_st" in df.columns:
        df = df[~df["is_st"]]

    factor_cols = list(factor_cfg.keys())
    print("[长期] 因子打分 ...")
    scored = score_stocks(
        df[factor_cols], factor_cfg,
        clip_q=scoring_cfg.get("clip_quantile", 0.01),
        method=scoring_cfg.get("standardize", "zscore"),
        min_coverage=scoring_cfg.get("min_factor_coverage", 0.5),
    )

    top_n = scoring_cfg.get("long_top_n", 20)
    top = scored.head(top_n).copy()
    top.index.name = "code"
    top = top.reset_index()
    top.insert(1, "name", top["code"].map(df["name"]))

    out_path = os.path.join(BASE_DIR, "output", f"长期选股_{date.replace('-', '')}.xlsx")
    top.to_excel(out_path, index=False)
    print(f"[长期] 已保存：{out_path}")
    print(top[["rank", "name", "code", "total_score"]].to_string(index=False))

    if push:
        push_cfg = cfg.get("push", {})
        sendkey = push_cfg.get("sendkey", "")
        if push_cfg.get("enable") and sendkey.startswith("SCT"):
            content = format_long_message(date, top)
            ok = push_serverchan(sendkey, push_cfg.get("long_title", "每周价值选股"), content)
            print("[长期] 微信推送" + ("成功" if ok else "失败"))
    return top


def is_trading_day(date_str: str) -> bool:
    """判断是否交易日：优先用 akshare 交易日历（含节假日），失败退回周末判断。"""
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    if dt.weekday() >= 5:  # 周六(5)/周日(6)
        return False
    try:
        import akshare as ak
        cal = ak.tool_trade_date_hist_sina()
        trade_dates = set(cal["trade_date"].astype(str))
        return date_str in trade_dates
    except Exception:  # noqa: BLE001 —— 拿不到日历，默认工作日即交易日
        return True


def last_trading_day() -> str:
    """上一个交易日（早上跑时用「昨天」的 A股数据 + 昨晚美股，预测今天）。"""
    from datetime import timedelta
    d = datetime.now() - timedelta(days=1)
    for _ in range(10):  # 最多往前找 10 天，跳过周末/节假日
        if is_trading_day(d.strftime("%Y-%m-%d")):
            return d.strftime("%Y-%m-%d")
        d -= timedelta(days=1)
    return (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")


def is_weekly_update_day(date_str: str) -> bool:
    """是否「每周自进化」的日子（周一调权重/收纳退役，其余天只积累 IC）。"""
    return datetime.strptime(date_str, "%Y-%m-%d").weekday() == 0


# 收盘后（默认 15:30）跑当天数据，之前跑上一交易日数据（预测当天）
MARKET_CLOSE_TIME = "15:30"


def default_run_date() -> str | None:
    """默认跑哪个交易日。

    收盘后：跑当天数据；盘中/盘前：跑上一交易日（用昨天预测今天）；
    今天休市：返回 None（不跑）。
    """
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    if not is_trading_day(today):
        return None
    if now.strftime("%H:%M") >= MARKET_CLOSE_TIME:
        return today
    return last_trading_day()


def list_result_dates() -> list:
    """扫描 output/短期选股_YYYYMMDD.xlsx，返回已有结果的日期列表。"""
    import glob
    files = glob.glob(os.path.join(BASE_DIR, "output", "短期选股_*.xlsx"))
    dates = []
    for f in files:
        stem = os.path.basename(f).replace("短期选股_", "").replace(".xlsx", "")
        if len(stem) == 8 and stem.isdigit():
            dates.append(f"{stem[:4]}-{stem[4:6]}-{stem[6:]}")
    return sorted(dates)


def find_missing_trading_days(target_date: str, lookback_trading_days: int = 5) -> list:
    """找 target_date 之前最近 lookback_trading_days 个「交易日」里应跑但没结果的日期。

    按交易日窗口（跳过周末/节假日），不看自然日，避免窗口被长假吃掉。
    """
    from datetime import timedelta
    target = datetime.strptime(target_date, "%Y-%m-%d")
    results = set(list_result_dates())

    try:
        import akshare as ak
        cal = ak.tool_trade_date_hist_sina()
        all_td = [d for d in cal["trade_date"].astype(str).tolist() if d < target_date]
    except Exception:  # noqa: BLE001
        all_td = None

    if all_td is not None:
        recent = all_td[-lookback_trading_days:]
        return [d for d in recent if d not in results]

    # 无日历：退回按工作日回看
    missing = []
    d = target - timedelta(days=1)
    count = 0
    while count < lookback_trading_days:
        s = d.strftime("%Y-%m-%d")
        if d.weekday() < 5:
            count += 1
            if s not in results:
                missing.append(s)
        d -= timedelta(days=1)
    return sorted(missing)


def run_daily_pipeline(cfg: dict, date: str, push: bool = False) -> dict:
    """完整跑一次每日流程：选股 + 昨日验证 + 股票池更新 + 因子健康度。

    push=True 时发送 Server酱微信推送（仅定时任务用）；页面/更新数据调用时传 False。
    自进化（IC 记录/快照/每周调权）在 run_short 内部执行，调用即生效。
    """
    import json
    top, sentiment = run_short(cfg, date)

    # 每日验证 + 动态股票池（验证前一日选股，更新股票池）
    verify = daily_verify.verify_prev_selection(date)
    market_avg = None
    changes = {"added": [], "kept": [], "removed": []}
    if verify is not None:
        market_avg = daily_verify.get_market_avg()
        daily_verify.append_verify_record(date, verify, market_avg)
        if top is not None and len(top):
            names = dict(zip(top["code"], top["name"]))
            changes = daily_verify.update_watchlist(date, top["code"].tolist(), names,
                                                     up_ratio=sentiment.get("up_ratio"),
                                                     market_avg=market_avg)
        # 复盘撤票：外围风险时，撤掉前一天推的误判票
        if sentiment.get("overseas_risk"):
            misremoved = daily_verify.remove_misjudged(verify["prev_date"], date)
            if misremoved:
                changes["removed"] = changes.get("removed", []) + misremoved
                print(f"[复盘] 外围风险，撤掉昨日误判 {len(misremoved)} 只")
        print(f"[验证] 昨日({verify['prev_date']})胜率 {verify['win_rate']:.0%}，"
              f"股票池 新增{len(changes['added'])} 移除{len(changes['removed'])}")
    else:
        print("[验证] 无上一交易日选股结果，跳过（首次运行）")

    # 合并推送文案：选股 + 昨日表现 + 胜率曲线 + 完整股票池
    msg = daily_verify.format_daily_message(date, top, sentiment, verify, market_avg, changes)

    # 因子健康度（direction×IC 有效值变化，作为最后一项）
    health = evolution.format_factor_health(
        cfg["short_term"].get("factors", {}),
        cfg["short_term"].get("candidate_factors", {}),
    )
    if health:
        msg += "\n\n**因子健康度（方向×IC）：**\n" + health

    if push:
        push_cfg = cfg.get("push", {})
        sendkey = push_cfg.get("sendkey", "")
        if push_cfg.get("enable") and sendkey.startswith("SCT"):
            ok = push_serverchan(sendkey, f"{push_cfg.get('title', '每日量化选股')} · {sentiment['level']}", msg)
            print("[推送] 微信推送" + ("成功" if ok else "失败"))

    # 保存 summary 供页面/Web 版读取
    try:
        summary = {
            "date": date,
            "sentiment": sentiment,
            "health": health,
            "verify": verify,
            "changes": {k: [str(x) for x in v] for k, v in changes.items()},
            "market_avg": market_avg,
        }
        with open(os.path.join(BASE_DIR, "output", "summary.json"), "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, default=str)
    except Exception:  # noqa: BLE001
        pass

    return {
        "date": date,
        "top": top,
        "sentiment": sentiment,
        "verify": verify,
        "market_avg": market_avg,
        "changes": changes,
        "health": health,
        "msg": msg,
    }


def main():
    parser = argparse.ArgumentParser(description="量化选股工具")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--date", default=None, help="日期 YYYY-MM-DD（默认上一交易日）")
    parser.add_argument("--long", action="store_true", help="同时跑长期表")
    args = parser.parse_args()

    cfg = load_config(args.config)

    # 日期策略：收盘后(>=15:30)跑当天；否则跑上一交易日（预测当天）；休市不跑
    if args.date:
        date = args.date
        if not is_trading_day(date):
            print(f"[跳过] {date} 非交易日（周末/节假日），不跑选股")
            return
    else:
        date = default_run_date()

        # 检测缺失交易日：交互模式下询问是否补跑，非交互模式（定时任务）自动跳过。
        # 休市日也检测（以今天为参考），这样周末/节假日打开时也能补跑漏掉的日子。
        ref_date = date or datetime.now().strftime("%Y-%m-%d")
        missing = find_missing_trading_days(ref_date)
        if missing:
            msg = f"[检测] 缺失交易日（output 无结果）：{', '.join(missing)}"
            if sys.stdin.isatty():
                print(msg)
                try:
                    ans = input("是否补跑？(y/n，默认 n)：").strip().lower()
                except (EOFError, KeyboardInterrupt):
                    ans = ""
                if ans in ("y", "yes"):
                    for md in missing:
                        print(f"[补跑] {md} ...")
                        run_short(cfg, md)
            else:
                print(f"{msg}；非交互模式自动跳过（可手动 python main.py --date <缺失日> 补跑）")

        if date is None:
            print(f"[跳过] 今天 {datetime.now().strftime('%Y-%m-%d')} 休市（周末/节假日），不跑选股")
            return

    pipeline = run_daily_pipeline(cfg, date, push=True)

    # 长期表：每周一跑（或手动 --long 强制）
    is_monday = datetime.strptime(date, "%Y-%m-%d").weekday() == 0
    if args.long or is_monday:
        run_long(cfg, date)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        log = os.path.join(BASE_DIR, "output", "task_log.txt")
        with open(log, "a", encoding="utf-8") as f:
            f.write(f"\n[{datetime.now()}] 异常退出：\n{traceback.format_exc()}\n")
        raise
