import pandas as pd

def auto_fmt_cn(val):
    if val is None or (isinstance(val, float) and pd.isna(val)): return "—"
    try: n = float(val)
    except: return str(val)
    if abs(n) >= 1e8: return f"{n/1e8:.2f}亿"
    elif abs(n) >= 1e4: return f"{n/1e4:.0f}万"
    elif abs(n) >= 1000: return f"{n:,.0f}"
    return f"{n:.2f}"

def fmt_dataframe(df):
    if df is None or df.empty: return df
    result = df.copy()
    money_kw = ['金额','成交','买入','卖出','净额','净买','市值','收入','利润','资产','成交额','流入','流出']
    skip_kw  = ['代码','code','名称','name','序号','数量','count','次数','PE','PB','pe','pb','连板','封板']
    
    for col in result.columns:
        cs = str(col).lower()
        if any(k in cs for k in skip_kw): continue
        
        # 时间列
        if any(k in cs for k in ['时间','time']):
            try: result[col] = pd.to_datetime(result[col], errors='coerce').dt.strftime('%H:%M')
            except: pass
            continue
        
        # 日期列
        if any(k in cs for k in ['日期','date']):
            try: result[col] = pd.to_datetime(result[col], errors='coerce').dt.strftime('%m-%d')
            except: pass
            continue
        
        # 涨跌幅/换手率 → +X.XX%
        if any(k in cs for k in ['涨跌幅','change','pct','涨跌','换手','比例']):
            try:
                result[col] = pd.to_numeric(result[col], errors='coerce').apply(
                    lambda v: f"{v:+.2f}%" if pd.notna(v) else "—")
            except: pass
            continue
        
        # 金额
        if any(k in str(col) for k in money_kw):
            try: result[col] = pd.to_numeric(result[col], errors='coerce').apply(auto_fmt_cn)
            except: pass
    
    return result
