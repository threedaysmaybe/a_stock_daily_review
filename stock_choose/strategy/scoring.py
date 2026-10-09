"""多因子加权打分"""
import pandas as pd

from stock_choose.factors.process import process_factor


def score_stocks(factor_df: pd.DataFrame, factor_config: dict,
                 clip_q: float = 0.01, method: str = "zscore",
                 min_coverage: float = 0.5) -> pd.DataFrame:
    """
    对每只股票做多因子加权打分。

    参数:
        factor_df:     DataFrame，index=股票代码，columns=因子名
        factor_config: dict，{因子名: {"weight": float, "direction": 1|-1}}
        clip_q:        去极值分位
        method:        zscore / rank
        min_coverage:  因子非空占比低于该值的股票剔除

    返回:
        DataFrame，含各因子标准化值、total_score、rank，按得分降序。
    """
    factor_names = [n for n in factor_config if n in factor_df.columns]
    if not factor_names:
        raise ValueError("factor_df 中没有任何已配置的因子列")

    # 剔除因子缺失率过高的股票
    coverage = factor_df[factor_names].notna().mean(axis=1)
    df = factor_df.loc[coverage >= min_coverage].copy()

    total_weight = sum(factor_config[n]["weight"] for n in factor_names)
    if total_weight <= 0:
        raise ValueError("因子权重之和必须大于 0")

    proc_df = pd.DataFrame(index=df.index)
    score = pd.Series(0.0, index=df.index)
    valid_weight = pd.Series(0.0, index=df.index)

    for name in factor_names:
        cfg = factor_config[name]
        p = process_factor(df[name], clip_q, method)
        proc_df[name] = p
        w = cfg["direction"] * cfg["weight"]
        valid = p.notna()
        # 缺失因子按 0 贡献；分母只统计实际参与打分的因子权重，
        # 因此数据不全的股票自然得分偏低。
        score = score + p.fillna(0.0) * w
        valid_weight = valid_weight + valid.astype(float) * abs(cfg["weight"])

    score = score / valid_weight.replace(0, float("nan"))
    result = proc_df.copy()
    result["total_score"] = score
    result["rank"] = score.rank(ascending=False, method="first").astype(int)
    return result.sort_values("total_score", ascending=False)
