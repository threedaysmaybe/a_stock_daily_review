"""生成个股深度研究HTML报告"""

import streamlit as st
import sys, os, json, io
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config as cfg
import data_fetcher as df_
import analyzer as anl
import visualizer as viz
from utils.helpers import fmt_cn
import pandas as pd, numpy as np
from datetime import datetime

st.set_page_config(page_title="生成报告", page_icon="📄", layout="wide")

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

st.title("📄 生成个股深度研究报告")

# ============================================================
# Step 1: 选择股票
# ============================================================
st.subheader("🔍 选择分析标的")

col1, col2 = st.columns([3, 1])
with col1:
    search = st.text_input("输入股票代码", placeholder="如 600519", key="rpt_code")
with col2:
    st.write("")
    if st.button("🔍 查找", use_container_width=True):
        pass

if search:
    code = str(search).strip().zfill(6)
    if len(code) == 6 and code.isdigit():
        # 获取名称
        rt = df_.get_stock_realtime(code)
        name = rt.get("name", code) if rt else code
        
        st.info(f"📌 **{name}**（{code}）")
        
        if st.button("🚀 生成HTML报告", use_container_width=True, type="primary"):
            with st.spinner(f"正在生成 {name} 深度研究报告..."):
                status = st.empty()
                
                # 1. 获取数据
                status.text("📊 获取K线数据...")
                kdf = df_.get_stock_kline(code, days=250)
                if kdf.empty:
                    st.error("无法获取K线数据")
                    st.stop()
                kdf = anl.calc_all_indicators(kdf)
                
                # 2. 分析
                status.text("🔍 分析技术指标...")
                pred = anl.predict_next_day(kdf)
                trend = anl.classify_trend(kdf)
                patterns = anl.detect_patterns(kdf)
                sl_tp = anl.calc_stop_loss_take_profit(kdf)
                sr = trend.get("sr_levels", {})
                
                # 3. 财务数据
                status.text("📋 获取基本面...")
                fin = df_.get_stock_financial(code)
                rt = df_.get_stock_realtime(code)
                
                # 4. 生成图表
                status.text("📈 生成K线图...")
                fig_kline = viz.plot_kline_with_volume(kdf.tail(120), title=f"{name} K线图", height=500)
                kline_html = fig_kline.to_html(full_html=False, include_plotlyjs=False)
                
                fig_macd = viz.plot_macd(kdf.tail(120))
                macd_html = fig_macd.to_html(full_html=False, include_plotlyjs=False)
                
                fig_kdj = viz.plot_kdj(kdf.tail(120))
                kdj_html = fig_kdj.to_html(full_html=False, include_plotlyjs=False)
                
                fig_rsi = viz.plot_rsi(kdf.tail(120))
                rsi_html = fig_rsi.to_html(full_html=False, include_plotlyjs=False)
                
                fig_boll = viz.plot_boll(kdf.tail(120))
                boll_html = fig_boll.to_html(full_html=False, include_plotlyjs=False)
                
                # 5. 拼接HTML
                status.text("📄 生成报告...")
                price = rt.get("price", kdf["close"].iloc[-1]) if rt else kdf["close"].iloc[-1]
                pct = rt.get("change_pct", 0) if rt else 0
                pe = rt.get("pe", 0) if rt else 0
                pb = rt.get("pb", 0) if rt else 0
                mv = rt.get("total_mv", 0) if rt else 0
                
                up_class = "up" if pct >= 0 else "down"
                sign = "+" if pct >= 0 else ""
                
                # 财务
                roe = fin.get("roe", "—") if fin else "—"
                gross = fin.get("gross_margin", "—") if fin else "—"
                rev = fmt_cn(fin.get("revenue", 0)) if fin else "—"
                profit = fmt_cn(fin.get("net_profit", 0)) if fin else "—"
                
                # 支撑阻力
                supports_html = ""
                for s in sr.get("supports", [])[:3]:
                    supports_html += f'<div class="sr-item"><span class="sr-label green">🟢 {s["label"]}</span><span>¥{s["price"]}</span></div>'
                resistances_html = ""
                for r in sr.get("resistances", [])[:3]:
                    resistances_html += f'<div class="sr-item"><span class="sr-label red">🔴 {r["label"]}</span><span>¥{r["price"]}</span></div>'
                
                # 形态
                patterns_html = "".join(f'<li>{p}</li>' for p in patterns) if patterns else "<li>无明显形态</li>"
                
                # 预测
                pred_color = "#DC143C" if "看涨" in pred.get("direction", "") or "偏强" in pred.get("direction", "") else ("#228B22" if "看跌" in pred.get("direction", "") else "#FFD700")
                
                html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>个股研究-{name}</title>
