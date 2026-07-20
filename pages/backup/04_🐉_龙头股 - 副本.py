"""龙头股分析"""

import streamlit as st
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ============================================================
# 抑制所有警告和调试输出
# ============================================================
import warnings
warnings.filterwarnings("ignore")
import logging
logging.getLogger("streamlit").setLevel(logging.ERROR)
os.environ["STREAMLIT_LOG_LEVEL"] = "ERROR"

import config as cfg
import data_fetcher as df_
import analyzer as anl
import visualizer as viz
from utils.helpers import fmt_cn
import pandas as pd, numpy as np

st.set_page_config(page_title="龙头股分析", page_icon="🐉", layout="wide")

#import sys as _sys
#_real_stdout, _real_stderr = _sys.stdout, _sys.stderr
#_noise_captured = []
#class _Capture:
#    def __init__(self, real):
#        self.real = real
#    def write(self, s):
#        if 'DeltaGenerator' in s or 'Delta protobuf' in s or 'root_container' in s:
#            _noise_captured.append(s)
#        else:
#            self.real.write(s)
#    def flush(self):
#        self.real.flush()
#_sys.stdout = _Capture(_real_stdout)
#_sys.stderr = _Capture(_real_stderr)



# session_state缓存
if "_dcache" not in st.session_state:
    st.session_state._dcache = {}

def _analyze(code):
    if code in st.session_state._dcache:
        return st.session_state._dcache[code]
    kdf = df_.get_stock_kline(code, days=120)
    if kdf.empty:
        st.session_state._dcache[code] = None
        return None
    kdf = anl.calc_all_indicators(kdf)
    r = {"kline": kdf, "pred": anl.predict_next_day(kdf),
         "trend": anl.classify_trend(kdf),
         "sr": anl.calc_stop_loss_take_profit(kdf, "中等")}
    st.session_state._dcache[code] = r
    return r

st.title("🐉 热门龙头股分析")

# --- 涨停板 ---
st.subheader("📋 今日涨停板")
limit_up_df = df_.get_limit_up_stocks()

if not limit_up_df.empty:
    ddf = limit_up_df.copy()
    for col in ddf.columns:
        cs = str(col).lower()
        if any(k in cs for k in ['封板时间','封板']):
            try:
                t = ddf[col].astype(str).str.replace('.0','',regex=False).str.zfill(6)
                ddf[col] = t.str[:2] + ':' + t.str[2:4] + ':' + t.str[4:6]
            except: pass
        elif any(k in cs for k in ['涨跌幅','换手率','换手']):
            try: ddf[col] = pd.to_numeric(ddf[col], errors='coerce').apply(lambda v: f'{v:+.2f}%' if pd.notna(v) else '—')
            except: pass
        elif any(k in str(col) for k in ['成交额','封板资金','流通市值','总市值']):
            try: ddf[col] = pd.to_numeric(ddf[col], errors='coerce').apply(lambda v: f'{v/1e8:.2f}亿' if abs(v)>=1e8 else (f'{v/1e4:.0f}万' if abs(v)>=1e4 else f'{v:.0f}') if pd.notna(v) else '—')
            except: pass
    st.dataframe(ddf, hide_index=True, use_container_width=True, height=400)
    st.metric("涨停家数", len(limit_up_df))

# --- 连板 ---
if not limit_up_df.empty and "连板数" in limit_up_df.columns:
    st.subheader("🔥 连板龙虎榜")
    mb = limit_up_df[limit_up_df["连板数"] > 1].sort_values("连板数", ascending=False)
    if not mb.empty:
        for _, row in mb.iterrows():
            n, c, b = row.get("名称",""), row.get("代码",""), int(row["连板数"])
            st.write(f"{'🔥'*min(b,5)} **{n}**({c}) — {b}连板")
    else:
        st.info("今日无连板股")

st.divider()

