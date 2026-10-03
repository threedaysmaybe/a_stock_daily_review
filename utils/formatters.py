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
        if any(k in cs for k in ['日期', 'date']):
            try:
                # int（如 20260916）需先转字符串，否则 pd.to_datetime 会当成纳秒时间戳 → 1970-01-01
                s = result[col].astype(str)
                result[col] = pd.to_datetime(s, format='%Y%m%d', errors='coerce').dt.strftime('%m-%d')
            except Exception:
                pass
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


def render_merged_table(df, merge_cols=None, color_cols=None):
    """DataFrame → 带合并单元格(rowspan)的 HTML 表格。

    merge_cols: 要合并的列名列表，连续相同值用 rowspan 合并（如游资名、日期）。
    color_cols: 需要按正负上色的列（正值标红=加仓，负值标绿=减仓）。
    「状态」列含「清仓」自动标黄。
    返回 HTML 字符串，供 st.markdown(unsafe_allow_html=True) 使用。
    """
    if df is None or df.empty:
        return ""
    # 记录正负号（fmt 之前，因 fmt 会把金额转成"万/亿"字符串）
    signs = {}
    for col in (color_cols or []):
        if col in df.columns:
            try:
                nums = pd.to_numeric(df[col], errors="coerce")
                for r, v in enumerate(nums):
                    if pd.notna(v) and v != 0:
                        signs[(col, r)] = 1 if v > 0 else -1
            except Exception:
                pass

    df = fmt_dataframe(df.copy())
    merge_cols = merge_cols or []
    cols = list(df.columns)
    n = len(df)

    # 计算每个 (列, 行) 的 rowspan
    spans = {}
    for ci, col in enumerate(cols):
        if col not in merge_cols:
            continue
        i = 0
        while i < n:
            j = i + 1
            while j < n and str(df.iloc[j][col]) == str(df.iloc[i][col]):
                j += 1
            spans[(ci, i)] = j - i
            i = j

    def _paint(col, r):
        s = str(df.iloc[r][col])
        cs = str(col)
        if (col, r) in signs:
            c = "#FF6B6B" if signs[(col, r)] > 0 else "#4ADE80"
            return f'<span style="color:{c};font-weight:600">{s}</span>'
        if "状态" in cs and "清仓" in s:
            return f'<span style="color:#FBBF24;font-weight:600">{s}</span>'
        if "状态" in cs and "持仓" in s:
            return f'<span style="color:#FF6B6B;font-weight:600">{s}</span>'
        return s

    th = "border:1px solid #334155;padding:6px 10px;background:#1E293B;color:#E2E8F0;position:sticky;top:0"
    td = "border:1px solid #334155;padding:6px 10px;color:#E2E8F0;white-space:nowrap"
    tdm = f"{td};vertical-align:middle"

    html = "<table style='border-collapse:collapse;width:100%;font-size:13px;'>"
    html += "<thead><tr>" + "".join(f"<th style='{th}'>{c}</th>" for c in cols) + "</tr></thead><tbody>"
    for r in range(n):
        html += "<tr>"
        for ci, col in enumerate(cols):
            if (ci, r) in spans:
                html += f"<td rowspan='{spans[(ci, r)]}' style='{tdm}'>{_paint(col, r)}</td>"
            else:
                covered = any(cc == ci and rr < r < rr + sp for (cc, rr), sp in spans.items())
                if not covered:
                    html += f"<td style='{td}'>{_paint(col, r)}</td>"
        html += "</tr>"
    html += "</tbody></table>"
    return html
