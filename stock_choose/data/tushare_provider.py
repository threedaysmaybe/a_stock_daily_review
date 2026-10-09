"""Tushare 官方 API 全市场截面数据（2000 积分）。

数据分三档更新：
1. 每日更新：换手/量比/PE/PB/股息率/市值/涨跌幅/振幅/主力资金（daily_basic+daily+moneyflow）
2. 每日更新（历史累计）：动量/乖离率/5日资金/5日换手（查最近 21 天）
3. 每周更新（季度财务）：ROE/净利增长/营收增长/负债率/毛利率（fina_indicator 个股循环，缓存）
"""
import os
import time
import tushare as ts
import numpy as np
import pandas as pd

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TushareProvider:
    """Tushare 全市场截面数据。"""

    def __init__(self, factor_config: dict, token: str):
        self.factor_config = factor_config
        self.token = token
        self.pro = ts.pro_api(token)
        self._names = None  # 代码 -> 名称 缓存

    def _retry(self, fn, retry=3, sleep=2):
        for i in range(retry):
            try:
                return fn()
            except Exception as e:  # noqa: BLE001
                if i == retry - 1:
                    raise
                time.sleep(sleep)

    def fetch(self, trade_date: str = None, update_finance: bool = False) -> pd.DataFrame:
        """拉全市场当日截面。trade_date 形如 YYYY-MM-DD 或 YYYYMMDD。"""
        td = (trade_date or "").replace("-", "")
        # 1. 每日指标：换手率/量比/PE/PB/股息率/市值
        db = self._retry(lambda: self.pro.daily_basic(
            trade_date=td,
            fields="ts_code,close,turnover_rate,volume_ratio,pe_ttm,pb,dv_ratio,total_mv,circ_mv",
        ))
        # 2. 日线：涨跌幅 + 振幅（high/low/pre_close）
        d = self._retry(lambda: self.pro.daily(
            trade_date=td, fields="ts_code,open,high,low,pre_close,pct_chg"
        ))
        if db is None or db.empty or d is None or d.empty:
            return pd.DataFrame()
        # 3. 资金流：主力净流入（大单+特大单 净额）
        mf = self._fetch_moneyflow(td)
        merged = db.merge(d, on="ts_code", how="inner").merge(mf, on="ts_code", how="left")
        # 4. 历史累计因子：动量/乖离率/5日资金/5日换手
        hist = self._fetch_history(td)
        merged = merged.merge(hist, on="ts_code", how="left")
        # 5. 财务因子（季度，缓存/每周更新）
        fin = self._fetch_finance(force=update_finance)
        if fin is not None and len(fin):
            merged = merged.merge(fin, on="ts_code", how="left")
        # 6. 名称映射
        names = self._get_names()
        merged = merged.merge(names, on="ts_code", how="left")
        return self._normalize(merged)

    def _fetch_moneyflow(self, td: str) -> pd.DataFrame:
        try:
            mf = self.pro.moneyflow(
                trade_date=td,
                fields="ts_code,buy_lg_amount,buy_elg_amount,sell_lg_amount,sell_elg_amount",
            )
            mf["main_net_inflow"] = (mf["buy_lg_amount"] + mf["buy_elg_amount"]) - (mf["sell_lg_amount"] + mf["sell_elg_amount"])
            return mf[["ts_code", "main_net_inflow"]]
        except Exception:  # noqa: BLE001
            return pd.DataFrame(columns=["ts_code", "main_net_inflow"])

    def _recent_trade_dates(self, td: str, n: int) -> list:
        cal = self.pro.trade_cal(end_date=td, is_open="1")
        return sorted(cal["cal_date"].tolist())[-n:]

    def _fetch_history(self, td: str) -> pd.DataFrame:
        """动量(20日)、乖离率(MA5)、5日换手、5日资金。

        对单日接口返回空表做容错：跳过无数据的日期，避免交易日历与行情数据
        不一致（如节假日日历未更新）时整个选股崩溃。
        """
        empty_hist = pd.DataFrame(columns=["ts_code", "momentum_20d", "ma_bias", "turnover_5d", "main_inflow_5d"])
        dates = self._recent_trade_dates(td, 21)

        # 动量 + 乖离率（close）
        closes = {}
        for hd in dates:
            try:
                c = self.pro.daily(trade_date=hd, fields="ts_code,close")
                if c is None or c.empty or "ts_code" not in c.columns or "close" not in c.columns:
                    continue
                closes[hd] = c.set_index("ts_code")["close"]
            except Exception:  # noqa: BLE001
                continue
        if not closes:
            return empty_hist
        close_df = pd.DataFrame(closes)
        result = pd.DataFrame(index=close_df.index)
        result["momentum_20d"] = close_df.iloc[:, -1] / close_df.iloc[:, 0] - 1
        result["ma_bias"] = close_df.iloc[:, -1] / close_df.iloc[:, -5:].mean(axis=1) - 1

        # 5日换手
        turns = {}
        for hd in dates[-5:]:
            try:
                t = self.pro.daily_basic(trade_date=hd, fields="ts_code,turnover_rate")
                if t is None or t.empty or "ts_code" not in t.columns or "turnover_rate" not in t.columns:
                    continue
                turns[hd] = t.set_index("ts_code")["turnover_rate"]
            except Exception:  # noqa: BLE001
                continue
        result["turnover_5d"] = pd.DataFrame(turns).mean(axis=1) if turns else np.nan

        # 5日资金
        mfs = {}
        for hd in dates[-5:]:
            try:
                m = self.pro.moneyflow(
                    trade_date=hd,
                    fields="ts_code,buy_lg_amount,buy_elg_amount,sell_lg_amount,sell_elg_amount",
                )
                need = ["ts_code", "buy_lg_amount", "buy_elg_amount", "sell_lg_amount", "sell_elg_amount"]
                if m is None or m.empty or any(col not in m.columns for col in need):
                    continue
                m["net"] = (m["buy_lg_amount"] + m["buy_elg_amount"]) - (m["sell_lg_amount"] + m["sell_elg_amount"])
                mfs[hd] = m.set_index("ts_code")["net"]
            except Exception:  # noqa: BLE001
                continue
        result["main_inflow_5d"] = pd.DataFrame(mfs).sum(axis=1) if mfs else np.nan

        result.index.name = "ts_code"
        return result.reset_index()

    def _fetch_finance(self, force: bool = False) -> pd.DataFrame:
        """财务因子（季度数据）：缓存 output/finance_cache.csv，每周一 force 更新。"""
        cache_file = os.path.join(_BASE_DIR, "output", "finance_cache.csv")
        if os.path.exists(cache_file):
            return pd.read_csv(cache_file)
        if not force:
            # 缓存不存在且非更新日：返回空，等周一 force 跑一次
            return pd.DataFrame()
        codes = self.pro.stock_basic(exchange="", list_status="L", fields="ts_code")["ts_code"].tolist()
        rows = []
        for i, c in enumerate(codes):
            try:
                fi = self.pro.fina_indicator(
                    ts_code=c,
                    fields="ts_code,roe,netprofit_yoy,or_yoy,grossprofit_margin,debt_to_assets",
                )
                if len(fi):
                    rows.append(fi.iloc[0])
            except Exception:  # noqa: BLE001
                pass
            if (i + 1) % 500 == 0:
                print(f"    财务进度 {i + 1}/{len(codes)}")
                time.sleep(1)  # 避免频率超限
        if rows:
            df = pd.DataFrame(rows)
            df.to_csv(cache_file, index=False)
            return df
        return pd.DataFrame()

    def _get_names(self) -> pd.DataFrame:
        if self._names is None:
            self._names = self.pro.stock_basic(exchange="", list_status="L", fields="ts_code,name")
        return self._names

    def _normalize(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.rename(columns={
            "ts_code": "code",
            "turnover_rate": "turnover",
            "volume_ratio": "volume_ratio",
            "pe_ttm": "pe_ttm",
            "pb": "pb",
            "dv_ratio": "dividend_yield",
            "total_mv": "total_market_cap",
            "circ_mv": "float_market_cap",
            "pct_chg": "pct_change",
        })
        # 振幅 = (最高-最低)/昨收
        df["amplitude"] = (df["high"] - df["low"]) / df["pre_close"]
        # is_st：名称含 ST / 退（退市整理，供门槛过滤用）
        df["is_st"] = df["name"].astype(str).str.contains("ST|退", na=False)
        # 市值：万元 -> 亿元
        df["total_market_cap"] = df["total_market_cap"] / 10000
        df["float_market_cap"] = df["float_market_cap"] / 10000
        # 过滤北交所（.BJ，akshare 拉不到其历史 K 线）
        df = df[~df["code"].str.endswith(".BJ")]
        df = df.set_index("code")
        df.index.name = "code"
        return df
