"""
HTML研报生成器
根据股票数据生成完整HTML报告
"""

import pandas as pd
import json
from datetime import datetime
import os

def generate_html_report(code: str, name: str, data: dict) -> str:
    """
    生成HTML报告
    data: 包含所有数据的字典
    """
    
    # 提取数据
    price = data.get('price', 0)
    change_pct = data.get('change_pct', 0)
    pe = data.get('pe', 0)
    pb = data.get('pb', 0)
    total_mv = data.get('total_mv', 0)
    
    fin = data.get('financial', {})
    revenue = fin.get('revenue', 0)
    net_profit = fin.get('net_profit', 0)
    roe = fin.get('roe', 0)
    gross_margin = fin.get('gross_margin', 0)
    eps = fin.get('eps', 0)
    bps = fin.get('bps', 0)
    
    pred = data.get('prediction', {})
    direction = pred.get('direction', '—')
    confidence = pred.get('confidence', 0)
    
    sr = data.get('stop_loss_take_profit', {})
    stop_loss = sr.get('stop_loss_tight', '—')
    take_profit = sr.get('take_profit_1', '—')
    
    trend = data.get('trend', {})
    short_signal = trend.get('short_signal', '—')
    mid_signal = trend.get('mid_signal', '—')
    macd_signal = trend.get('macd_signal', '—')
    
    # 生成HTML
    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{name} {code} · 深度研报</title>
