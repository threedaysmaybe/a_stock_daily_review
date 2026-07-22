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

# ============================================================
# 通用工具
# ============================================================

def _fmt_code(raw: str) -> str:
    """统一6位代码格式"""
    return str(raw).zfill(6)

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
    """
    获取指数日K线
    index_code: '000001'（上证）, '399001'（深证）, '399006'（创业板）, '000688'（科创50）
    返回 DataFrame：[date, open, high, low, close, volume, amount]
    """
    local = dm.load_local(f"index_{index_code}.csv")
    if local is not None and not local.empty:
        return local
    try:
        prefix = "sh" if index_code.startswith("000") or index_code.startswith("60") else "sz"
        df = ak.stock_zh_index_daily(symbol=f"{prefix}{index_code}")
        if df is None or df.empty:
            return pd.DataFrame()
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date").tail(days).reset_index(drop=True)
        return df
    except Exception:
        try:
            df = ak.stock_zh_index_daily_em(symbol=f"sh{index_code}" if index_code.startswith("000") else f"sz{index_code}")
            df["date"] = pd.to_datetime(df["date"])
            df = df.sort_values("date").tail(days).reset_index(drop=True)
            return df
        except Exception:
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
        try:
            url = "https://q.10jqka.com.cn/gn/"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": "https://q.10jqka.com.cn/",
            }
            
            response = requests.get(url, headers=headers, timeout=10)
            response.encoding = "gbk"
            
            if response.status_code == 200:
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
        
        response = requests.get(url, headers=headers, timeout=10)
        response.encoding = "gbk"
        
        if response.status_code == 200:
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
    if local is not None and not local.empty:
        return local
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
    except Exception as e:
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
    """获取全市场资金流向（主力/超大单/大单/中单/小单）"""
    try:
        df = ak.stock_market_fund_flow()
        return df
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=cfg.CACHE_TTL)
def get_stock_financial(code: str) -> dict:
    """获取个股财务摘要"""
    code = _fmt_code(code)
    local = dm.load_local(f"stock_{code}_fin.json")
    if local:
        return local
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

@st.cache_data(ttl=cfg.CACHE_TTL)
def get_lhb_recent(days: int = 10) -> pd.DataFrame:
    """获取近N天龙虎榜数据"""
    # 按天数分别缓存
    local = dm.load_local(f"lhb_{days}.csv")
    if local is not None and not local.empty:
        return local
    try:
        dfs = []
        for i in range(days):
            date = (datetime.now() - timedelta(days=i)).strftime("%Y%m%d")
            try:
                summary = ak.stock_lhb_detail_em(start_date=date, end_date=date)
                if summary is not None and not summary.empty:
                    for _, row in summary.iterrows():
                        try:
                            stock_code = str(row["代码"]).zfill(6)
                            detail = ak.stock_lhb_stock_detail_em(date=date, symbol=stock_code)
                            if detail is not None and not detail.empty:
                                detail["trade_date"] = date
                                detail["股票代码"] = stock_code
                                detail["股票名称"] = row.get("名称", "")
                                dfs.append(detail)
                        except Exception:
                            continue
                        time.sleep(0.05)
            except Exception:
                continue
            time.sleep(0.1)
        if not dfs:
            return pd.DataFrame()
        df = pd.concat(dfs, ignore_index=True)
        # 保存到按天数的缓存文件
        dm.save_local(df, f"lhb_{days}.csv")
        return df
    except Exception:
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
    """获取主营业务构成"""
    code = _fmt_code(code)
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
    except Exception as e:
        print(f"主营业务构成获取失败: {e}")
    return pd.DataFrame()


@st.cache_data(ttl=cfg.CACHE_TTL)
def get_stock_top10(code: str) -> pd.DataFrame:
    """获取十大股东"""
    code = _fmt_code(code)
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
    """获取十大流通股东"""
    code = _fmt_code(code)
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
    """获取机构研报"""
    code = _fmt_code(code)
    try:
        df = ak.stock_research_report_em(symbol=code)
        if df is not None and not df.empty:
            return df
    except Exception as e:
        print(f"机构研报获取失败: {e}")
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
    """获取历史分红"""
    code = _fmt_code(code)
    try:
        df = ak.stock_history_dividend_detail(symbol=code, indicator="分红")
        if df is not None and not df.empty:
            return df
    except Exception as e:
        print(f"分红数据获取失败: {e}")
    return pd.DataFrame()


@st.cache_data(ttl=cfg.CACHE_TTL)
def get_stock_share_alloc(code: str) -> pd.DataFrame:
    """获取历史送转"""
    code = _fmt_code(code)
    try:
        df = ak.stock_history_dividend_detail(symbol=code, indicator="配股")
        if df is not None and not df.empty:
            return df
    except Exception as e:
        print(f"送转数据获取失败: {e}")
    return pd.DataFrame()


@st.cache_data(ttl=cfg.CACHE_TTL)
def get_stock_release(code: str) -> pd.DataFrame:
    """获取限售解禁"""
    code = _fmt_code(code)
    try:
        df = ak.stock_restricted_release_queue_em(symbol=code)
        if df is not None and not df.empty:
            return df
    except Exception as e:
        print(f"限售解禁获取失败: {e}")
    return pd.DataFrame()