"""板块/概念情绪因子。

sector_heat：个股所属的最热概念的当日平均涨幅（方向 +1，追热点）。
数据源：问财「所属概念」+「涨跌幅」（已由 provider 拉取为 concept / pct_change 列）。
"""
import pandas as pd


def compute_sector_heat(df: pd.DataFrame) -> pd.Series:
    """概念情绪：个股所属的所有概念里，当日涨幅最高的那个概念的涨幅。

    输入 df 需含「concept」（所属概念，分号分隔字符串）和「pct_change」列。
    返回与 df 同 index 的 Series（概念情绪值）。
    """
    if "concept" not in df.columns or "pct_change" not in df.columns:
        return pd.Series(index=df.index, dtype=float)

    codes, concepts, pcs = [], [], []
    for code in df.index:
        c = df.at[code, "concept"]
        p = df.at[code, "pct_change"]
        if pd.isna(c) or str(c) == "nan" or pd.isna(p):
            continue
        for cc in str(c).split(";"):
            cc = cc.strip()
            if cc:
                codes.append(code)
                concepts.append(cc)
                pcs.append(p)

    if not codes:
        return pd.Series(index=df.index, dtype=float)

    exp = pd.DataFrame({"code": codes, "concept": concepts, "pc": pcs})
    sector_ret = exp.groupby("concept")["pc"].mean()
    exp["heat"] = exp["concept"].map(sector_ret)
    result = exp.groupby("code")["heat"].max()  # 最热概念
    return result.reindex(df.index)
