"""东财全市场截面数据 provider（低频，少次请求）。

东财 clist 接口单次能拿全市场实时行情，字段覆盖：
最新价、涨跌幅、换手率、量比、市盈率、市净率、总市值、流通市值等。

⚠️ 东财有频率限制，务必低频调用（每天只跑 1 次，不要频繁重试/测试）。
"""
import time
import requests
import pandas as pd

_URL = "https://82.push2.eastmoney.com/api/qt/clist/get"
_FS = "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23"  # 沪深A股

# 东财字段 -> 标准列名
_FIELDS = {
    "f2": "close", "f3": "pct_change", "f5": "volume", "f6": "amount",
    "f8": "turnover", "f9": "pe_ttm", "f10": "volume_ratio",
    "f12": "code", "f14": "name", "f15": "high", "f16": "low",
    "f17": "open", "f18": "pre_close", "f20": "total_market_cap",
    "f21": "float_market_cap", "f23": "pb",
}


class EastmoneyProvider:
    """东财全市场截面数据（低频）。"""

    def __init__(self, factor_config: dict):
        self.factor_config = factor_config

    def fetch(self, page_size: int = 100) -> pd.DataFrame:
        """分页拉全市场（尽量少的请求，页间小幅 sleep 避免触发风控）。"""
        all_rows = []
        pn = 1
        while pn <= 60:  # 安全上限
            page = self._fetch_page(pn, page_size)
            if page is None or len(page) == 0:
                break
            all_rows.append(page)
            if len(page) < page_size:
                break
            pn += 1
            time.sleep(0.5)  # 页间间隔，避免高频
        if not all_rows:
            raise RuntimeError("东财全市场行情拉取失败（可能触发限流，请稍后再试）")
        merged = pd.concat(all_rows, ignore_index=True)
        return self._normalize(merged)

    def _fetch_page(self, pn: int, pz: int) -> pd.DataFrame:
        params = {
            "pn": str(pn), "pz": str(pz), "po": "1", "np": "1",
            "fltt": "2", "invt": "2", "fid": "f3", "fs": _FS,
            "fields": ",".join(_FIELDS.keys()),
        }
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        r = requests.get(_URL, params=params, headers=headers, timeout=15)
        data = r.json().get("data")
        if not data or not data.get("diff"):
            return None
        return pd.DataFrame(data["diff"])

    def _normalize(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.rename(columns=_FIELDS)
        # 保留存在的列
        cols = [c for c in _FIELDS.values() if c in df.columns]
        df = df[cols].copy()
        # 代码补后缀（6=沪市，0/3=深市）
        def to_code(c):
            c = str(c)
            if c.startswith(("6", "9")):
                return c + ".SH"
            return c + ".SZ"
        df["code"] = df["code"].apply(to_code)
        # 数值列转 float
        for c in df.columns:
            if c not in ("code", "name"):
                df[c] = pd.to_numeric(df[c], errors="coerce")
        # 振幅 = (最高-最低)/昨收
        if {"high", "low", "pre_close"}.issubset(df.columns):
            df["amplitude"] = (df["high"] - df["low"]) / df["pre_close"]
        df = df.set_index("code")
        df.index.name = "code"
        return df
