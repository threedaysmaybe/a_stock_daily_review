"""
每日A股复盘模型 - 数据获取模块
封装 akshare 调用，统一数据格式，含缓存和重试
"""

import time
import streamlit as st
import akshare as ak
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional
import os
import requests
import json
import re

import config as cfg
import data_manager as dm
from tushare_source import TushareSource

_tushare = None


def _get_tushare() -> TushareSource:
    """Tushare 数据源单例（龙虎榜/北向资金）。"""
    global _tushare
    if _tushare is None:
        _tushare = TushareSource(cfg.TUSHARE_TOKEN)
    return _tushare


_LAST_THS_REQUEST = 0.0
_THS_MIN_INTERVAL = 1.0  # 同花顺请求最小间隔（秒），防封


def _ths_request(url: str, headers: dict = None, timeout: int = 10, retries: int = 3):
    """同花顺网页请求（降频 + 失败重试，防封）。返回 response 或 None。"""
    global _LAST_THS_REQUEST
    elapsed = time.time() - _LAST_THS_REQUEST
    if elapsed < _THS_MIN_INTERVAL:
        time.sleep(_THS_MIN_INTERVAL - elapsed)
    for i in range(retries):
        try:
            resp = requests.get(url, headers=headers, timeout=timeout)
            _LAST_THS_REQUEST = time.time()
            resp.encoding = "gbk"
            if resp.status_code == 200:
                return resp
        except Exception:  # noqa: BLE001
            pass
        time.sleep(2 * (i + 1))  # 重试间隔递增
    return None

# ============================================================
# 通用工具
# ============================================================

def _fmt_code(raw: str) -> str:
    """统一6位代码格式：去 sz/sh/bj 前缀 + 去 .SZ/.SH 后缀。"""
    s = str(raw).strip().lower()
    s = s.replace("sz", "").replace("sh", "").replace("bj", "")
    s = s.split(".")[0]
    return s.zfill(6)

def _to_float(s) -> Optional[float]:
    """安全转浮点，支持亿/万单位"""
    if s is None:
        return None
    try:
        if isinstance(s, (int, float)):
            return float(s)
        s = str(s).strip()
        if s.endswith("亿"):
            return float(s.replace("亿", "").strip()) * 100000000
        elif s.endswith("万"):
            return float(s.replace("万", "").strip()) * 10000
        elif s.endswith("%"):
            return float(s.replace("%", "").strip())
        return float(s)
    except (ValueError, TypeError):
        return None


@st.cache_data(ttl=cfg.CACHE_TTL)
def _cached(func_name: str, *args, **kwargs):
    """通用缓存包装（streamlit cache_data 已自动处理，此处为标识）"""
    pass


# ============================================================
# 1. 大盘指数数据
# ============================================================

@st.cache_data(ttl=cfg.CACHE_TTL)
def get_index_kline(index_code: str, days: int = 120) -> pd.DataFrame:
    """获取指数日K线（Tushare index_daily 优先，稳定不封）。"""
    local = dm.load_local(f"index_{index_code}.csv")
    if local is not None and not local.empty and "date" in local.columns:
        return local  # 有快照就用，不判断过期
    if not cfg.ALLOW_REALTIME_API:
        return pd.DataFrame()  # 只读快照模式，无快照返回空
    try:
        src = _get_tushare()
        ts_map = {"000001": "000001.SH", "399001": "399001.SZ", "399006": "399006.SZ", "000688": "000688.SH"}
        ts_code = ts_map.get(index_code)
        if ts_code:
            end = datetime.now().strftime("%Y%m%d")
            start = (datetime.now() - timedelta(days=days * 2)).strftime("%Y%m%d")
            df = src.pro.index_daily(ts_code=ts_code, start_date=start, end_date=end)
            if df is not None and not df.empty:
                df = df.rename(columns={"trade_date": "date", "vol": "volume"})
                df["date"] = pd.to_datetime(df["date"])
                if "amount" in df.columns:
                    df["amount"] = df["amount"] / 1e5  # 千元 → 亿元
                df = df.sort_values("date").tail(days).reset_index(drop=True)
                return df
    except Exception:  # noqa: BLE001
        pass
    # 兜底：新浪
    try:
        prefix = "sh" if index_code.startswith("000") or index_code.startswith("60") else "sz"
        df = ak.stock_zh_index_daily(symbol=f"{prefix}{index_code}")
        df["date"] = pd.to_datetime(df["date"])
        return df.sort_values("date").tail(days).reset_index(drop=True)
    except Exception:  # noqa: BLE001
        return pd.DataFrame()


@st.cache_data(ttl=cfg.CACHE_TTL)
def get_index_realtime(index_code: str) -> dict:
    """获取指数实时行情"""
    try:
        kline = get_index_kline(index_code, days=2)
        if not kline.empty and len(kline) >= 1:
            latest = kline.iloc[-1]
            prev = kline.iloc[-2] if len(kline) >= 2 else latest
            pct = (latest["close"] - prev["close"]) / prev["close"] * 100 if prev["close"] != 0 else 0
            return {
                "name": "", "price": latest["close"],
                "change_pct": round(pct, 2),
                "change_amt": round(latest["close"] - prev["close"], 2),
                "volume": latest.get("volume", 0),
                "amount": latest.get("amount", 0),
            }
    except Exception:
        pass
    try:
        df = ak.stock_zh_index_spot_em()
        name_map = {
            "000001": "上证指数", "399001": "深证成指",
            "399006": "创业板指", "000688": "科创50"
        }
        name = name_map.get(index_code, "")
        row = df[df["名称"] == name]
        if row.empty:
            return {}
        r = row.iloc[0]
        return {
            "name": name,
            "price": _to_float(r.get("最新价", 0)),
            "change_pct": _to_float(r.get("涨跌幅", 0)),
            "change_amt": _to_float(r.get("涨跌额", 0)),
            "volume": _to_float(r.get("成交量", 0)),
            "amount": _to_float(r.get("成交额", 0)),
        }
    except Exception:
        try:
            kline = get_stock_kline(index_code, days=2)
            if not kline.empty and len(kline) >= 1:
                latest = kline.iloc[-1]
                return {
                    "code": index_code,
                    "name": "",
                    "price": latest["close"],
                    "change_pct": 0,
                    "change_amt": 0,
                    "volume": latest.get("volume", 0),
                    "amount": latest.get("amount", 0),
                    "turnover": 0,
                    "high": latest["high"],
                    "low": latest["low"],
                    "open": latest["open"],
                }
        except Exception:
            pass
        return {}


@st.cache_data(ttl=cfg.CACHE_TTL)
def get_all_indices() -> dict:
    """获取所有指数实时行情"""
    result = {}
    for name, code in cfg.INDICES.items():
        result[name] = get_index_realtime(code)
    return result


# ============================================================
# 2. 板块数据
# ============================================================

