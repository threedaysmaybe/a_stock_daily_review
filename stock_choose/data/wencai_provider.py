"""问财（pywencai）数据源。

通过同花顺问财智能选股接口，一次查询获取全市场股票的因子数据。

依赖：pywencai（pip install pywencai）

注意：pywencai 0.13.x 的 headers 缺少 Referer，会被问财 Nginx 拦截(403)，
本模块在导入时自动 patch 补上 Referer/Origin；同时抑制 node 生成 token 的噪音。
"""
import os
import subprocess
import time

import pandas as pd

_pywencai_ready = False


def _ensure_pywencai():
    """延迟导入 pywencai 并修复 403 问题 + 抑制 node 噪音（幂等）。

    只在真正调用问财接口时才加载 pywencai，避免拖慢页面首次打开。
    """
    global _pywencai_ready
    if _pywencai_ready:
        return
    import pywencai
    import pywencai.headers as _hdrs
    import pywencai.wencai as _wencai

    # 1) 抑制 get_token 里 node 的 stderr 噪音
    def _quiet_get_token():
        js_path = os.path.join(os.path.dirname(_hdrs.__file__), "hexin-v.bundle.js")
        kwargs = {"stdout": subprocess.PIPE, "stderr": subprocess.DEVNULL}
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        result = subprocess.run(["node", js_path], **kwargs)
        return result.stdout.decode().strip()

    _hdrs.get_token = _quiet_get_token

    # 2) 补 Referer / Origin / Accept
    _orig_headers = _wencai.headers

    def _patched_headers(cookie=None, user_agent=None):
        h = _orig_headers(cookie, user_agent)
        h.setdefault("Referer", "https://www.iwencai.com/")
        h.setdefault("Origin", "https://www.iwencai.com")
        h.setdefault("Accept", "application/json, text/plain, */*")
        return h

    _wencai.headers = _patched_headers
    _pywencai_ready = True


# 因子名 -> 问财返回列名的匹配关键词（按优先级，前面的更精确）
FACTOR_COLUMN_KEYWORDS = {
    "pe_ttm": ["市盈率(pe", "市盈率"],
    "pb": ["市净率(pb", "市净率"],
    "peg": ["历史peg", "peg"],
    "dividend_yield": ["股息率(近12个月", "股息率"],
    "roe": ["净资产收益率roe(加权", "净资产收益率"],
    "gross_margin": ["销售毛利率"],
    "net_margin": ["销售净利率"],
    "debt_ratio": ["资产负债率"],
    "net_profit_growth": ["净利润(同比增长率"],
    "revenue_growth": ["营业收入(同比增长率"],
    "momentum_20d": ["区间涨跌幅"],
    "turnover": ["换手率"],
    "volume_ratio": ["量比"],
    "main_net_inflow": ["主力资金流向"],
    "northbound_holding": ["陆股通持股占流通a股比", "陆股通持股"],
    "float_market_cap": ["a股市值(不含限售股", "流通市值"],
    # 候选因子池（自动收纳/退役）
    "amplitude": ["振幅["],                 # 当日振幅
    "total_market_cap": ["总市值"],          # 总市值
    "main_inflow_5d": ["区间主力资金流向"],    # 5日主力资金流向
    "turnover_5d": ["区间换手率"],            # 5日换手率
}

BASE_COLUMN_KEYWORDS = {
    "name": ["股票简称"],
    "market_type": ["股票市场类型"],
    "pct_change": ["最新涨跌幅"],
}

# 派生因子所需原始字段（_build_query 固定附带）
AUX_COLUMN_KEYWORDS = {
    "concept": ["所属概念"],       # 供 sector_heat（概念情绪）
    "ma5": ["5日均线"],           # 供 ma_bias（乖离率）
    "close_price": ["收盘价", "最新价"],  # 供 ma_bias（收盘后最新价=收盘价）
}


def _find_column(columns, keywords):
    """按关键词优先级返回第一个命中的列名。"""
    for kw in keywords:
        for col in columns:
            if kw in col:
                return col
    return None


def _to_numeric(s: pd.Series) -> pd.Series:
    """去掉 % / 逗号后转数值，失败置 NaN。"""
    return pd.to_numeric(
        s.astype(str).str.replace("%", "").str.replace(",", ""),
        errors="coerce",
    )


def _is_st(market_type) -> bool:
    """从「股票市场类型」列判断是否 ST/风险警示。"""
    mt = str(market_type)
    first = mt.split(";")[0]
    return ("ST" in first) or ("风险警示板" in mt)


