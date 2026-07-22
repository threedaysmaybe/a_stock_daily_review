"""
数据管理模块 — 批量下载 + 本地文件读写
工作日运行一次，各页面直接读本地文件秒开
"""

import os
import json
import time
import pandas as pd
from datetime import datetime, timedelta
import akshare as ak
import streamlit as st

import config as cfg
try:
    with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "portfolio.json"), "r", encoding="utf-8") as _pf:
        _local_pf = json.load(_pf)
except Exception:
    _local_pf = dict(cfg.PORTFOLIO)

# 本地数据目录
DATA_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

def _today_str() -> str:
    """获取今天的日期字符串"""
    return datetime.now().strftime("%Y%m%d")

def _today_dir() -> str:
    """今天的数据目录"""
    d = os.path.join(DATA_ROOT, _today_str())
    os.makedirs(d, exist_ok=True)
    return d

def _fmt_code(code: str) -> str:
    return str(code).zfill(6)

def _to_float(s):
    try: return float(s)
    except: return None

# ============================================================
# 批量下载
# ============================================================

def download_all(progress_callback=None) -> dict:
    """
    一次性下载所有数据到本地
    progress_callback(i, total, name) — 进度回调
    返回 {成功数, 失败数, 文件列表}
    """
    today = _today_dir()
    tasks = _build_task_list()
    total = len(tasks)
    ok, fail = 0, 0
    files = []

    for i, task in enumerate(tasks):
        name = task["name"]
        try:
            if progress_callback:
                progress_callback(i, total, name)

            result = task["fn"]()
            if result is not None and not (isinstance(result, pd.DataFrame) and result.empty):
                _save(task, result, today)
                ok += 1
                files.append(task["filename"])
            else:
                fail += 1
        except Exception as e:
            fail += 1
            # print(f"[SKIP] {name}: {e}")
        time.sleep(0.05)  # 避免请求太快

    # 保存元信息
    meta = {
        "date": _today_str(),
        "download_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "ok": ok, "fail": fail, "total": total,
        "files": files,
    }
    with open(os.path.join(today, "_meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    if progress_callback:
        progress_callback(total - 1, total, "检查缺失数据并回补...")

    # 回补缺失的历史交易日板块数据
    backfilled = _backfill_missing_dates(today)

    if progress_callback:
        progress_callback(total - 1, total, "写入完成，即将刷新...")

    return meta


def _build_task_list() -> list:
    """构建下载任务列表"""
    tasks = []

    # 1. 指数K线
    for idx_name, idx_code in cfg.INDICES.items():
        tasks.append({
            "name": f"{idx_name}",
            "filename": f"index_{idx_code}.csv",
            "fn": lambda c=idx_code: _download_index_kline(c),
        })

    # 2. 板块行情
    tasks.append({
        "name": "行业板块行情",
        "filename": "sectors.csv",
        "fn": _download_sectors,
    })
    # 2.5 概念板块行情 ← 新增
    tasks.append({
        "name": "概念板块行情",
        "filename": "concept_sectors.csv",
        "fn": _download_concept_sectors,
    })
    
    # 3. 市场情绪
    tasks.append({
        "name": "市场情绪指标",
        "filename": "sentiment.json",
        "fn": _download_sentiment,
    })

    # 4. 个股K线
    for code in _local_pf:
        tasks.append({
            "name": f"{_local_pf[code]}",
            "filename": f"stock_{code}.csv",
            "fn": lambda c=code: _download_stock_kline(c),
        })
        tasks.append({
            "name": f"{_local_pf[code]} 财务",
            "filename": f"stock_{code}_fin.json",
            "fn": lambda c=code: _download_stock_financial(c),
        })

    # 5. 涨停板
    tasks.append({
        "name": "涨停板数据",
        "filename": "limit_up.csv",
        "fn": _download_limit_up,
    })

    # 6. 龙虎榜
    tasks.append({
        "name": "龙虎榜数据",
        "filename": "lhb.csv",
        "fn": _download_lhb,
    })

    # 7. 股票列表（搜索用）
    tasks.append({
        "name": "全市场股票列表",
        "filename": "stock_list.csv",
        "fn": _download_stock_list,
    })

    return tasks


# ============================================================
# 下载函数（内部）
# ============================================================

def _download_index_kline(code: str) -> pd.DataFrame:
    """下载指数K线（新浪源）"""
    prefix = "sh" if code.startswith("000") or code.startswith("60") else "sz"
    df = ak.stock_zh_index_daily(symbol=f"{prefix}{code}")
    if df is not None and not df.empty:
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date").tail(120).reset_index(drop=True)
    return df


def _download_sectors() -> pd.DataFrame:
    """下载行业板块行情（同花顺源，90行业）"""
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
            df["change_pct"] = df["change_pct"].apply(_to_float)
            for col in ["up_count", "down_count", "top_stock"]:
                if col not in df.columns:
                    df[col] = 0 if col != "top_stock" else ""
            df = df[["sector_name", "change_pct", "up_count", "down_count", "top_stock"]]
            df = df.sort_values("change_pct", ascending=False).reset_index(drop=True)
            return df
    except Exception:
        pass
    return pd.DataFrame()


def _download_concept_sectors() -> pd.DataFrame:
    """下载概念板块数据"""
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
                    df = pd.DataFrame(concepts)
                    df = df.sort_values("change_pct", ascending=False).reset_index(drop=True)
                    return df
    except Exception as e:
        print(f"概念板块下载失败: {e}")
    
    return pd.DataFrame()

def _download_sentiment() -> dict:
    """下载市场情绪"""
    try:
        spot = ak.stock_zh_a_spot_em()
        if spot is None or spot.empty:
            return {}
        pct_col = "涨跌幅"
        up = len(spot[spot[pct_col].apply(lambda x: _to_float(x) or 0) > 0])
        down = len(spot[spot[pct_col].apply(lambda x: _to_float(x) or 0) < 0])
        flat = len(spot) - up - down
        total_amt = spot["成交额"].apply(lambda x: _to_float(x) or 0).sum() / 1e8

        ratio = up / (up + down) if (up + down) > 0 else 0.5
        if ratio > 0.8: sent = "极度亢奋"
        elif ratio > 0.65: sent = "偏暖"
        elif ratio > 0.5: sent = "中性"
        elif ratio > 0.35: sent = "偏冷"
        elif ratio > 0.2: sent = "冰点"
        else: sent = "恐慌"

        return {
            "up_count": up, "down_count": down, "flat_count": flat,
            "up_ratio": round(up / len(spot) * 100, 1) if len(spot) > 0 else 0,
            "total_amount": round(total_amt, 0),
            "sentiment": sent,
        }
    except Exception:
        return {}


def _download_stock_kline(code: str) -> pd.DataFrame:
    """下载个股K线（新浪源）"""
    code = _fmt_code(code)
    prefix = "sh" if code.startswith("6") else "sz"
    df = ak.stock_zh_a_daily(symbol=f"{prefix}{code}", adjust="qfq")
    if df is not None and not df.empty:
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date").tail(120).reset_index(drop=True)
    return df


def _download_stock_financial(code: str) -> dict:
    """下载个股财务数据"""
    code = str(code).zfill(6)
    try:
        df = ak.stock_financial_abstract_ths(symbol=code, indicator="按报告期")
        if df is not None and not df.empty:
            latest = df.iloc[-1]
            return {
                "report_date": str(latest.get("报告期", "")),
                "revenue": _to_float(latest.get("营业收入", 0)),
                "revenue_yoy": _to_float(latest.get("营业收入同比增长", 0)),
                "net_profit": _to_float(latest.get("净利润", 0)),
                "net_profit_yoy": _to_float(latest.get("净利润同比增长", 0)),
                "gross_margin": _to_float(latest.get("销售毛利率", 0)),
                "net_margin": _to_float(latest.get("销售净利率", 0)),
                "roe": _to_float(latest.get("净资产收益率", 0)),
                "debt_ratio": _to_float(latest.get("资产负债率", 0)),
                "eps": _to_float(latest.get("每股收益", 0)),
                "bps": _to_float(latest.get("每股净资产", 0)),
            }
    except Exception:
        pass
    return {}


def _download_limit_up() -> pd.DataFrame:
    """下载涨停板"""
    try:
        return ak.stock_zt_pool_em(date=datetime.now().strftime("%Y%m%d"))
    except Exception:
        return pd.DataFrame()


def _download_lhb() -> pd.DataFrame:
    """下载龙虎榜近30日（席位详情，便于本地筛选）"""
    dfs = []
    for i in range(30):
        date_str = (datetime.now() - timedelta(days=i)).strftime("%Y%m%d")
        try:
            summary = ak.stock_lhb_detail_em(start_date=date_str, end_date=date_str)
            if summary is not None and not summary.empty:
                for _, row in summary.iterrows():
                    try:
                        stock_code = str(row["代码"]).zfill(6)
                        detail = ak.stock_lhb_stock_detail_em(date=date_str, symbol=stock_code)
                        if detail is not None and not detail.empty:
                            detail["trade_date"] = date_str
                            detail["股票代码"] = stock_code
                            detail["股票名称"] = row.get("名称", "")
                            dfs.append(detail)
                    except Exception:
                        continue
                    time.sleep(0.05)  # 减少延迟
        except Exception:
            continue
        time.sleep(0.05)
    if dfs:
        return pd.concat(dfs, ignore_index=True)
    return pd.DataFrame()


def _download_stock_list() -> pd.DataFrame:
    """下载全市场股票列表（代码+名称，供搜索用）"""
    import akshare as ak
    for src in ['em', 'sina']:
        try:
            df = ak.stock_zh_a_spot_em() if src == 'em' else ak.stock_zh_a_spot()
            if df is not None and not df.empty:
                cc = '代码'
                if df[cc].iloc[0].startswith('sh') or df[cc].iloc[0].startswith('sz'):
                    df[cc] = df[cc].str[2:]
                return pd.DataFrame({"code": df[cc], "name": df['名称']})
        except Exception:
            continue
    return pd.DataFrame()


def _backfill_missing_dates(today_dir: str) -> int:
    """回补最近10个交易日内缺失的板块排名数据，返回回补天数"""
    if not os.path.exists(DATA_ROOT):
        return 0
    
    # 收集所有可用的日期目录
    all_dirs = sorted([d for d in os.listdir(DATA_ROOT) 
                       if os.path.isdir(os.path.join(DATA_ROOT, d)) and d.isdigit()])
    if not all_dirs:
        return 0
    
    # 读取今天的上证指数K线，获取最近10个交易日列表
    index_path = os.path.join(today_dir, "index_000001.csv")
    if not os.path.exists(index_path):
        return 0
    
    try:
        idx_df = pd.read_csv(index_path, encoding="utf-8-sig")
        if idx_df.empty or "date" not in idx_df.columns:
            return 0
        idx_df["date"] = pd.to_datetime(idx_df["date"])
        # 最近10个交易日
        last_date = idx_df["date"].iloc[-1]
        trading_days = idx_df[idx_df["date"] >= last_date - timedelta(days=14)]["date"]
        trading_days = sorted(set(d.dt.strftime("%Y%m%d") for d in trading_days))
        trading_days = trading_days[-10:]  # 最多回补10天
    except Exception:
        return 0
    
    backfilled = 0
    for date_str in trading_days:
        target_dir = os.path.join(DATA_ROOT, date_str)
        
        # 检查是否需要回补行业板块
        sector_path = os.path.join(target_dir, "sectors.csv")
        if not os.path.exists(sector_path):
            if _try_backfill_sectors(target_dir, date_str):
                backfilled += 1
        
        # 检查是否需要回补概念板块
        concept_path = os.path.join(target_dir, "concept_sectors.csv")
        if not os.path.exists(concept_path):
            if _try_backfill_concepts(target_dir, date_str):
                backfilled += 1
    
    return backfilled


def _try_backfill_sectors(target_dir: str, date_str: str) -> bool:
    """回补行业板块：同花顺真实行业指数"""
    try:
        # 往前推几天取基准价
        from datetime import datetime as _dt, timedelta as _td
        start_dt = _dt.strptime(date_str, '%Y%m%d') - _td(days=4)
        start_str = start_dt.strftime('%Y%m%d')
        
        rows = []
        names = _get_ths_industry_names()
        for name in names:
            try:
                df = ak.stock_board_industry_index_ths(symbol=name, start_date=start_str, end_date=date_str)
                if df is not None and len(df) >= 2:
                    prev_close = float(df.iloc[-2]['收盘价'])
                    curr_close = float(df.iloc[-1]['收盘价'])
                    change_pct = (curr_close - prev_close) / prev_close * 100 if prev_close else 0
                    rows.append({'sector_name': name, 'change_pct': round(change_pct, 2),
                                 'up_count': 0, 'down_count': 0, 'top_stock': ''})
            except Exception:
                continue
            time.sleep(0.1)
        if rows:
            df = pd.DataFrame(rows)
            df = df.sort_values('change_pct', ascending=False).reset_index(drop=True)
            os.makedirs(target_dir, exist_ok=True)
            df.to_csv(os.path.join(target_dir, 'sectors.csv'), index=False, encoding='utf-8-sig')
            with open(os.path.join(target_dir, '_backfill_date.txt'), 'w') as f:
                f.write(date_str)
            return True
    except Exception:
        pass
    return False


def _get_ths_industry_names() -> list:
    if _get_ths_industry_names._cache:
        return _get_ths_industry_names._cache
    try:
        df = ak.stock_board_industry_name_ths()
        names = df['name'].tolist() if df is not None and not df.empty else []
        _get_ths_industry_names._cache = names
        return names
    except Exception:
        return []
_get_ths_industry_names._cache = []


def _try_backfill_concepts(target_dir: str, date_str: str) -> bool:
    """回补概念板块：同花顺真实概念指数（限前50热门）"""
    try:
        from datetime import datetime as _dt, timedelta as _td
        start_dt = _dt.strptime(date_str, '%Y%m%d') - _td(days=4)
        start_str = start_dt.strftime('%Y%m%d')
        
        rows = []
        names = _get_ths_concept_names()[:100]
        for name in names:
            try:
                df = ak.stock_board_concept_index_ths(symbol=name, start_date=start_str, end_date=date_str)
                if df is not None and len(df) >= 2:
                    prev_close = float(df.iloc[-2]['收盘价'])
                    curr_close = float(df.iloc[-1]['收盘价'])
                    change_pct = (curr_close - prev_close) / prev_close * 100 if prev_close else 0
                    rows.append({'sector_name': name, 'change_pct': round(change_pct, 2),
                                 'up_count': 0, 'down_count': 0, 'top_stock': ''})
            except Exception:
                continue
            time.sleep(0.1)
        if rows:
            df = pd.DataFrame(rows)
            df = df.sort_values('change_pct', ascending=False).reset_index(drop=True)
            os.makedirs(target_dir, exist_ok=True)
            df.to_csv(os.path.join(target_dir, 'concept_sectors.csv'), index=False, encoding='utf-8-sig')
            with open(os.path.join(target_dir, '_backfill_date.txt'), 'w') as f:
                f.write(date_str)
            return True
    except Exception:
        pass
    return False


def _get_ths_concept_names() -> list:
    if _get_ths_concept_names._cache:
        return _get_ths_concept_names._cache
    try:
        df = ak.stock_board_concept_name_ths()
        names = df['name'].tolist() if df is not None and not df.empty else []
        _get_ths_concept_names._cache = names
        return names
    except Exception:
        return []
_get_ths_concept_names._cache = []

def _save(task: dict, data, today_dir: str):
    """保存数据到本地文件"""
    path = os.path.join(today_dir, task["filename"])
    if isinstance(data, pd.DataFrame):
        data.to_csv(path, index=False, encoding="utf-8-sig")
    elif isinstance(data, dict):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, default=str)
    elif isinstance(data, (list, str)):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, default=str)


