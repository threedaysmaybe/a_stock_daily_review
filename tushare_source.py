"""Tushare 官方数据源 —— 替代同花顺/东财爬虫，稳定不封。

覆盖（2000 积分即可）：
- top_list      龙虎榜汇总（当日上榜股票）
- top_inst      龙虎榜席位明细（含 exalter 营业部名称，供游资筛选）
- moneyflow_hsgt 北向资金（沪深港通）

依赖：pip install tushare
"""
import time

import tushare as ts
import pandas as pd


class TushareSource:
    """Tushare 官方数据源。"""

    def __init__(self, token: str):
        self.token = token
        self.pro = ts.pro_api(token)

    def _retry(self, fn, retry=3, sleep=2):
        for i in range(retry):
            try:
                return fn()
            except Exception:  # noqa: BLE001
                if i == retry - 1:
                    raise
                time.sleep(sleep)

    def get_lhb_summary(self, trade_date: str) -> pd.DataFrame:
        """龙虎榜汇总（当日上榜股票）。trade_date: YYYYMMDD"""
        return self._retry(lambda: self.pro.top_list(trade_date=trade_date))

    def get_lhb_inst(self, trade_date: str) -> pd.DataFrame:
        """龙虎榜席位明细（含 exalter 营业部/席位名称，供游资筛选）。trade_date: YYYYMMDD"""
        return self._retry(lambda: self.pro.top_inst(trade_date=trade_date))

    def get_northbound(self, start_date: str, end_date: str) -> pd.DataFrame:
        """北向资金（沪深港通）。date: YYYYMMDD"""
        return self._retry(lambda: self.pro.moneyflow_hsgt(start_date=start_date, end_date=end_date))

    def filter_hot_money(self, inst_df: pd.DataFrame, seat_keywords: dict) -> pd.DataFrame:
        """从龙虎榜席位明细里筛出游资席位。

        seat_keywords: {游资名: [席位关键词...]}
        返回：命中游资的席位明细（含游资名、净买入额）。
        """
        if inst_df is None or inst_df.empty:
            return pd.DataFrame()
        rows = []
        for hot, keywords in seat_keywords.items():
            for kw in keywords:
                hit = inst_df[inst_df["exalter"].astype(str).str.contains(kw, na=False)]
                for _, r in hit.iterrows():
                    rows.append({
                        "游资": hot,
                        "席位": r.get("exalter", ""),
                        "代码": r.get("ts_code", ""),
                        "买入额": r.get("buy", 0),
                        "卖出额": r.get("sell", 0),
                        "净买入": r.get("net_buy", 0),
                        "日期": r.get("trade_date", ""),
                    })
        if not rows:
            return pd.DataFrame()
        return pd.DataFrame(rows).drop_duplicates().reset_index(drop=True)

    def get_moneyflow(self, trade_date: str) -> pd.DataFrame:
        """个股资金流（主力/超大单/大单净流入）。trade_date: YYYYMMDD"""
        return self._retry(lambda: self.pro.moneyflow(trade_date=trade_date))

    def get_daily_basic(self, trade_date: str) -> pd.DataFrame:
        """每日指标（换手率/量比/市盈率/市值）。trade_date: YYYYMMDD"""
        return self._retry(lambda: self.pro.daily_basic(
            trade_date=trade_date,
            fields="ts_code,turnover_rate,volume_ratio,pe_ttm,pb,total_mv,circ_mv",
        ))