def get_sector_spot() -> pd.DataFrame:
    """获取板块实时行情（30秒简单缓存，避免同一次页面交互重复读盘）"""
    # 模块级简单缓存：比 @st.cache_data 更可控
    now = time.time()
    if get_sector_spot._cache is not None and now - get_sector_spot._time < 30:
        return get_sector_spot._cache.copy()
    
    local = dm.load_local("sectors.csv")
    result = None
    if local is not None and not local.empty:
        # 重命名中文列名为英文
        if "板块" in local.columns:
            local = local.rename(columns={"板块": "sector_name"})
        if "涨跌幅" in local.columns:
            local = local.rename(columns={"涨跌幅": "change_pct"})
        # 确保 change_pct 是数值
        if "change_pct" in local.columns:
            local["change_pct"] = pd.to_numeric(local["change_pct"], errors="coerce").fillna(0)
        # 补全缺失的列
        if "up_count" not in local.columns:
            local["up_count"] = 0
        if "down_count" not in local.columns:
            local["down_count"] = 0
        if "top_stock" not in local.columns:
            local["top_stock"] = ""
        # 按涨跌幅从高到低排序
        result = local.sort_values("change_pct", ascending=False).reset_index(drop=True)
    
    if result is None:
        if not cfg.ALLOW_REALTIME_API:
            return pd.DataFrame()  # 只读快照模式，无快照返回空
        try:
            df = ak.stock_board_industry_summary_ths()
            if df is not None and not df.empty:
                df = df.rename(columns={
                    "板块": "sector_name",
                    "涨跌幅": "change_pct",
                    "上涨家数": "up_count",
                    "下跌家数": "down_count",
                    "领涨股": "top_stock",
                })
                df["change_pct"] = pd.to_numeric(df["change_pct"], errors="coerce").fillna(0)
                for col in ["up_count", "down_count", "top_stock"]:
                    if col not in df.columns:
                        df[col] = 0 if col != "top_stock" else ""
                result = df[["sector_name", "change_pct", "up_count", "down_count", "top_stock"]]
                result = result.sort_values("change_pct", ascending=False).reset_index(drop=True)
                
                today = datetime.now().strftime("%Y%m%d")
                data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", today)
                os.makedirs(data_dir, exist_ok=True)
                result.to_csv(os.path.join(data_dir, "sectors.csv"), index=False, encoding="utf-8-sig")
        except Exception as e:
            print(f"stock_board_industry_summary_ths 失败: {e}")
    
    if result is None:
        result = pd.DataFrame()
    
    get_sector_spot._cache = result.copy()
    get_sector_spot._time = now
    return result

# 初始化模块级缓存
get_sector_spot._cache = None
get_sector_spot._time = 0



def get_concept_spot() -> pd.DataFrame:
    """获取概念板块实时行情（30秒简单缓存）"""
    now = time.time()
    if get_concept_spot._cache is not None and now - get_concept_spot._time < 30:
        return get_concept_spot._cache.copy()
    
    local = dm.load_local("concept_sectors.csv")
    result = None
    if local is not None and not local.empty:
        # 补全缺失列
        if "up_count" not in local.columns:
            local["up_count"] = 0
        if "down_count" not in local.columns:
            local["down_count"] = 0
        if "top_stock" not in local.columns:
            local["top_stock"] = ""
        result = local
    
    if result is None:
        if not cfg.ALLOW_REALTIME_API:
            return pd.DataFrame()  # 只读快照模式，无快照返回空
        try:
            url = "https://q.10jqka.com.cn/gn/"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": "https://q.10jqka.com.cn/",
            }

            response = _ths_request(url, headers=headers)
            if response is not None:
                html = response.text
                pattern = r'<input type="hidden" id="gnSection" value=\'([^\']+)\'>'
                match = re.search(pattern, html)
                
                if match:
                    json_str = match.group(1)
                    json_str = json_str.replace('\\"', '"').replace('\\/', '/')
                    data = json.loads(json_str)
                    
                    concepts = []
                    for key, value in data.items():
                        platename = value.get("platename", "")
                        change_pct = value.get("199112", 0)
                        if platename:
                            concepts.append({
                                "sector_name": platename,
                                "change_pct": float(change_pct) if change_pct else 0,
                                "up_count": 0,
                                "down_count": 0,
                                "top_stock": ""
                            })
                    
                    if concepts:
                        result = pd.DataFrame(concepts)
                        result = result.sort_values("change_pct", ascending=False).reset_index(drop=True)
                        
                        today = datetime.now().strftime("%Y%m%d")
                        data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", today)
                        os.makedirs(data_dir, exist_ok=True)
                        result.to_csv(os.path.join(data_dir, "concept_sectors.csv"), index=False, encoding="utf-8-sig")
        except Exception as e:
            print(f"概念板块解析失败: {e}")
    
    if result is None:
        result = pd.DataFrame()
    
    get_concept_spot._cache = result.copy()
    get_concept_spot._time = now
    return result

# 初始化模块级缓存
get_concept_spot._cache = None
get_concept_spot._time = 0


@st.cache_data(ttl=cfg.CACHE_TTL)
def get_sector_fund_flow_rank() -> pd.DataFrame:
    """获取板块资金流向（从同花顺 gnSection 解析 zjjlr）"""
    try:
        import requests
        import json
        import re
        
        url = "https://q.10jqka.com.cn/gn/"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://q.10jqka.com.cn/",
        }

        response = _ths_request(url, headers=headers)
        if response is not None:
            html = response.text
            pattern = r'<input type="hidden" id="gnSection" value=\'([^\']+)\'>'
            match = re.search(pattern, html)
            
            if match:
                json_str = match.group(1)
                json_str = json_str.replace('\\"', '"').replace('\\/', '/')
                data = json.loads(json_str)
                
                df_list = []
                for key, value in data.items():
                    platename = value.get("platename", "")
                    change_pct = value.get("199112", 0)
                    zjjlr = value.get("zjjlr", 0)
                    if platename:
                        df_list.append({
                            "板块": platename,
                            "涨幅": change_pct,
                            "主力净流入": zjjlr,
                        })
                
                if df_list:
                    df = pd.DataFrame(df_list)
                    df = df.sort_values("涨幅", ascending=False).reset_index(drop=True)
                    return df
    except Exception as e:
        print(f"资金流向抓取失败: {e}")
    
    return pd.DataFrame()


@st.cache_data(ttl=cfg.CACHE_TTL)
def get_concept_fund_flow_rank() -> pd.DataFrame:
    """获取概念板块资金流向排名"""
    try:
        df = ak.stock_sector_fund_flow_rank()
        if df is not None and not df.empty:
            return df
    except Exception as e:
        print(f"概念资金流向失败: {e}")
    return pd.DataFrame()


@st.cache_data(ttl=cfg.CACHE_TTL)
def get_sector_fund_flow_history(days: int = 5) -> pd.DataFrame:
    """获取板块历史资金流向"""
    try:
        df = ak.stock_sector_fund_flow_rank()
        if df is not None and not df.empty:
            return df
    except Exception as e:
        print(f"板块历史资金流向失败: {e}")
    return pd.DataFrame()


@st.cache_data(ttl=cfg.CACHE_TTL)
def get_concept_fund_flow_history(days: int = 5) -> pd.DataFrame:
    """获取概念板块历史资金流向"""
    try:
        df = ak.stock_sector_fund_flow_rank()
        if df is not None and not df.empty:
            return df
    except Exception as e:
        print(f"概念历史资金流向失败: {e}")
    return pd.DataFrame()


