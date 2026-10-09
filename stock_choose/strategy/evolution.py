"""在线因子进化：每天验证 IC，定期自动调权重。

思路：
  1. 每天选股后，保存全市场因子快照（snapshot_YYYYMMDD.csv）
  2. 每天用「昨天因子值」对「今天涨跌幅」算 Rank IC，存入 ic_history.csv
  3. 累积足够天数后，用最近 N 天的平均 IC 调整权重，写入 weights_override.json
"""
import glob
import json
import os

import numpy as np
import pandas as pd

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
IC_FILE = os.path.join(OUTPUT_DIR, "ic_history.csv")
OVERRIDE_FILE = os.path.join(OUTPUT_DIR, "weights_override.json")


def _snapshot_path(date: str) -> str:
    return os.path.join(OUTPUT_DIR, f"snapshot_{date.replace('-', '')}.csv")


def save_snapshot(df, factor_cols: list, date: str):
    """保存当天全市场因子快照（用于次日算 IC）。"""
    df[factor_cols].to_csv(_snapshot_path(date))


def find_prev_snapshot(today: str):
    """找最近一个非今天的快照，返回 (date, df)。"""
    files = glob.glob(os.path.join(OUTPUT_DIR, "snapshot_*.csv"))
    today_key = today.replace("-", "")
    candidates = []
    for f in files:
        key = os.path.basename(f).replace("snapshot_", "").replace(".csv", "")
        if key != today_key:
            candidates.append((key, f))
    if not candidates:
        return None, None
    candidates.sort()
    prev_key, prev_file = candidates[-1]
    df = pd.read_csv(prev_file, index_col=0)
    return prev_key, df


def compute_ic(prev_df: pd.DataFrame, today_df: pd.DataFrame,
               factor_cols: list) -> dict:
    """Rank IC：昨天因子值 vs 今天涨跌幅（spearman 相关，更稳健）。"""
    ic = {}
    for f in factor_cols:
        if f not in prev_df.columns or "pct_change" not in today_df.columns:
            ic[f] = np.nan
            continue
        merged = pd.DataFrame({f: prev_df[f], "ret": today_df["pct_change"]}).dropna()
        if len(merged) < 30:
            ic[f] = np.nan
        else:
            # rank 后算 pearson 等价于 spearman，避免依赖 scipy
            ic[f] = merged[f].rank().corr(merged["ret"].rank())
    return ic


def record_ic(date: str, ic_dict: dict):
    """把当天各因子 IC 记录到 ic_history.csv（同日期覆盖，避免重复）。"""
    row = {"date": date, **ic_dict}
    df_new = pd.DataFrame([row])
    if os.path.exists(IC_FILE):
        df_old = pd.read_csv(IC_FILE)
        df_old = df_old[df_old["date"] != date]  # 同一天重跑：覆盖而非追加
        df = pd.concat([df_old, df_new], ignore_index=True)
    else:
        df = df_new
    df.to_csv(IC_FILE, index=False)


def update_weights(factor_config: dict, n_days: int = 20,
                   min_samples: int = 5, ic_scale: float = 10.0) -> bool:
    """用最近 n_days 的平均 IC 调整权重，写入 weights_override.json。

    规则：
      - IC 为正 → 加大权重；IC 为负 → 减小权重
      - IC 显著为负（<-0.03）→ 反转 direction（因子方向反了）
    返回是否发生调整。
    """
    if not os.path.exists(IC_FILE):
        return False
    ic_df = pd.read_csv(IC_FILE)
    if len(ic_df) < min_samples:
        return False

    recent = ic_df.tail(n_days)
    mean_ic = recent.mean(numeric_only=True)

    override = {}
    for name, cfg in factor_config.items():
        ic = mean_ic.get(name, 0.0)
        if pd.isna(ic):
            continue
        direction = cfg["direction"]
        if ic < -0.03:
            direction = -direction  # 因子方向反了
        new_weight = max(0.01, min(0.5, cfg["weight"] * (1.0 + ic * ic_scale)))
        override[name] = {
            "weight": round(new_weight, 4),
            "direction": direction,
        }

    if override:
        with open(OVERRIDE_FILE, "w", encoding="utf-8") as f:
            json.dump(override, f, ensure_ascii=False, indent=2)
    return bool(override)