<script src="https://cdn.plot.ly/plotly-2.32.0.min.js"></script>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:"Microsoft YaHei",sans-serif;background:#0F172A;color:#F1F5F9;padding:20px;max-width:1100px;margin:0 auto}}
h1{{font-size:24px;color:#FFD700;margin-bottom:4px}}
h2{{font-size:18px;color:#F1F5F9;border-bottom:1px solid #334155;padding-bottom:8px;margin:24px 0 12px}}
h3{{font-size:14px;color:#94A3B8;margin:12px 0 6px}}
.subtitle{{color:#94A3B8;font-size:13px;margin-bottom:16px}}
.card{{background:#1E293B;border:1px solid #334155;border-radius:10px;padding:16px 20px;margin-bottom:14px}}
.hero{{background:linear-gradient(105deg,#1a1a2e,#16213e);border:1px solid #FFD700;border-radius:12px;padding:20px 24px;margin-bottom:14px}}
.hero-price{{font-size:36px;font-weight:700}}
.hero-change{{font-size:18px;font-weight:600;margin-left:16px}}
.up{{color:#DC143C}}.down{{color:#228B22}}
.meta{{display:flex;gap:24px;margin-top:12px;flex-wrap:wrap}}
.meta-item .lbl{{font-size:10px;color:#94A3B8}}.meta-item .val{{font-size:14px;font-weight:600;color:#F0D68A}}
.grid2{{display:grid;grid-template-columns:1fr 1fr;gap:14px}}
.grid3{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px}}
.tag{{display:inline-block;padding:2px 8px;border-radius:4px;font-size:11px;border:1px solid;margin:2px 4px 2px 0}}
.tag-gold{{color:#D4A853;border-color:#D4A853;background:rgba(212,168,83,0.1)}}
.tag-red{{color:#DC143C;border-color:#DC143C;background:rgba(220,20,60,0.1)}}
.tag-green{{color:#228B22;border-color:#228B22;background:rgba(34,139,34,0.1)}}
.score-bar{{height:6px;background:#334155;border-radius:3px;margin:4px 0}}
.score-fill{{height:100%;border-radius:3px;background:#D4A853}}
table{{width:100%;border-collapse:collapse;font-size:12px}}
th{{background:#16213e;padding:8px;text-align:left;color:#94A3B8;border-bottom:2px solid #334155}}
td{{padding:6px 8px;border-bottom:1px solid #1e293b}}
.kpi{{text-align:center;padding:12px}}
.kpi-val{{font-size:22px;font-weight:700;color:#F0D68A}}
.kpi-lbl{{font-size:11px;color:#94A3B8}}
.sr-item{{display:flex;justify-content:space-between;padding:4px 0;font-size:13px}}
.sr-label{{font-weight:600}}.green{{color:#228B22}}.red{{color:#DC143C}}
.pred-box{{background:rgba(255,255,255,0.03);border-left:4px solid {pred_color};padding:12px 16px;border-radius:0 8px 8px 0;margin:8px 0}}
.pred-dir{{font-size:20px;font-weight:700;color:{pred_color}}}
.verdict{{background:rgba(255,215,0,0.05);border-left:4px solid #D4A853;padding:16px;border-radius:0 8px 8px 0;margin:12px 0}}
.footer{{text-align:center;color:#94A3B8;font-size:10px;padding:30px 0 10px}}
</style>
</head>
<body>

<div class="hero">
  <h1>{name}</h1>
  <div class="subtitle">{code} | {datetime.now().strftime("%Y-%m-%d")}</div>
  <div style="display:flex;align-items:baseline">
    <span class="hero-price">¥{price:.2f}</span>
    <span class="hero-change {up_class}">{sign}{pct:.2f}%</span>
  </div>
  <div class="meta">
    <div class="meta-item"><div class="lbl">公司质地</div><div class="val">{'优秀' if (fin and fin.get('roe',0) and fin['roe']>15) else '良好' if (fin and fin.get('roe',0) and fin['roe']>8) else '一般'}</div></div>
    <div class="meta-item"><div class="lbl">总市值</div><div class="val">{fmt_cn(mv)}</div></div>
    <div class="meta-item"><div class="lbl">动态PE/PB</div><div class="val">{pe:.1f}/{pb:.1f}</div></div>
    <div class="meta-item"><div class="lbl">预测方向</div><div class="val" style="color:{pred_color}">{pred.get('direction','—')}</div></div>
    <div class="meta-item"><div class="lbl">风险等级</div><div class="val">{'中低' if pred.get('score',0)>2 else '中高'}</div></div>
  </div>
  <div style="margin-top:10px">
    <span class="tag tag-gold">A股</span>
    <span class="tag tag-{'red' if pct>=0 else 'green'}">{sign}{pct:.2f}%</span>
  </div>
</div>

<h2>📊 基本面概览</h2>
<div class="card">
  <div class="grid3">
    <div class="kpi"><div class="kpi-val">{roe}</div><div class="kpi-lbl">ROE (%)</div></div>
    <div class="kpi"><div class="kpi-val">{gross}</div><div class="kpi-lbl">毛利率 (%)</div></div>
    <div class="kpi"><div class="kpi-val">{rev}</div><div class="kpi-lbl">营业收入</div></div>
    <div class="kpi"><div class="kpi-val">{profit}</div><div class="kpi-lbl">净利润</div></div>
    <div class="kpi"><div class="kpi-val">{pe:.1f}</div><div class="kpi-lbl">动态PE</div></div>
    <div class="kpi"><div class="kpi-val">{pb:.1f}</div><div class="kpi-lbl">市净率</div></div>
  </div>
</div>

<h2>📈 K线分析</h2>
<div class="card">
  {kline_html}
</div>

<h2>🔍 技术指标</h2>
<div class="card">
  <div class="grid2">
    {macd_html}
    {kdj_html}
  </div>
  <div class="grid2" style="margin-top:14px">
    {rsi_html}
    {boll_html}
  </div>
</div>

<h2>📍 支撑与阻力</h2>
<div class="card">
  <div class="grid2">
    <div><h3>🟢 支撑位</h3>{supports_html or '<p style="color:#94A3B8">暂无</p>'}</div>
    <div><h3>🔴 压力位</h3>{resistances_html or '<p style="color:#94A3B8">暂无</p>'}</div>
  </div>
</div>

<h2>📋 趋势研判</h2>
<div class="card">
  <div class="grid3">
    <div class="kpi"><div class="kpi-val">{trend.get('short_signal','—')}</div><div class="kpi-lbl">短期趋势</div></div>
    <div class="kpi"><div class="kpi-val">{trend.get('mid_signal','—')}</div><div class="kpi-lbl">中期趋势</div></div>
    <div class="kpi"><div class="kpi-val">{trend.get('macd_signal','—')}</div><div class="kpi-lbl">MACD信号</div></div>
  </div>
  <h3>K线形态识别</h3>
  <ul style="font-size:13px;color:#94A3B8;padding-left:20px">{patterns_html}</ul>
</div>

<h2>🔮 明日预测</h2>
<div class="pred-box">
  <span class="pred-dir">{pred.get('direction','—')}</span>
  <span style="color:#94A3B8;margin-left:12px">置信度: {pred.get('confidence',0)}%</span>
  <span style="color:#94A3B8;margin-left:12px">波动区间: {pred.get('range','—')}</span>
</div>
<div style="margin-top:8px">
  {'<br>'.join(f'• {r}' for r in pred.get('reasons',[])) if pred.get('reasons') else ''}
</div>

<h2>🎯 止盈止损</h2>
<div class="card">
  <div class="grid3">
    <div class="kpi"><div class="kpi-val" style="color:#228B22">¥{sl_tp.get('stop_loss_tight','—') if sl_tp else '—'}</div><div class="kpi-lbl">🛑 止损位</div></div>
    <div class="kpi"><div class="kpi-val" style="color:#DC143C">¥{sl_tp.get('take_profit_1','—') if sl_tp else '—'}</div><div class="kpi-lbl">🎯 止盈位</div></div>
    <div class="kpi"><div class="kpi-val">{sl_tp.get('suggested_position','—') if sl_tp else '—'}</div><div class="kpi-lbl">💼 建议仓位</div></div>
  </div>
</div>

<div class="verdict">
  <h3 style="color:#D4A853;margin-bottom:8px">📌 综合结论</h3>
  <p style="font-size:14px;line-height:1.6">
    基于技术面分析，{name}（{code}）当前处于<strong>{trend.get('short_trend','震荡')}</strong>格局。
    明日预测<strong style="color:{pred_color}">{pred.get('direction','—')}</strong>。
    建议仓位<strong>{sl_tp.get('suggested_position','—') if sl_tp else '待定'}</strong>，止损设在¥{sl_tp.get('stop_loss_tight','—') if sl_tp else '—'}。
  </p>
</div>

<div class="footer">
  <p>免责声明：本报告由AI自动生成，仅供研究参考，不构成投资建议。</p>
  <p>数据来源：akshare / 东方财富 | 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
</div>

</body></html>'''
                
                # 保存
                fname = f"个股研究-{name}.html"
                fpath = os.path.join(OUTPUT_DIR, fname)
                with open(fpath, "w", encoding="utf-8") as f:
                    f.write(html)
                
                status.text("✅ 报告生成完成！")
                st.success(f"报告已保存至: `{fpath}`")
                st.info(f"文件大小: {os.path.getsize(fpath)/1024:.0f} KB")
                
                # 预览按钮
                st.markdown(f'<a href="file:///{fpath}" target="_blank" style="display:inline-block;padding:8px 16px;background:#D4A853;color:#0F172A;border-radius:6px;text-decoration:none;font-weight:600">📄 打开报告</a>', unsafe_allow_html=True)
    else:
        st.error("请输入6位数字代码")

# ============================================================
# 已生成报告列表
# ============================================================
st.divider()
st.subheader("📚 已生成报告")
reports = sorted([f for f in os.listdir(OUTPUT_DIR) if f.endswith(".html")], reverse=True)
if reports:
    for r in reports:
        fpath = os.path.join(OUTPUT_DIR, r)
        size_kb = os.path.getsize(fpath) / 1024
        st.write(f"📄 {r} ({size_kb:.0f} KB)")
else:
    st.info("暂无报告，请在上方生成")