# ============================================================
# 3. 个股数据
# ============================================================

@st.cache_data(ttl=cfg.CACHE_TTL)
def get_stock_kline(code: str, days: int = 120) -> pd.DataFrame:
    """获取个股日K线"""
    code = _fmt_code(code)
    local = dm.load_local(f"stock_{code}.csv")
    if local is not None and not local.empty and "date" in local.columns:
        return local  # 有快照就用，不判断过期（数据更新靠「更新数据」按钮）
    if not cfg.ALLOW_REALTIME_API:
        return pd.DataFrame()  # 只读快照模式，无快照返回空
    try:
        prefix = "sh" if code.startswith("6") else "sz"
        df = ak.stock_zh_a_daily(symbol=f"{prefix}{code}", adjust="qfq")
        if df is None or df.empty:
            return pd.DataFrame()

        df = df.rename(columns={
            "日期": "date", "开盘": "open", "最高": "high",
            "最低": "low", "收盘": "close", "成交量": "volume",
            "成交额": "amount", "振幅": "amplitude",
            "涨跌幅": "change_pct", "涨跌额": "change_amt", "换手率": "turnover"
        })
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date").tail(days).reset_index(drop=True)
        return df
    except Exception:
        # 兜底：Tushare daily（稳定）
        try:
            src = _get_tushare()
            ts_code = code + (".SH" if code.startswith("6") else ".SZ")
            end = datetime.now().strftime("%Y%m%d")
            start = (datetime.now() - timedelta(days=days * 2)).strftime("%Y%m%d")
            df = src.pro.daily(ts_code=ts_code, start_date=start, end_date=end)
            if df is not None and not df.empty:
                df = df.rename(columns={"trade_date": "date", "vol": "volume", "pct_chg": "change_pct"})
                df["date"] = pd.to_datetime(df["date"])
                df = df.sort_values("date").tail(days).reset_index(drop=True)
                return df
        except Exception:  # noqa: BLE001
            pass
        return pd.DataFrame()


@st.cache_data(ttl=cfg.CACHE_TTL)
def get_stock_realtime(code: str) -> dict:
    """获取个股实时行情（优先新浪源）"""
    code = _fmt_code(code)
    try:
        df = ak.stock_zh_a_spot()
        if df is not None and not df.empty:
            if df['代码'].iloc[0].startswith('sh') or df['代码'].iloc[0].startswith('sz'):
                mask = df['代码'].str[2:] == code
            else:
                mask = df['代码'] == code
            row = df[mask]
            if not row.empty:
                r = row.iloc[0]
                return {
                    "code": code, "name": r.get("名称", ""),
                    "price": _to_float(r.get("最新价", 0)),
                    "change_pct": _to_float(r.get("涨跌幅", 0)),
                    "change_amt": _to_float(r.get("涨跌额", 0)),
                    "volume": _to_float(r.get("成交量", 0)),
                    "amount": _to_float(r.get("成交额", 0)),
                    "turnover": _to_float(r.get("换手率", 0)),
                    "high": _to_float(r.get("最高", 0)),
                    "low": _to_float(r.get("最低", 0)),
                    "open": _to_float(r.get("今开", 0)),
                    "pe": _to_float(r.get("市盈率-动态", 0)),
                    "pb": _to_float(r.get("市净率", 0)),
                    "total_mv": _to_float(r.get("总市值", 0)),
                    "circ_mv": _to_float(r.get("流通市值", 0)),
                    "time": str(r.get("时间戳", "")),
                }
    except Exception:
        pass
    try:
        df = ak.stock_zh_a_spot_em()
        if df is not None and not df.empty:
            row = df[df["代码"] == code]
            if not row.empty:
                r = row.iloc[0]
                return {
                    "code": code, "name": r.get("名称", ""),
                    "price": _to_float(r.get("最新价", 0)),
                    "change_pct": _to_float(r.get("涨跌幅", 0)),
                    "change_amt": _to_float(r.get("涨跌额", 0)),
                    "volume": _to_float(r.get("成交量", 0)),
                    "amount": _to_float(r.get("成交额", 0)),
                    "turnover": _to_float(r.get("换手率", 0)),
                    "high": _to_float(r.get("最高", 0)),
                    "low": _to_float(r.get("最低", 0)),
                    "open": _to_float(r.get("今开", 0)),
                    "pe": _to_float(r.get("市盈率-动态", 0)),
                    "pb": _to_float(r.get("市净率", 0)),
                    "total_mv": _to_float(r.get("总市值", 0)),
                    "circ_mv": _to_float(r.get("流通市值", 0)),
                    "time": "",
                }
    except Exception:
        pass
    try:
        kline = get_stock_kline(code, days=2)
        if not kline.empty and len(kline) >= 1:
            latest = kline.iloc[-1]
            return {
                "code": code, "name": "", "price": latest["close"],
                "change_pct": 0, "change_amt": 0,
                "volume": latest.get("volume", 0), "amount": latest.get("amount", 0),
                "turnover": 0, "high": latest["high"], "low": latest["low"],
                "open": latest["open"], "time": "",
            }
    except Exception:
        pass
    return {}


# ============================================================
# 4. 资金流向
# ============================================================

@st.cache_data(ttl=cfg.CACHE_TTL)
def get_market_fund_flow() -> pd.DataFrame:
    """获取全市场资金流向（东财优先，Tushare 兜底；本地缓存当天结果，重启不重跑）。"""
    # 本地缓存（当天）
    local = dm.load_local("market_fund_flow.csv")
    if local is not None and not local.empty:
        return local
    if not cfg.ALLOW_REALTIME_API:
        return pd.DataFrame()
    try:
        df = ak.stock_market_fund_flow()
        if df is not None and not df.empty:
            dm.save_local(df, "market_fund_flow.csv")
            return df
    except Exception:  # noqa: BLE001
        pass
    # 兜底：Tushare moneyflow 聚合最近 10 个交易日
    try:
        src = _get_tushare()
        cal = src.pro.trade_cal(exchange="SSE", is_open="1", end_date=datetime.now().strftime("%Y%m%d"))
        tds = sorted(cal["cal_date"].tolist())[-10:] if cal is not None and not cal.empty else []
        rows = []
        for td in tds:
            mf = src.pro.moneyflow(trade_date=td)
            if mf is None or mf.empty:
                continue
            main_net = (mf["buy_lg_amount"] + mf["buy_elg_amount"] - mf["sell_lg_amount"] - mf["sell_elg_amount"]).sum()
            elg_net = (mf["buy_elg_amount"] - mf["sell_elg_amount"]).sum()
            lg_net = (mf["buy_lg_amount"] - mf["sell_lg_amount"]).sum()
            md_net = (mf["buy_md_amount"] - mf["sell_md_amount"]).sum()
            sm_net = (mf["buy_sm_amount"] - mf["sell_sm_amount"]).sum()
            rows.append({
                "日期": td, "主力净流入-净额": main_net, "超大单净流入-净额": elg_net,
                "大单净流入-净额": lg_net, "中单净流入-净额": md_net, "小单净流入-净额": sm_net,
            })
        if rows:
            result = pd.DataFrame(rows)
            dm.save_local(result, "market_fund_flow.csv")
            return result
    except Exception:  # noqa: BLE001
        pass
    return pd.DataFrame()