def update_factor_pool(factor_config: dict, candidate_config: dict, n_days: int = 10,
                       min_samples: int = 5, activate_ic: float = 0.03,
                       deactivate_ic: float = 0.01) -> dict:
    """候选因子自动收纳 / 正式因子自动退役。

    基于 ic_history.csv 最近 n_days 的平均 IC：
    - 候选因子：|mean_ic| >= activate_ic → 收纳（direction 按 IC 符号，初始权重 0.05）
    - 正式因子：|mean_ic| < deactivate_ic → 退役（weight 归 0）
    结果写入 weights_override.json。
    """
    result = {"activated": [], "deactivated": []}
    if not os.path.exists(IC_FILE):
        return result
    ic_df = pd.read_csv(IC_FILE)
    if len(ic_df) < min_samples:
        return result
    mean_ic = ic_df.tail(n_days).mean(numeric_only=True)

    override = {}
    if os.path.exists(OVERRIDE_FILE):
        with open(OVERRIDE_FILE, encoding="utf-8") as f:
            override = json.load(f)

    # 候选因子收纳
    for name, cfg in candidate_config.items():
        ic = mean_ic.get(name, 0.0)
        if pd.isna(ic) or name in override:
            continue
        if abs(ic) >= activate_ic:
            direction = 1 if ic > 0 else -1
            override[name] = {"weight": 0.05, "direction": direction}
            result["activated"].append(name)

    # 正式因子退役
    for name in factor_config.keys():
        ic = mean_ic.get(name, 0.0)
        if pd.isna(ic):
            continue
        if abs(ic) < deactivate_ic:
            override[name] = {"weight": 0.0,
                              "direction": factor_config[name].get("direction", 1)}
            result["deactivated"].append(name)

    if result["activated"] or result["deactivated"]:
        with open(OVERRIDE_FILE, "w", encoding="utf-8") as f:
            json.dump(override, f, ensure_ascii=False, indent=2)

    return result


def load_override(factor_config: dict) -> dict:
    """应用 weights_override.json：覆盖权重/方向，收纳新增因子，退役移除因子。"""
    if not os.path.exists(OVERRIDE_FILE):
        return factor_config
    with open(OVERRIDE_FILE, encoding="utf-8") as f:
        override = json.load(f)
    for name, adj in override.items():
        w = adj.get("weight", 0)
        if w > 0:
            if name in factor_config:
                factor_config[name]["weight"] = w
                factor_config[name]["direction"] = adj.get("direction", factor_config[name].get("direction", 1))
            else:
                # 收纳的候选因子：新增进正式因子
                factor_config[name] = {"weight": w, "direction": adj.get("direction", 1)}
        else:
            # 退役：移除
            factor_config.pop(name, None)
    return factor_config


def format_factor_health(factor_config: dict, candidate_config: dict, n_days: int = 2) -> str:
    """生成因子健康度文本（direction×IC 有效值，最近 n_days 天变化）。

    有效值 = direction × IC：正=方向对，负=方向反。
    返回对齐的代码块文本；数据不足返回空串。
    """
    if not os.path.exists(IC_FILE):
        return ""
    ic_df = pd.read_csv(IC_FILE)
    if len(ic_df) < 2:
        return ""
    recent = ic_df.tail(n_days)

    def dw(s):
        return sum(2 if ord(c) > 127 else 1 for c in str(s))

    def padl(s, w):
        s = str(s)
        return s + " " * (w - dw(s))

    rows = []
    for f in list(factor_config) + list(candidate_config):
        d = factor_config.get(f, {}).get("direction", candidate_config.get(f, {}).get("direction", 1))
        vals = recent[f].tolist()
        if len(vals) < 2 or any(pd.isna(v) for v in vals):
            continue
        e1, e2 = d * vals[0], d * vals[1]
        if e1 > 0 and e2 > 0:
            j = "✅"
        elif e1 < 0 and e2 < 0:
            j = "❌"
        else:
            j = "⚠️"
        tag = "正式" if f in factor_config else "候选"
        rows.append([tag, f, f"{d:+d}", f"{e1:+.3f}→{e2:+.3f}", j])

    if not rows:
        return ""
    header = ["类别", "因子", "方向", "有效值(前2日)", "判定"]
    widths = [max([dw(h)] + [dw(r[i]) for r in rows]) + 2 for i, h in enumerate(header)]

    def line(c):
        return "  ".join(padl(c[i], widths[i]) for i in range(len(c)))

    lines = [line(header), "  ".join("-" * w for w in widths)]
    lines += [line(r) for r in rows]
    return "```\n" + "\n".join(lines) + "\n```"