def load_local(filename: str, date_str: str = None) -> any:
    """从本地加载数据"""
    if date_str is None:
        date_str = _today_str()

    path = os.path.join(DATA_ROOT, date_str, filename)
    if not os.path.exists(path):
        # 回退到最近的数据
        path = _find_latest_file(filename)

    if path and os.path.exists(path):
        ext = os.path.splitext(filename)[1]
        if ext == ".csv":
            df = pd.read_csv(path, encoding="utf-8-sig")
            if "date" in df.columns:
                df["date"] = pd.to_datetime(df["date"])
            return df
        elif ext == ".json":
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    return None


def _find_latest_file(filename: str) -> str:
    """查找最近日期的数据文件"""
    if not os.path.exists(DATA_ROOT):
        return None
    dirs = sorted([d for d in os.listdir(DATA_ROOT)
                   if os.path.isdir(os.path.join(DATA_ROOT, d))], reverse=True)
    for d in dirs:
        path = os.path.join(DATA_ROOT, d, filename)
        if os.path.exists(path):
            return path
    return None


def get_latest_date() -> str:
    """获取最新数据日期"""
    if not os.path.exists(DATA_ROOT):
        return ""
    dirs = sorted([d for d in os.listdir(DATA_ROOT)
                   if os.path.isdir(os.path.join(DATA_ROOT, d))], reverse=True)
    return dirs[0] if dirs else ""


def has_data_today() -> bool:
    """检查今天是否已有数据"""
    return os.path.exists(os.path.join(_today_dir(), "_meta.json"))

def save_local(data, filename: str, date_str: str = None):
    """保存数据到本地"""
    if date_str is None:
        date_str = _today_str()
    
    today_dir = os.path.join(DATA_ROOT, date_str)
    os.makedirs(today_dir, exist_ok=True)
    
    path = os.path.join(today_dir, filename)
    if isinstance(data, pd.DataFrame):
        data.to_csv(path, index=False, encoding="utf-8-sig")
    elif isinstance(data, dict):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, default=str)