class WencaiProvider:
    """问财数据源，对外只提供 fetch()：一次查询返回全市场标准列 DataFrame。"""

    def __init__(self, factor_config: dict, retry: int = 3):
        self.factor_config = factor_config
        self.retry = retry

    def _build_query(self, factor_keys: list) -> str:
        keywords = []
        for k in factor_keys:
            q = self.factor_config[k].get("query")
            if q:  # 派生因子（如 ma_bias/sector_heat）无 query，跳过
                keywords.append(q)
        # 净资产收益率用于 roe_min 门槛（不参与排序）
        keywords.append("净资产收益率")
        # 派生因子原始字段（乖离率 / 概念情绪）
        keywords.append("5日均线")
        keywords.append("所属概念")
        return "沪深A股，" + "，".join(keywords)

    def _query_with_retry(self, query: str):
        last_err = None
        for i in range(self.retry):
            try:
                import pywencai
                _ensure_pywencai()
                return pywencai.get(query=query, query_type="stock", loop=True)
            except Exception as e:  # noqa: BLE001
                last_err = e
                print(f"[问财] 第 {i + 1} 次查询失败：{e}")
                time.sleep(2)
        raise RuntimeError(f"问财查询失败：{last_err}")

    def fetch(self) -> pd.DataFrame:
        """分批查询并合并（问财免费用户单次查询字段数有上限）。

        返回 DataFrame：index=股票代码，列含 name/is_st 及各因子。
        """
        factor_names = list(self.factor_config.keys())
        # 问财免费用户单次约 8 个字段以内，超出报 -9135
        # _build_query 固定附带 3 个字段（净资产收益率/5日均线/所属概念），故每批因子数设 5
        batch_size = 5
        batches = [
            factor_names[i:i + batch_size]
            for i in range(0, len(factor_names), batch_size)
        ]

        merged = None
        for i, batch in enumerate(batches):
            print(f"[问财] 查询第 {i + 1}/{len(batches)} 批因子 ...")
            raw = self._query_with_retry(self._build_query(batch))
            norm = self._normalize(raw)
            # keep 只保留有 query 的因子；派生因子（ma_bias/sector_heat）走 base_cols
            keep = [c for c in batch if c in norm.columns and self.factor_config[c].get("query")]
            if merged is None:
                base_cols = [c for c in ["name", "market_type", "is_st", "pct_change",
                                         "concept", "ma_bias"] if c in norm.columns]
                merged = norm[keep + base_cols]
            else:
                merged = merged.join(norm[keep], how="outer")
        return merged

    def _normalize(self, raw: pd.DataFrame) -> pd.DataFrame:
        if raw is None or raw.empty:
            raise ValueError("问财返回空数据")

        code_col = _find_column(raw.columns, ["股票代码"])
        if code_col is None:
            raise ValueError("问财返回中未找到「股票代码」列")

        # 关键：先把 index 对齐到股票代码，避免按默认整数 index 赋值错位
        raw = raw.set_index(code_col)
        raw.index = raw.index.astype(str)
        raw.index.name = "code"

        result = pd.DataFrame(index=raw.index)

        for std, kws in BASE_COLUMN_KEYWORDS.items():
            col = _find_column(raw.columns, kws)
            if col is not None:
                result[std] = raw[col]

        for std, kws in FACTOR_COLUMN_KEYWORDS.items():
            col = _find_column(raw.columns, kws)
            if col is not None:
                result[std] = _to_numeric(raw[col])

        # 派生因子原始字段
        for std, kws in AUX_COLUMN_KEYWORDS.items():
            col = _find_column(raw.columns, kws)
            if col is not None:
                if std == "concept":
                    result[std] = raw[col].astype(str)
                else:
                    result[std] = _to_numeric(raw[col])

        # 乖离率 = 收盘价 / 5日均线 - 1
        if "close_price" in result.columns and "ma5" in result.columns:
            result["ma_bias"] = result["close_price"] / result["ma5"] - 1

        if "market_type" in result.columns:
            result["is_st"] = result["market_type"].apply(_is_st)
        if "float_market_cap" in result.columns:
            # 问财返回单位是元，转成亿元便于配置
            result["float_market_cap"] = _to_numeric(result["float_market_cap"]) / 1e8
        if "pct_change" in result.columns:
            result["pct_change"] = _to_numeric(result["pct_change"])

        return result