@st.cache_data(ttl=cfg.CACHE_TTL)
def get_northbound(days: int = 10) -> pd.DataFrame:
    """北向资金（沪深港通，Tushare moneyflow_hsgt）。"""
    local = dm.load_local("northbound.csv")
    if local is not None and not local.empty:
        return local
    if not cfg.ALLOW_REALTIME_API:
        return pd.DataFrame()
    try:
        src = _get_tushare()
        end = datetime.now().strftime("%Y%m%d")
        start = (datetime.now() - timedelta(days=days * 2)).strftime("%Y%m%d")
        df = src.get_northbound(start, end)
        if df is not None and not df.empty:
            dm.save_local(df, "northbound.csv")
        return df if df is not None else pd.DataFrame()
    except Exception:  # noqa: BLE001
        return pd.DataFrame()


@st.cache_data(ttl=cfg.CACHE_TTL)
def get_stock_financial(code: str) -> dict:
    """获取个股财务摘要（Tushare fina_indicator，稳定）。"""
    code = _fmt_code(code)
    local = dm.load_local(f"stock_{code}_fin.json")
    if local:
        return local
    try:
        src = _get_tushare()
        ts_code = code + (".SH" if code.startswith(("6", "9")) else ".SZ")
        fi = src.pro.fina_indicator(ts_code=ts_code)
        if fi is not None and not fi.empty:
            fi = fi.sort_values("end_date")
            latest = fi.iloc[-1]
            result = {
                "report_date": str(latest.get("end_date", "")),
                "revenue": None,
                "revenue_yoy": _to_float(latest.get("tr_yoy", 0)),
                "net_profit": None,
                "net_profit_yoy": _to_float(latest.get("netprofit_yoy", 0)),
                "gross_margin": _to_float(latest.get("grossprofit_margin", 0)),
                "net_margin": _to_float(latest.get("netprofit_margin", 0)),
                "roe": _to_float(latest.get("roe", 0)),
                "debt_ratio": _to_float(latest.get("debt_to_assets", 0)),
                "eps": _to_float(latest.get("eps", 0)),
                "bps": _to_float(latest.get("bps", 0)),
            }
            # 营业收入 / 净利润从 income 接口补
            try:
                inc = src.pro.income(ts_code=ts_code, fields="end_date,revenue,n_income_attr_p")
                if inc is not None and not inc.empty:
                    inc = inc.sort_values("end_date")
                    result["revenue"] = _to_float(inc.iloc[-1].get("revenue", 0))
                    result["net_profit"] = _to_float(inc.iloc[-1].get("n_income_attr_p", 0))
            except Exception:
                pass
            dm.save_local(result, f"stock_{code}_fin.json")
            return result
    except Exception:
        pass
    # 兜底 akshare 同花顺
    try:
        df = ak.stock_financial_abstract_ths(symbol=code, indicator="按报告期")
        if df is not None and not df.empty:
            latest = df.iloc[-1]
            return {
                "report_date": str(latest.get("报告期", "")),
                "revenue": _to_float(latest.get("营业总收入", 0)),
                "revenue_yoy": _to_float(latest.get("营业总收入同比增长率", 0)),
                "net_profit": _to_float(latest.get("净利润", 0)),
                "net_profit_yoy": _to_float(latest.get("净利润同比增长率", 0)),
                "gross_margin": _to_float(latest.get("销售毛利率", 0)),
                "net_margin": _to_float(latest.get("销售净利率", 0)),
                "roe": _to_float(latest.get("净资产收益率", 0)),
                "debt_ratio": _to_float(latest.get("资产负债率", 0)),
                "eps": _to_float(latest.get("基本每股收益", 0)),
                "bps": _to_float(latest.get("每股净资产", 0)),
            }
    except Exception:
        pass
    return {}


@st.cache_data(ttl=cfg.CACHE_TTL)
def get_stock_fund_factors(code: str, days: int = 20) -> pd.DataFrame:
    """个股资金面因子历史（主力净流入 + 换手率 + 量比），供预测模型用。"""
    code = _fmt_code(code)
    ts_code = code + (".SH" if code.startswith("6") else ".SZ")
    try:
        src = _get_tushare()
        end = datetime.now().strftime("%Y%m%d")
        start = (datetime.now() - timedelta(days=days * 2)).strftime("%Y%m%d")
        mf = src.pro.moneyflow(ts_code=ts_code, start_date=start, end_date=end)
        db = src.pro.daily_basic(
            ts_code=ts_code, start_date=start, end_date=end,
            fields="ts_code,trade_date,turnover_rate,volume_ratio",
        )
        if mf is None or mf.empty:
            return pd.DataFrame()
        # 主力净流入 = (大单买+特大单买) - (大单卖+特大单卖)
        mf["main_net"] = (mf.get("buy_lg_amount", 0) + mf.get("buy_elg_amount", 0)) - \
                         (mf.get("sell_lg_amount", 0) + mf.get("sell_elg_amount", 0))
        if db is not None and not db.empty:
            mf = mf.merge(db, on="trade_date", how="left")
        return mf
    except Exception:  # noqa: BLE001
        return pd.DataFrame()


@st.cache_data(ttl=cfg.CACHE_TTL)
def get_stock_fund_flow(code: str) -> dict:
    """获取个股资金流向"""
    code = _fmt_code(code)
    try:
        df = ak.stock_individual_fund_flow(stock=code, market="sh" if code.startswith("6") else "sz")
        if df is None or df.empty:
            return {}
        latest = df.iloc[-1]
        return {
            "date": str(latest.get("日期", "")),
            "main_net_inflow": _to_float(latest.get("主力净流入", 0)),
            "main_net_pct": _to_float(latest.get("主力净流入占比", 0)),
            "super_large_net": _to_float(latest.get("超大单净流入", 0)),
            "large_net": _to_float(latest.get("大单净流入", 0)),
            "mid_net": _to_float(latest.get("中单净流入", 0)),
            "small_net": _to_float(latest.get("小单净流入", 0)),
        }
    except Exception:
        try:
            kline = get_stock_kline(code, days=2)
            if not kline.empty and len(kline) >= 1:
                latest = kline.iloc[-1]
                return {
                    "code": code,
                    "name": "",
                    "price": latest["close"],
                    "change_pct": 0,
                    "change_amt": 0,
                    "volume": latest.get("volume", 0),
                    "amount": latest.get("amount", 0),
                    "turnover": 0,
                    "high": latest["high"],
                    "low": latest["low"],
                    "open": latest["open"],
                }
        except Exception:
            pass
        return {}


# ============================================================
# 5. 龙虎榜 & 游资
# ============================================================