# --- 技术分析 ---
st.subheader("🔍 龙头股技术分析")
if not limit_up_df.empty and "代码" in limit_up_df.columns:
    options = [f"{r['代码']} — {r['名称']}" for _, r in limit_up_df.iterrows()]
    sel = st.selectbox("选择涨停股", options, key="ds")
    
    if sel:
        code = sel.split("—")[0].strip()
        name = sel.split("—")[1].strip()
        rt = df_.get_stock_realtime(code)
        r = _analyze(code)
        
        if r is None:
            st.warning(f"{name}({code}) 无K线数据")
        else:
            kdf, pred, trend, sr = r["kline"], r["pred"], r["trend"], r["sr"]
            
            if rt:
                c = st.columns(6)
                c[0].metric("最新价", f"{rt.get('price',0):.2f}")
                c[1].metric("涨跌幅", f"{rt.get('change_pct',0):+.2f}%")
                c[2].metric("成交额", fmt_cn(rt.get('amount',0)) or "—")
                c[3].metric("换手率", f"{rt.get('turnover',0):.2f}%" if rt.get('turnover') else "—")
                c[4].metric("PE/PB", f"{rt.get('pe',0):.1f}/{rt.get('pb',0):.1f}" if rt.get('pe') else "—")
                tm = (rt.get('time','') or '')[:5]
                c[5].metric("更新时间", tm or "—")
            
            st.plotly_chart(viz.plot_kline_with_volume(kdf, title=f"{name}({code})", height=450), use_container_width=True)
            
            tab = st.radio("指标", ["MACD","KDJ","RSI","BOLL"], horizontal=True, key="ind_tab")
            fn = {"MACD":viz.plot_macd,"KDJ":viz.plot_kdj,"RSI":viz.plot_rsi,"BOLL":viz.plot_boll}[tab]
            st.plotly_chart(fn(kdf), use_container_width=True)
            
            x = st.columns(4)
            x[0].info(f"短期: {trend.get('short_signal','—')}")
            x[1].info(f"中期: {trend.get('mid_signal','—')}")
            x[2].info(f"MACD: {trend.get('macd_signal','—')}")
            pat = anl.detect_patterns(kdf)
            x[3].warning("\n".join(pat)) if pat else x[3].info("形态: 无")
            
            st.info(f"📈 明日: **{pred.get('direction','—')}** | 置信度{pred.get('confidence',0)}% | 区间{pred.get('range','—')}")
            if sr:
                x = st.columns(2)
                x[0].error(f"止损: ¥{sr.get('stop_loss_tight','—')}")
                x[1].success(f"止盈: ¥{sr.get('take_profit_1','—')}")

st.divider()

# --- 建仓建议 ---
st.subheader("📋 明日建仓建议")
if not limit_up_df.empty and "代码" in limit_up_df.columns:
    cand = []
    for _, row in limit_up_df.iterrows():
        code = str(row["代码"]).zfill(6)
        name = row.get("名称", "")
        r = _analyze(code)
        if r is None: continue
        sc = r["pred"].get("score", 0)
        if "多头" in r["trend"].get("short_trend",""): sc += 2
        if "金叉" in r["trend"].get("macd_signal",""): sc += 1
        boards = int(row.get("连板数", 1)) if "连板数" in limit_up_df.columns else 1
        if boards >= 3: sc -= 1
        if sc <= 0: continue
        cand.append({"code":code,"name":name,"score":round(sc,1),
                     "dir":r["pred"].get("direction","—"),
                     "cf":r["pred"].get("confidence",0),
                     "b":boards,"tr":r["trend"].get("short_signal","—")})
    
    if cand:
        cand.sort(key=lambda x:x["score"], reverse=True)
        for i, c in enumerate(cand[:5]):
            em = ["🥇","🥈","🥉"][i] if i<3 else f"{i+1}."
            st.write(f"{em} **{c['name']}**({c['code']}) — {c['score']}分 | {c['dir']} | {c['tr']} | {c['b']}连板")
        b = cand[0]
        st.success(f"### 💡 建仓建议\n**{b['name']}（{b['code']}）**\n- 评分{b['score']} | {b['dir']} | 置信度{b['cf']}%\n- {b['tr']} | {b['b']}连板\n> ⚠️ 涨停次日高开，集合竞价观察，勿追高。止损:涨停价-3%")
    else:
        st.warning("无符合条件标的，建议观望")

#if _noise_captured:
#    with st.expander("⚙️ 系统调试信息", expanded=False):
#        st.code(''.join(_noise_captured[:5]), language=None)
