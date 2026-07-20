import time
import akshare as ak

def _safe_call(fn, *args, retries=3, **kwargs):
    """带重试的调用（直接抄 stock_full_report.py）"""
    backoff = (0.5, 1.5, 3.0)
    for attempt in range(retries + 1):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            if attempt < retries and any(k in str(e) for k in ("Connection", "Timeout", "Disconnected")):
                time.sleep(backoff[min(attempt, len(backoff) - 1)])
                continue
            return None


def get_stock_fund_flow(code: str) -> dict:
    """获取个股资金流向（完全照抄 stock_full_report.py）"""
    code = str(code).zfill(6)
    market = "sh" if code.startswith("6") else "sz"
    
    df = _safe_call(ak.stock_individual_fund_flow, stock=code, market=market, retries=3)
    
    if df is not None and not df.empty:
        latest = df.iloc[-1]
        return {
            "date": str(latest.get("日期", "")),
            "main_net_inflow": float(latest.get("主力净流入", 0)) if latest.get("主力净流入") else 0,
            "super_large_net": float(latest.get("超大单净流入", 0)) if latest.get("超大单净流入") else 0,
            "large_net": float(latest.get("大单净流入", 0)) if latest.get("大单净流入") else 0,
            "mid_net": float(latest.get("中单净流入", 0)) if latest.get("中单净流入") else 0,
            "small_net": float(latest.get("小单净流入", 0)) if latest.get("小单净流入") else 0,
        }
    return {}


if __name__ == "__main__":
    code = "600176"
    print(f"测试 {code}...")
    result = get_stock_fund_flow(code)
    if result:
        print("✅ 成功:")
        for k, v in result.items():
            print(f"  {k}: {v}")
    else:
        print("❌ 失败")