def _ts_inst_to_lhb(inst_df: pd.DataFrame) -> pd.DataFrame:
    """Tushare top_inst → 东财龙虎榜字段格式（下游兼容）。"""
    if inst_df is None or inst_df.empty:
        return pd.DataFrame()
    df = inst_df.rename(columns={
        "exalter": "交易营业部名称",
        "ts_code": "股票代码",
        "buy": "买入金额",
        "sell": "卖出金额",
        "net_buy": "净额",
    })
    df["股票代码"] = df["股票代码"].astype(str).str.split(".").str[0].str.zfill(6)
    try:
        names = _get_tushare().pro.stock_basic(exchange="", list_status="L", fields="ts_code,name")
        name_map = dict(zip(names["ts_code"], names["name"]))
        df["股票名称"] = inst_df["ts_code"].map(name_map)
    except Exception:  # noqa: BLE001
        df["股票名称"] = ""
    return df


@st.cache_data(ttl=cfg.CACHE_TTL)
def get_lhb_recent(days: int = 10) -> pd.DataFrame:
    """获取近N天龙虎榜席位明细（Tushare top_inst，稳定不封）。"""
    local = dm.load_local("lhb.csv")
    if local is None or local.empty:
        local = dm.load_local(f"lhb_{days}.csv")
    if local is not None and not local.empty:
        return local
    if not cfg.ALLOW_REALTIME_API:
        return pd.DataFrame()
    try:
        src = _get_tushare()
        dfs = []
        for i in range(days):
            date = (datetime.now() - timedelta(days=i)).strftime("%Y%m%d")
            try:
                inst = src.get_lhb_inst(date)  # top_inst 席位明细
                if inst is not None and not inst.empty:
                    dfs.append(inst)
            except Exception:  # noqa: BLE001
                continue
            time.sleep(0.1)
        if not dfs:
            return pd.DataFrame()
        df = pd.concat(dfs, ignore_index=True)
        df = _ts_inst_to_lhb(df)  # 字段映射成下游兼容格式
        dm.save_local(df, f"lhb_{days}.csv")
        return df
    except Exception:  # noqa: BLE001
        return pd.DataFrame()


def filter_hot_money(lhb_df: pd.DataFrame) -> pd.DataFrame:
    """从龙虎榜数据中筛选游资操作"""
    if lhb_df.empty:
        return pd.DataFrame()

    seat_col = None
    for col in ["交易营业部名称", "营业部名称"]:
        if col in lhb_df.columns:
            seat_col = col
            break
    if seat_col is None:
        return pd.DataFrame()

    all_keywords = []
    for name, keywords in cfg.HOT_MONEY_SEATS.items():
        all_keywords.extend(keywords)

    pattern = "|".join(all_keywords)
    mask = lhb_df[seat_col].str.contains(pattern, na=False)
    hot_df = lhb_df[mask].copy()

    if hot_df.empty:
        return hot_df

    def label_hot_money(seat_name):
        for name, keywords in cfg.HOT_MONEY_SEATS.items():
            for kw in keywords:
                if kw in str(seat_name):
                    return name
        return "未知游资"

    hot_df["hot_money_name"] = hot_df[seat_col].apply(label_hot_money)
    
    if "净额" not in hot_df.columns:
        if "买入金额" in hot_df.columns and "卖出金额" in hot_df.columns:
            hot_df["净额"] = hot_df["买入金额"].fillna(0) - hot_df["卖出金额"].fillna(0)
        else:
            hot_df["净额"] = 0
    
    return hot_df


@st.cache_data(ttl=cfg.CACHE_TTL)
def get_hot_money_trades(days: int = 10) -> pd.DataFrame:
    """获取游资近N日交易"""
    # 获取足够的天数（多取一些，确保有足够数据）
    fetch_days = max(days + 5, 15)  # 至少15天，确保数据充足
    lhb = get_lhb_recent(days=fetch_days)
    if lhb.empty:
        return lhb
    
    if "trade_date" in lhb.columns:
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")
        lhb["trade_date"] = lhb["trade_date"].astype(str)
        lhb = lhb[lhb["trade_date"] >= cutoff]
    
    return filter_hot_money(lhb)


# ============================================================
# 6. 涨停板
# ============================================================

@st.cache_data(ttl=cfg.CACHE_TTL)
def get_limit_up_stocks() -> pd.DataFrame:
    """获取当日涨停板股票"""
    local = dm.load_local("limit_up.csv")
    if local is not None and not local.empty:
        return local
    if not cfg.ALLOW_REALTIME_API:
        return pd.DataFrame()
    try:
        df = ak.stock_zt_pool_em(date=datetime.now().strftime("%Y%m%d"))
        if df is None or df.empty:
            return pd.DataFrame()
        return df
    except Exception:
        return pd.DataFrame()


# ============================================================
# 7. 市场情绪指标
# ============================================================

@st.cache_data(ttl=cfg.CACHE_TTL)
def get_market_sentiment() -> dict:
    """综合市场情绪指标"""
    local = dm.load_local("sentiment.json")
    if local:
        return local
    if not cfg.ALLOW_REALTIME_API:
        return {}
    # 优先 Tushare：全市场涨跌家数（稳定不封）
    try:
        src = _get_tushare()
        cal = src.pro.trade_cal(exchange="SSE", is_open="1", end_date=datetime.now().strftime("%Y%m%d"))
        td = sorted(cal["cal_date"].tolist())[-1] if cal is not None and not cal.empty else datetime.now().strftime("%Y%m%d")
        daily = src.pro.daily(trade_date=td, fields="ts_code,pct_chg,amount")
        if daily is not None and not daily.empty:
            up_count = int((daily["pct_chg"] > 0).sum())
            down_count = int((daily["pct_chg"] < 0).sum())
            flat_count = len(daily) - up_count - down_count
            total_amount = float(daily["amount"].sum()) / 1e5  # 千元 → 亿元
            zt_count = int(((daily["pct_chg"] >= 9.5)).sum())  # 涨停近似（10%/20% 涨停）
            return {
                "up_count": up_count,
                "down_count": down_count,
                "flat_count": flat_count,
                "up_ratio": up_count / len(daily) * 100 if len(daily) else 0,
                "zt_count": zt_count,
                "zha_rate": None,  # Tushare 拿不到炸板数据，None 表示无数据
                "total_amount": round(total_amount, 1),
                "sentiment": _classify_sentiment(up_count, down_count),
            }
    except Exception:  # noqa: BLE001
        pass
    # 兜底：东财
    try:
        spot_df = ak.stock_zh_a_spot_em()
        up_count = len(spot_df[spot_df["涨跌幅"].apply(lambda x: _to_float(x) or 0) > 0])
        down_count = len(spot_df[spot_df["涨跌幅"].apply(lambda x: _to_float(x) or 0) < 0])
        flat_count = len(spot_df) - up_count - down_count

        zt_df = get_limit_up_stocks()
        zt_count = len(zt_df) if not zt_df.empty else 0

        if not zt_df.empty and "炸板次数" in zt_df.columns:
            zha_count = len(zt_df[zt_df["炸板次数"] > 0])
            zha_rate = zha_count / len(zt_df) * 100 if len(zt_df) > 0 else 0
        else:
            zha_rate = 0

        total_amount = spot_df["成交额"].apply(lambda x: _to_float(x) or 0).sum() / 1e8

        return {
            "up_count": up_count,
            "down_count": down_count,
            "flat_count": flat_count,
            "up_ratio": up_count / len(spot_df) * 100 if len(spot_df) > 0 else 0,
            "zt_count": zt_count,
            "zha_rate": zha_rate,
            "total_amount": total_amount,
            "sentiment": _classify_sentiment(up_count, down_count),
        }
    except Exception:  # noqa: BLE001
        return {}