<style>
:root{{--bg:#0c0f15;--card-bg:#1a1c24;--text-primary:#e8e9ec;--text-secondary:#b0b3be;--text-muted:#7a7d8a;--red-up:#f55656;--green-down:#28c75b;--gold:#d4a853;--border:#2a2d3a;--radius:10px;}}
*{{margin:0;padding:0;box-sizing:border-box}}
body{{background:var(--bg);color:var(--text-primary);font-family:"PingFang SC","Microsoft YaHei",sans-serif;line-height:1.7;padding:20px}}
.container{{max-width:1200px;margin:0 auto}}
.card{{background:var(--card-bg);border:1px solid var(--border);border-radius:var(--radius);padding:20px 24px;margin-bottom:16px}}
.card-header{{display:flex;align-items:center;gap:10px;margin-bottom:12px;padding-bottom:10px;border-bottom:1px solid var(--border)}}
.card-header h2{{font-size:18px;color:#fff}}
.grid-2{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}
.grid-3{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px}}
.hero{{background:linear-gradient(135deg,#1c1010,#3d2424);border-radius:var(--radius);padding:24px 28px;margin-bottom:20px;border:1px solid var(--gold)}}
.hero-price{{font-size:48px;font-weight:900}}
.hero-change{{font-size:20px;font-weight:700;padding:4px 12px;border-radius:6px;background:rgba(245,86,86,0.2);color:#f87171}}
.hero-meta{{display:flex;gap:24px;margin-top:12px;flex-wrap:wrap}}
.hero-meta-item .val{{font-size:20px;font-weight:700;color:var(--gold)}}
.hero-meta-item .label{{font-size:11px;color:var(--text-muted)}}
.tag{{display:inline-block;padding:2px 12px;border-radius:12px;font-size:11px;background:rgba(212,168,83,0.15);color:var(--gold);border:1px solid var(--gold);margin:2px}}
.metric-grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:12px 0}}
.metric-item{{text-align:center;padding:12px;background:var(--bg);border-radius:8px}}
.metric-item .label{{font-size:11px;color:var(--text-muted)}}
.metric-item .value{{font-size:18px;font-weight:700;color:#fff}}
.metric-item .delta{{font-size:12px;color:var(--text-muted)}}
.metric-item .delta-up{{color:var(--red-up)}}
.metric-item .delta-down{{color:var(--green-down)}}
table{{width:100%;border-collapse:collapse;font-size:13px}}
table th{{background:#2a2d3a;color:#fff;padding:8px 12px;text-align:left}}
table td{{padding:8px 12px;border-bottom:1px solid var(--border);color:var(--text-secondary)}}
.val-up{{color:var(--red-up)}}
.val-down{{color:var(--green-down)}}
.footer{{text-align:center;padding:20px;font-size:12px;color:var(--text-muted);border-top:1px solid var(--border);margin-top:20px}}
</style>
</head>
<body>
<div class="container">

<!-- Hero -->
<div class="hero">
<div>
<span class="hero-price">{price:.2f}</span>
<span class="hero-change">{change_pct:+.2f}%</span>
</div>
<div class="hero-meta">
<div class="hero-meta-item"><div class="val">{datetime.now().strftime("%Y-%m-%d")}</div><div class="label">分析日期</div></div>
<div class="hero-meta-item"><div class="val">{pe:.1f}/{pb:.1f}</div><div class="label">PE/PB</div></div>
<div class="hero-meta-item"><div class="val">{total_mv/1e8:.1f}亿</div><div class="label">总市值</div></div>
<div class="hero-meta-item"><div class="val">{direction}</div><div class="label">预测方向</div></div>
</div>
<div style="margin-top:10px">
<span class="tag">{name}</span>
<span class="tag">{code}</span>
<span class="tag">{short_signal}</span>
</div>
</div>

<!-- 结论卡片 -->
<div class="card">
<div class="card-header"><h2>📊 核心结论</h2></div>
<div class="metric-grid">
<div class="metric-item"><div class="label">当前价</div><div class="value">{price:.2f}</div><div class="delta {'delta-up' if change_pct>=0 else 'delta-down'}">{change_pct:+.2f}%</div></div>
<div class="metric-item"><div class="label">预测方向</div><div class="value">{direction}</div><div class="delta">置信度 {confidence}%</div></div>
<div class="metric-item"><div class="label">短期趋势</div><div class="value">{short_signal}</div></div>
<div class="metric-item"><div class="label">中期趋势</div><div class="value">{mid_signal}</div></div>
</div>
<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-top:12px">
<div style="text-align:center;padding:8px;background:var(--bg);border-radius:6px"><div style="font-size:11px;color:var(--text-muted)">止损</div><div style="font-weight:700;color:var(--green-down)">¥{stop_loss}</div></div>
<div style="text-align:center;padding:8px;background:var(--bg);border-radius:6px"><div style="font-size:11px;color:var(--text-muted)">止盈</div><div style="font-weight:700;color:var(--red-up)">¥{take_profit}</div></div>
<div style="text-align:center;padding:8px;background:var(--bg);border-radius:6px"><div style="font-size:11px;color:var(--text-muted)">MACD</div><div style="font-weight:700;color:var(--gold)">{macd_signal}</div></div>
<div style="text-align:center;padding:8px;background:var(--bg);border-radius:6px"><div style="font-size:11px;color:var(--text-muted)">ROE</div><div style="font-weight:700;color:var(--gold)">{roe:.2f}%</div></div>
</div>
</div>

<!-- 财务数据 -->
<div class="card">
<div class="card-header"><h2>📋 财务数据</h2></div>
<div class="grid-2">
<div>
<table>
<tr><th>指标</th><th>数值</th></tr>
<tr><td>营业总收入</td><td>{revenue/1e8:.2f}亿</td></tr>
<tr><td>净利润</td><td>{net_profit/1e8:.2f}亿</td></tr>
<tr><td>ROE</td><td>{roe:.2f}%</td></tr>
<tr><td>毛利率</td><td>{gross_margin:.2f}%</td></tr>
</table>
</div>
<div>
<table>
<tr><th>指标</th><th>数值</th></tr>
<tr><td>每股收益(EPS)</td><td>{eps:.4f}</td></tr>
<tr><td>每股净资产(BPS)</td><td>{bps:.2f}</td></tr>
<tr><td>市盈率(PE)</td><td>{pe:.1f}</td></tr>
<tr><td>市净率(PB)</td><td>{pb:.2f}</td></tr>
</table>
</div>
</div>
</div>

<!-- 页脚 -->
<div class="footer">
<p>⚠️ 以上分析仅供研究参考，不构成投资建议。市场有风险，投资需谨慎。</p>
<p>📅 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
<p style="font-size:11px;color:var(--text-muted);">数据来源：akshare / 同花顺 / 东方财富</p>
</div>

</div>
</body>
</html>'''
    
    return html


def save_report(code: str, name: str, html_content: str) -> str:
    """保存HTML报告到本地"""
    output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
    os.makedirs(output_dir, exist_ok=True)
    
    filename = f"个股研究-{name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
    filepath = os.path.join(output_dir, filename)
    
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html_content)
    
    return filepath