def _classify_sentiment(up: int, down: int) -> str:
    """根据涨跌比分类情绪"""
    if up + down == 0:
        return "数据异常"
    ratio = up / (up + down)
    if ratio > 0.8:
        return "🔥 极度亢奋"
    elif ratio > 0.65:
        return "😊 偏暖"
    elif ratio > 0.5:
        return "😐 中性"
    elif ratio > 0.35:
        return "😟 偏冷"
    elif ratio > 0.2:
        return "❄️ 冰点"
    else:
        return "💀 恐慌"
        
# ============================================================
# 8. 新增数据模块
# ============================================================

@st.cache_data(ttl=cfg.CACHE_TTL)
def get_stock_zygc(code: str) -> pd.DataFrame:
    """获取主营业务构成（Tushare fina_mainbz，稳定）。"""
    code = _fmt_code(code)
    try:
        src = _get_tushare()
        ts_code = code + (".SH" if code.startswith(("6", "9")) else ".SZ")
        df = src.pro.fina_mainbz(ts_code=ts_code, type="P")
        if df is not None and not df.empty:
            # 只取最近一个报告期，去重，剔除空收入
            latest = df["end_date"].max()
            df = df[df["end_date"] == latest].drop_duplicates("bz_item", keep="last")
            df = df[df["bz_sales"].notna()]
            df = df.rename(columns={
                "end_date": "报告期", "bz_item": "主营项目", "bz_sales": "主营收入(元)",
                "bz_profit": "主营利润(元)", "bz_cost": "主营成本(元)",
            })
            cols = [c for c in ["报告期", "主营项目", "主营收入(元)", "主营利润(元)", "主营成本(元)"] if c in df.columns]
            return df[cols].sort_values("主营收入(元)", ascending=False).reset_index(drop=True)
    except Exception:
        pass
    # 兜底 akshare
    try:
        if code.startswith(("60", "68", "11", "12", "5")):
            market = "sh"
        elif code.startswith(("00", "30", "20", "15", "16", "18")):
            market = "sz"
        else:
            market = "sh"
        df = ak.stock_zygc_em(symbol=f"{market.upper()}{code}")
        if df is not None and not df.empty:
            return df
    except Exception:
        pass
    return pd.DataFrame()


@st.cache_data(ttl=cfg.CACHE_TTL)
def get_stock_top10(code: str) -> pd.DataFrame:
    """获取十大股东（Tushare top10_holders，稳定）。"""
    code = _fmt_code(code)
    try:
        src = _get_tushare()
        ts_code = code + (".SH" if code.startswith(("6", "9")) else ".SZ")
        df = src.pro.top10_holders(ts_code=ts_code)
        if df is not None and not df.empty:
            df = df.sort_values("end_date").drop_duplicates("holder_name", keep="last")
            df = df.rename(columns={"end_date": "报告期", "holder_name": "股东名称",
                                    "hold_amount": "持股数(股)", "hold_ratio": "持股比例(%)"})
            cols = [c for c in ["报告期", "股东名称", "持股数(股)", "持股比例(%)"] if c in df.columns]
            return df[cols].head(10).reset_index(drop=True)
    except Exception:
        pass
    # 兜底 akshare
    try:
        prefix = "sh" if code.startswith("6") else "sz"
        df = ak.stock_gdfx_top_10_em(symbol=f"{prefix}{code}")
        if df is not None and not df.empty:
            return df
    except Exception:
        pass
    return pd.DataFrame()


@st.cache_data(ttl=cfg.CACHE_TTL)
def get_stock_top10_free(code: str) -> pd.DataFrame:
    """获取十大流通股东（Tushare top10_floatholders，稳定）。"""
    code = _fmt_code(code)
    try:
        src = _get_tushare()
        ts_code = code + (".SH" if code.startswith(("6", "9")) else ".SZ")
        df = src.pro.top10_floatholders(ts_code=ts_code)
        if df is not None and not df.empty:
            df = df.sort_values("end_date").drop_duplicates("holder_name", keep="last")
            df = df.rename(columns={"end_date": "报告期", "holder_name": "股东名称",
                                    "hold_amount": "持股数(股)", "hold_ratio": "持股比例(%)"})
            cols = [c for c in ["报告期", "股东名称", "持股数(股)", "持股比例(%)"] if c in df.columns]
            return df[cols].head(10).reset_index(drop=True)
    except Exception:
        pass
    # 兜底 akshare
    try:
        prefix = "sh" if code.startswith("6") else "sz"
        df = ak.stock_gdfx_free_top_10_em(symbol=f"{prefix}{code}")
        if df is not None and not df.empty:
            return df
    except Exception:
        pass
    return pd.DataFrame()


@st.cache_data(ttl=cfg.CACHE_TTL)
def get_stock_research(code: str) -> pd.DataFrame:
    """获取机构研报（Tushare report_rc，稳定）。"""
    code = _fmt_code(code)
    try:
        src = _get_tushare()
        ts_code = code + (".SH" if code.startswith(("6", "9")) else ".SZ")
        df = src.pro.report_rc(ts_code=ts_code)
        if df is not None and not df.empty:
            # 按研报标题去重（同一标题会被多家转载/重复收录）
            df = df.drop_duplicates("report_title", keep="first").sort_values("report_date", ascending=False)
            df = df.rename(columns={"report_date": "报告日期", "report_title": "研报标题", "report_org": "机构名称"})
            cols = [c for c in ["报告日期", "研报标题", "机构名称"] if c in df.columns]
            return df[cols].head(10).reset_index(drop=True)
    except Exception:
        pass
    # 兜底 akshare
    try:
        df = ak.stock_research_report_em(symbol=code)
        if df is not None and not df.empty:
            return df
    except Exception:
        pass
    return pd.DataFrame()


@st.cache_data(ttl=cfg.CACHE_TTL)
def get_stock_news(code: str) -> pd.DataFrame:
    """获取个股新闻（新浪源）"""
    code = _fmt_code(code)
    try:
        # 尝试用新浪新闻接口
        df = ak.stock_news_sina(symbol=code)
        if df is not None and not df.empty:
            return df
    except Exception:
        pass
    try:
        # 备选：东方财富
        df = ak.stock_news_em(symbol=code)
        if df is not None and not df.empty:
            return df
    except Exception as e:
        print(f"个股新闻获取失败: {e}")
    return pd.DataFrame()


@st.cache_data(ttl=cfg.CACHE_TTL)
def get_stock_dividend(code: str) -> pd.DataFrame:
    """获取历史分红（Tushare dividend，稳定）。"""
    code = _fmt_code(code)
    try:
        src = _get_tushare()
        ts_code = code + (".SH" if code.startswith(("6", "9")) else ".SZ")
        df = src.pro.dividend(ts_code=ts_code)
        if df is not None and not df.empty:
            # 同一报告期有多条（预案/实施等），保留「实施阶段」（有派息日的），去重
            df["_has_pay"] = df["pay_date"].notna().astype(int)
            df = df.sort_values("_has_pay", ascending=False).drop_duplicates("end_date", keep="first")
            df = df.drop(columns=["_has_pay"]).sort_values("end_date", ascending=False)
            df = df.rename(columns={
                "end_date": "报告期", "ann_date": "公告日", "cash_div": "每股派息(元)",
                "stk_div": "每股送股", "stk_bo_rate": "送股比例", "stk_co_rate": "转增比例",
                "record_date": "登记日", "ex_date": "除权除息日", "pay_date": "派息日",
            })
            cols = [c for c in ["报告期", "公告日", "每股派息(元)", "每股送股", "转增比例", "登记日", "除权除息日", "派息日"] if c in df.columns]
            return df[cols].head(20).reset_index(drop=True)
    except Exception:
        pass
    # 兜底 akshare
    try:
        df = ak.stock_history_dividend_detail(symbol=code, indicator="分红")
        if df is not None and not df.empty:
            return df
    except Exception:
        pass
    return pd.DataFrame()


@st.cache_data(ttl=cfg.CACHE_TTL)
def get_stock_share_alloc(code: str) -> pd.DataFrame:
    """获取历史送转（Tushare dividend 的送转字段，稳定）。"""
    code = _fmt_code(code)
    try:
        src = _get_tushare()
        ts_code = code + (".SH" if code.startswith(("6", "9")) else ".SZ")
        df = src.pro.dividend(ts_code=ts_code)
        if df is not None and not df.empty:
            df = df[df.get("stk_div", 0).fillna(0) > 0]  # 只留有送转的
            df = df.rename(columns={
                "end_date": "报告期", "stk_div": "每股送股", "stk_bo_rate": "送股比例",
                "stk_co_rate": "转增比例", "ex_date": "除权除息日",
            })
            cols = [c for c in ["报告期", "每股送股", "送股比例", "转增比例", "除权除息日"] if c in df.columns]
            return df[cols].head(20).reset_index(drop=True)
    except Exception:
        pass
    # 兜底 akshare
    try:
        df = ak.stock_history_dividend_detail(symbol=code, indicator="配股")
        if df is not None and not df.empty:
            return df
    except Exception:
        pass
    return pd.DataFrame()


@st.cache_data(ttl=cfg.CACHE_TTL)
def get_stock_release(code: str) -> pd.DataFrame:
    """获取限售解禁（Tushare share_float，稳定）。"""
    code = _fmt_code(code)
    try:
        src = _get_tushare()
        ts_code = code + (".SH" if code.startswith(("6", "9")) else ".SZ")
        df = src.pro.share_float(ts_code=ts_code)
        if df is not None and not df.empty:
            df = df.rename(columns={
                "float_date": "解禁日期", "float_share": "解禁数量(股)",
                "float_ratio": "解禁占比(%)", "holder_name": "股东名称",
            })
            cols = [c for c in ["解禁日期", "解禁数量(股)", "解禁占比(%)", "股东名称"] if c in df.columns]
            return df[cols].head(20).reset_index(drop=True)
    except Exception:
        pass
    # 兜底 akshare
    try:
        df = ak.stock_restricted_release_queue_em(symbol=code)
        if df is not None and not df.empty:
            return df
    except Exception:
        pass
    return pd.DataFrame()


@st.cache_data(ttl=cfg.CACHE_TTL)
def get_lhb_trader_detail(days: int = 5) -> pd.DataFrame:
    """获取龙虎榜个股-营业部明细，含游资名映射"""
    end = datetime.now()
    start = end - timedelta(days=days)
    date_str = end.strftime("%Y%m%d")
    start_str = start.strftime("%Y%m%d")
    
    # 1. 获取近日全部龙虎榜股票
    try:
        all_lhb = ak.stock_lhb_detail_em(start_date=start_str, end_date=date_str)
        if all_lhb.empty: return pd.DataFrame()
    except:
        return pd.DataFrame()
    
    all_rows = []
    url = 'https://datacenter-web.eastmoney.com/api/data/v1/get'
    h = {'User-Agent': 'Mozilla/5.0'}
    
    # 2. 遍历每只股票获取营业部明细
    for _, row in all_lhb.iterrows():
        code = str(row.get('代码', ''))
        date_val = str(row.get('日期', ''))[:10].replace('-', '-')
        if not code or not date_val: continue
        
        for flag, rpt, sc in [('买入', 'RPT_BILLBOARD_DAILYDETAILSBUY', 'BUY'),
                               ('卖出', 'RPT_BILLBOARD_DAILYDETAILSSELL', 'SELL')]:
            try:
                flt = f"(TRADE_DATE='{date_val}')(SECURITY_CODE=\"{code}\")"
                params = {'reportName': rpt, 'columns': 'ALL', 'filter': flt,
                          'pageNumber': '1', 'pageSize': '20', 'sortTypes': '-1',
                          'sortColumns': sc, 'source': 'WEB', 'client': 'WEB'}
                r = requests.get(url, params=params, headers=h, timeout=10)
                d = r.json()
                if d.get('success') and d['result'].get('data'):
                    for item in d['result']['data']:
                        dept_name = item.get('OPERATEDEPT_NAME', '')
                        buy_amt = item.get('BUY') or 0
                        sell_amt = item.get('SELL') or 0
                        amount = buy_amt if flag == '买入' else sell_amt
                        all_rows.append({
                            '日期': date_val, '股票代码': code,
                            '股票名称': row.get('名称', ''),
                            '营业部': dept_name,
                            '方向': flag,
                            '金额(万)': round(amount / 10000, 2) if amount else 0,
                            '营业部代码': item.get('OPERATEDEPT_CODE', ''),
                        })
            except:
                pass
    
    if not all_rows: return pd.DataFrame()
    df = pd.DataFrame(all_rows)
    
    # 3. 匹配游资名
    seat_map = cfg.HOT_MONEY_SEATS
    def match_trader(dept):
        if not dept: return ''
        for trader, keywords in seat_map.items():
            for kw in keywords:
                if kw in str(dept):
                    return trader
        return ''
    df['游资'] = df['营业部'].apply(match_trader)
    
    # 4. 过滤只保留有游资名或金额>500万的行
    df = df[(df['游资'] != '') | (df['金额(万)'] > 500)]
    return df.sort_values(['日期', '金额(万)'], ascending=[False, False]).reset_index(drop=True)

# ============================================================
# 8. 板块龙头股（每个行业市值前 N，供每日龙头分析）
# ============================================================

@st.cache_data(ttl=cfg.CACHE_TTL)
def get_industry_leaders(top_n: int = 2) -> pd.DataFrame:
    """每个行业市值前 top_n 的龙头股（Tushare stock_basic + daily_basic）。

    返回列：trade_date, industry, ts_code, name, total_mv(万), circ_mv(万),
            turnover_rate, pe, pb, pct_chg
    """
    try:
        src = _get_tushare()
        # 最近交易日
        cal = src.pro.trade_cal(exchange="SSE", is_open="1", end_date=datetime.now().strftime("%Y%m%d"))
        td = sorted(cal["cal_date"].tolist())[-1] if cal is not None and not cal.empty else datetime.now().strftime("%Y%m%d")
        sb = src.pro.stock_basic(exchange="", list_status="L", fields="ts_code,name,industry")
        db = src.pro.daily_basic(trade_date=td, fields="ts_code,total_mv,circ_mv,turnover_rate,pe,pb")
        daily = src.pro.daily(trade_date=td, fields="ts_code,pct_chg")
        if sb is None or db is None or db.empty:
            return pd.DataFrame()
        m = sb.merge(db, on="ts_code", how="inner")
        if daily is not None and not daily.empty:
            m = m.merge(daily[["ts_code", "pct_chg"]], on="ts_code", how="left")
        else:
            m["pct_chg"] = 0
        # 剔除行业为空
        m = m[m["industry"].notna() & (m["industry"] != "")]
        # 每个行业取市值前 top_n
        leaders = (m.sort_values("total_mv", ascending=False)
                    .groupby("industry", group_keys=False).head(top_n)
                    .reset_index(drop=True))
        leaders["trade_date"] = td
        return leaders
    except Exception:  # noqa: BLE001
        return pd.DataFrame()


@st.cache_data(ttl=cfg.CACHE_TTL)
def get_stock_valuation(code: str) -> dict:
    """个股估值数据（总市值/流通市值/PE/PB/换手率，Tushare daily_basic）。"""
    code = _fmt_code(code)
    try:
        src = _get_tushare()
        ts_code = code + (".SH" if code.startswith(("6", "9")) else ".SZ")
        cal = src.pro.trade_cal(exchange="SSE", is_open="1", end_date=datetime.now().strftime("%Y%m%d"))
        td = sorted(cal["cal_date"].tolist())[-1] if cal is not None and not cal.empty else datetime.now().strftime("%Y%m%d")
        db = src.pro.daily_basic(ts_code=ts_code, trade_date=td, fields="total_mv,circ_mv,pe,pb,turnover_rate")
        if db is not None and not db.empty:
            r = db.iloc[-1]
            return {
                "total_mv": _to_float(r.get("total_mv", 0)) * 10000,   # 万元 → 元
                "circ_mv": _to_float(r.get("circ_mv", 0)) * 10000,
                "pe": _to_float(r.get("pe", 0)),
                "pb": _to_float(r.get("pb", 0)),
                "turnover_rate": _to_float(r.get("turnover_rate", 0)),
            }
    except Exception:  # noqa: BLE001
        pass
    return {}


@st.cache_data(ttl=cfg.CACHE_TTL)
def get_industry_pct() -> dict:
    """申万行业涨跌（Tushare daily + stock_basic 自己算，与龙头 industry 同一套分类）。"""
    try:
        src = _get_tushare()
        cal = src.pro.trade_cal(exchange="SSE", is_open="1", end_date=datetime.now().strftime("%Y%m%d"))
        td = sorted(cal["cal_date"].tolist())[-1] if cal is not None and not cal.empty else datetime.now().strftime("%Y%m%d")
        d = src.pro.daily(trade_date=td, fields="ts_code,pct_chg")
        sb = src.pro.stock_basic(list_status="L", fields="ts_code,industry")
        if d is not None and not d.empty and sb is not None and not sb.empty:
            m = d.merge(sb, on="ts_code", how="left")
            m = m[m["industry"].notna()]
            return m.groupby("industry")["pct_chg"].mean().round(2).to_dict()
    except Exception:  # noqa: BLE001
        pass
    return {}


def _to_ts_code(code: str) -> str:
    """6位代码 → Tushare 代码（6开头.SH，其余.SZ/.BJ）。"""
    c = str(code).zfill(6)
    if c.startswith("6"):
        return c + ".SH"
    if c.startswith(("4", "8")):
        return c + ".BJ"
    return c + ".SZ"


def _get_period_return(code: str, start_date: str, end_date: str):
    """持仓期间涨幅 = 最近收盘 / 首次收盘 - 1（百分比）。"""
    try:
        pro = _get_tushare().pro
        daily = pro.daily(ts_code=_to_ts_code(code), start_date=str(start_date), end_date=str(end_date))
        if daily is None or daily.empty:
            return None
        daily = daily.sort_values("trade_date")
        return round((float(daily["close"].iloc[-1]) / float(daily["close"].iloc[0]) - 1) * 100, 2)
    except Exception:  # noqa: BLE001
        return None


def get_hot_money_positions(hot_df: pd.DataFrame) -> pd.DataFrame:
    """游资持仓汇总：按 游资×股票 聚合，推算持仓/清仓状态。

    龙虎榜只披露买卖前5营业部，小额交易抓不到，所以：
    - 卖出 >= 买入 → 已清仓（确定）
    - 买入 - 卖出 < 买入的 5% → 疑似清仓（剩余很少忽略）
    - 其余 → 持仓中
    """
    if hot_df is None or hot_df.empty:
        return pd.DataFrame()
    g = hot_df.groupby(["hot_money_name", "股票代码", "股票名称"]).agg(
        累计买入=("买入金额", "sum"),
        累计卖出=("卖出金额", "sum"),
        首次买入=("trade_date", "min"),
        最近操作=("trade_date", "max"),
    ).reset_index()

    def _status(r):
        buy, sell = float(r["累计买入"]), float(r["累计卖出"])
        if sell >= buy:
            return "已清仓"
        if buy - sell < buy * 0.05:
            return "疑似清仓"
        return "持仓中"

    g["状态"] = g.apply(_status, axis=1)

    # 持仓天数（首次买入 → 最近操作，自然日）
    g["持仓天数"] = g.apply(
        lambda r: (datetime.strptime(str(r["最近操作"]), "%Y%m%d") - datetime.strptime(str(r["首次买入"]), "%Y%m%d")).days,
        axis=1,
    )
    # 持仓期间涨幅（首次买入收盘 → 最近操作收盘）
    g["期间涨幅%"] = g.apply(
        lambda r: _get_period_return(r["股票代码"], str(r["首次买入"]), str(r["最近操作"])),
        axis=1,
    )
    # 金额转万元（原始是元）
    g["净持仓(万)"] = ((g["累计买入"] - g["累计卖出"]) / 1e4).round(2)
    g["累计买入(万)"] = (g["累计买入"] / 1e4).round(2)
    g["累计卖出(万)"] = (g["累计卖出"] / 1e4).round(2)
    g = g.drop(columns=["累计买入", "累计卖出"])
    g = g.sort_values("净持仓(万)", ascending=False).reset_index(drop=True)
    return g


def merge_hot_money_daily(hot_df: pd.DataFrame) -> pd.DataFrame:
    """游资交易明细：同一天同一只票合并成一条（买入、卖出各自加总）。"""
    if hot_df is None or hot_df.empty:
        return pd.DataFrame()
    cols = ["trade_date", "hot_money_name", "股票名称", "股票代码"]
    agg = {
        "买入金额": "sum",
        "卖出金额": "sum",
    }
    g = hot_df.groupby(cols, as_index=False).agg(agg)
    g["净额"] = g["买入金额"] - g["卖出金额"]
    return g.sort_values(["trade_date", "净额"], ascending=[False, False]).reset_index(drop=True)
