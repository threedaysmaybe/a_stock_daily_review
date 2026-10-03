"""
个股研报 v4 — 读 stock_data_collect.py JSON，CSS 对齐 stock-analysis，标签+盈亏比完整
"""
import json, os, sys
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

CSS = '''<style>
:root{--bg:#0c0f15;--card-bg:#1a1c24;--card-bg-alt:#1e2029;--border:#2a2d3a;--text-primary:#e8e9ec;--text-secondary:#b0b3be;--text-muted:#7a7d8a;--red-up:#f55656;--green-down:#28c75b;--gold:#d4a853;--gold-light:#e3c26d;--orange-warn:#e8923a;--radius:10px;--font-sans:"PingFang SC","Microsoft YaHei",sans-serif;--font-mono:"JetBrains Mono","SF Mono","Consolas",monospace}
body.light-mode{--bg:#fdf8f0;--card-bg:#fffbf5;--card-bg-alt:#fef5e7;--border:#e2cfa2;--text-primary:#2a1f12;--text-secondary:#6b5634;--text-muted:#9c8b6e;--red-up:#dc2626;--green-down:#16a34a;--gold:#b38a3c;--gold-light:#d4a853}
*{margin:0;padding:0;box-sizing:border-box}
body{background:var(--bg);color:var(--text-primary);font:14px/1.7 var(--font-sans);max-width:1200px;margin:0 auto;padding:20px}
.top-nav{position:sticky;top:0;z-index:99;background:rgba(10,12,18,.92);backdrop-filter:blur(12px);border-bottom:2px solid var(--gold-light);padding:10px 28px;margin:-20px -20px 20px;display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap}
.top-nav .logo{display:flex;align-items:center;gap:10px;color:#fff}
.top-nav .logo-icon{width:34px;height:34px;background:linear-gradient(135deg,#c0392b,#8b0000);border-radius:8px;display:flex;align-items:center;justify-content:center;font-weight:900;font-size:18px;color:#fff}
.top-nav .stock-name{font-weight:700;font-size:17px}
.top-nav .stock-code{font-size:12px;opacity:.7;font-family:var(--font-mono)}
.nav-links{display:flex;gap:8px;flex-wrap:wrap}
.nav-links a{font-size:12px;padding:5px 14px;border-radius:16px;color:var(--gold-light);text-decoration:none;border:1px solid transparent;font-weight:500}
.tag{display:inline-block;padding:3px 12px;border-radius:14px;font-size:11px;font-weight:600;background:rgba(212,168,83,.15);color:var(--gold-light);border:1px solid var(--gold);margin-right:6px}
.nav-links a:hover{background:rgba(255,255,255,.08);color:#fff;border-color:var(--gold)}
.theme-toggle{background:rgba(255,255,255,.08);border:1px solid var(--gold-light);color:var(--gold-light);padding:5px 14px;border-radius:16px;font-size:12px;cursor:pointer}
.hero{background:linear-gradient(105deg,#1c1010,#2c1a1a 50%,#3d2424);border-radius:var(--radius);padding:28px 32px;margin-bottom:24px;border:1px solid var(--gold-light);display:flex;flex-wrap:wrap;gap:24px;align-items:center;color:#fff;position:relative;overflow:hidden}
.hero-price-block{display:flex;align-items:baseline;gap:12px;z-index:1}
.hero-price{font-size:56px;font-weight:900;line-height:1;font-family:var(--font-mono)}
.hero-change{font-size:20px;font-weight:700;padding:4px 12px;border-radius:6px;font-family:var(--font-mono)}
.hero-change.up{background:rgba(245,86,86,.2);color:#f87171}
.hero-change.dn{background:rgba(40,199,91,.2);color:#4ade80}
.hero-meta{display:flex;gap:28px;flex-wrap:wrap;z-index:1}
.hero-meta-item{text-align:center}
.hero-meta-item .val{font-size:22px;font-weight:700;font-family:var(--font-mono);color:var(--gold-light)}
.hero-meta-item .label{font-size:11px;color:rgba(255,255,255,.7)}
.hero-tags{display:flex;gap:8px;flex-wrap:wrap;z-index:1;width:100%}
.hero-tag{background:rgba(255,255,255,.08);border:1px solid rgba(255,215,0,.3);color:var(--gold-light);padding:5px 14px;border-radius:20px;font-size:12px}
.conclusion-top{background:linear-gradient(135deg,#1e1a10,#241f14);border:2px solid var(--gold);border-radius:var(--radius);padding:22px 28px;margin-bottom:24px;position:relative}
.conclusion-top::before{content:'核心结论';position:absolute;top:-13px;left:24px;background:var(--gold);color:#000;padding:3px 16px;border-radius:12px;font-weight:700;font-size:12px}
.conclusion-top .big-verdict{font-weight:800;font-size:20px;color:#fff;margin-top:8px}
.conclusion-top .verdict-tags{display:flex;gap:12px;flex-wrap:wrap;margin-top:12px}
.conclusion-top .verdict-detail{font-size:14px;color:var(--text-secondary);margin-top:8px;line-height:1.7}
.card{background:var(--card-bg);border:1px solid var(--border);border-radius:var(--radius);padding:22px 28px;margin-bottom:20px}
.card-header{display:flex;align-items:center;gap:10px;margin-bottom:16px;padding-bottom:12px;border-bottom:2px solid var(--border)}
.card-header .icon{width:32px;height:32px;border-radius:8px;background:rgba(255,255,255,.05);display:flex;align-items:center;justify-content:center;font-weight:700;color:var(--gold)}
.card-header h2{font-size:18px;font-weight:700;color:#fff}
.grid-2{display:grid;grid-template-columns:1fr 1fr;gap:20px}
.val-up{color:var(--red-up);font-weight:600}
.val-dn{color:var(--green-down);font-weight:600}
.info-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px 20px;font-size:13px}
.info-grid dt{color:var(--text-muted)}.info-grid dd{color:var(--text-secondary)}
table.cns{width:100%;border-collapse:collapse;font-size:13px;background:var(--card-bg-alt);border:1px solid var(--border);border-radius:8px;overflow:hidden;margin:12px 0}
table.cns thead th{background:linear-gradient(180deg,#2c1a1a,#1c1010);color:#fff;padding:10px 12px;text-align:left;font-size:12px}
table.cns td{padding:9px 12px;border-bottom:1px dashed var(--border);color:var(--text-secondary)}
.rating{background:linear-gradient(135deg,#1e1a10,#241f14);border:2px solid var(--gold);border-radius:var(--radius);padding:18px 24px;margin-top:16px;display:flex;align-items:center;gap:16px}
.rating .badge{min-width:64px;height:64px;border-radius:50%;background:var(--gold);color:#000;display:flex;align-items:center;justify-content:center;font-size:26px;font-weight:900}
.rating .body .title{font-size:16px;font-weight:700;color:#fff}
.rating .body .desc{font-size:12px;color:var(--text-secondary);margin-top:4px}
.alert-list{list-style:none;padding:0}
.alert-list li{padding:8px 14px;margin:6px 0;border-radius:6px;background:var(--card-bg-alt);border-left:4px solid var(--orange-warn);font-size:13px;color:var(--text-secondary)}
.chain-svg{background:var(--card-bg-alt);border:1px solid var(--border);border-radius:var(--radius);padding:16px;margin:16px 0;text-align:center}
.chain-svg .svg-hdr{fill:var(--text-primary)}
.chain-svg .svg-sub{fill:var(--text-secondary)}
footer{text-align:center;padding:24px;font-size:12px;color:var(--text-muted);border-top:1px solid var(--border);margin-top:24px}
</style>
<script>function toggleTheme(){var b=document.documentElement;b.classList.toggle('light-mode');document.getElementById('tb').textContent=b.classList.contains('light-mode')?'🌙深色':'☀浅色'}</script>'''

NAV = '<a href="#hero">行情</a><a href="#conclusion-top">结论</a><a href="#profile">画像</a><a href="#kline-section">K线</a><a href="#mission">任务</a><a href="#macro">宏观</a><a href="#chain">产业链</a><a href="#quality">质量</a><a href="#elasticity">弹性</a><a href="#risk">风险</a><a href="#valuation">估值</a><a href="#compare">对标</a><a href="#tracking">跟踪</a><a href="#technical">技术面</a>'

def _n(v, d=0):
    try: return float(v) if v is not None else d
    except: return d

def _s(v, d='—'):
    return str(v) if v else d

def _fix_keys(d):
    """修复 JSON 键名两端多余引号"""
    if not isinstance(d, dict): return d
    for k in list(d.keys()):
        v = d.pop(k)
        nk = k.strip("'\"").strip()
        d[nk] = _fix_keys(v) if isinstance(v, dict) else v
    return d


def generate_report(code, name, json_path=None):
    if json_path is None:
        json_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output", f"data_{code}.json")
    if not os.path.exists(json_path):
        return f"<p>JSON 缺失: {json_path}</p>"

    with open(json_path, 'r', encoding='utf-8') as f:
        j = json.load(f)
    b = j.get('blocks', {})


    # === 行情 ===
    sp = (b.get('spot') or [{}])[0]
    price = _n(sp.get('最新价', sp.get('close')))
    chg = _n(sp.get('涨跌幅'))
    pe = _n(sp.get('市盈率-动态'))
    pb = _n(sp.get('市净率'))
    mv = _n(sp.get('总市值'))

    # === 财务指标 ===
    fi = b.get('fin_indicator_ths', [])
    lf = fi[-1] if fi else {}
    roe = _n(lf.get('净资产收益率'))
    gm = _n(lf.get('销售毛利率'))
    rev = _n(lf.get('营业总收入'))
    npr = _n(lf.get('净利润'))
    eps = _n(lf.get('基本每股收益'))
    bps = _n(lf.get('每股净资产'))

    # === AI 分析文件 ===
    ai = None; ai0 = None; ai1 = None; ai4 = None
    try:
        import importlib.util
        analysis_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), f'stock_{code}_analysis.py')
        if os.path.exists(analysis_file):
            spec = importlib.util.spec_from_file_location(f'analysis_{code}', analysis_file)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            ai = mod.ANALYSIS.get('step2', {})
            ai0 = mod.ANALYSIS.get('step0', {})
            ai1 = mod.ANALYSIS.get('step1', {})
            ai4 = mod.ANALYSIS.get('step4', {})
    except: pass
    
    # === K线 + 技术分析 ===
    import pandas as pd, analyzer as anl
    kl = b.get('kline_daily', [])
    supports, resistances = [], []
    st_t = '—'; mt_t = '—'; macd = '—'
    if kl:
        try:
            kdf = pd.DataFrame(kl)
            if 'date' in kdf.columns: kdf['date'] = pd.to_datetime(kdf['date'])
            kdf_i = anl.calc_all_indicators(kdf)
            ti = anl.classify_trend(kdf_i)
            sr_lv = ti.get('sr_levels', {})
            supports = sr_lv.get('supports', [])
            resistances = sr_lv.get('resistances', [])
            st_t = ti.get('short_trend') or '—'
            mt_t = ti.get('mid_trend') or '—'
            macd = ti.get('macd_signal') or '—'
        except: pass

    # === 标签（主营业务） ===
    zyg = b.get('zygc', [])
    tags = []
    seen = set()
    max_d = ''
    for r in zyg:
        d = str(r.get('报告日期', r.get('报告期', '')))[:10]
        if d > max_d: max_d = d
    for r in zyg:
        d = str(r.get('报告日期', r.get('报告期', '')))[:10]
        if d != max_d: continue
        biz = str(r.get('经营项目', r.get('项目名称', r.get('主营构成', ''))))
        if biz and biz not in seen and len(biz) > 2 and ':' not in biz and '收入' not in biz:
            tags.append(biz); seen.add(biz)
        if len(tags) >= 3: break
        # AI标签优先，规则兜底
    if ai and ai.get('tags'):
        all_tags = ai['tags']
        # 补充数据驱动标签
        try:
            if kdf is not None and not kdf.empty and len(kdf) >= 5:
                recent = kdf.tail(5)
                avg_amp = recent.apply(lambda x: (x['high']-x['low'])/x['close']*100, axis=1).mean()
                if avg_amp > 5: all_tags.append('高波动')
        except: pass
        try:
            if kdf is not None and not kdf.empty and len(kdf) >= 20:
                r20 = kdf.tail(20)
                if ((r20['close'] - r20['open']) / r20['open'] * 100 < -9.5).any(): all_tags.append('跌停日')
        except: pass
    else:
        anl_tags = []
        if any('玻' in t or '纤维' in t for t in tags): anl_tags.append('玻纤龙头')
        if any('电子布' in t or '电子' in t for t in tags): anl_tags.append('电子布')
        all_tags = tags + anl_tags
    tags_html = ''.join(f'<span class="hero-tag">{t[:12]}</span>' for t in all_tags)

    # === 盈亏比 ===
    sl_v = supports[0]['price'] if supports else '—'
    tp1 = resistances[0]['price'] if resistances else '—'
    tp2 = resistances[1]['price'] if len(resistances) > 1 else '—'
    buy_r, rr = '—', '—'
    if sl_v != '—' and tp1 != '—' and price > 0:
        try:
            buy_r = f'{float(sl_v)*1.05:.0f}-{float(tp1):.0f}元'
            r = (float(tp1) - price) / (price - float(sl_v))
            rr = f'{r:.1f}x' if r > 0 else '—'
        except: pass

    # === PE分位目标价 ===
    ttm, pettm = 0, 0
    if len(fi) >= 4:
        qeps, pv = [], 0
        for r in fi[-5:]:
            v = _n(r.get('基本每股收益'))
            if v < pv*0.9 and qeps: qeps[-1]=v; pv=v
            elif not qeps: qeps.append(v); pv=v
            else: qeps.append(v-pv); pv=v
        if len(qeps) >= 4:
            ttm = sum(qeps[-4:])
            pettm = round(price/ttm, 1) if ttm > 0 else 0
    tl = f'{20*ttm:.1f}' if ttm > 0 else '—'
    tm = f'{25*ttm:.1f}' if ttm > 0 else '—'
    th = f'{30*ttm:.1f}' if ttm > 0 else '—'
    tp = f'{tl}-{th}元' if ttm > 0 else '—'

    # === 评分 ===
    sc = 50
    if roe > 20: sc += 10
    elif roe > 10: sc += 5
    elif roe <= 5: sc -= 5
    if gm > 50: sc += 8
    elif gm > 30: sc += 4
    if '多头' in str(st_t): sc += 10
    elif '空头' in str(st_t): sc -= 10
    if '多头' in str(mt_t): sc += 10
    elif '空头' in str(mt_t): sc -= 5
    if '金叉' in str(macd): sc += 8
    elif '死叉' in str(macd): sc -= 8
    sc = max(0, min(100, sc))
    gd = 'A' if sc >= 80 else ('B' if sc >= 60 else ('C' if sc >= 40 else 'D'))
    sd = f'{sc}分({gd}级)'

    risk_lv = '⚠低' if sc >= 70 else ('⚠中' if sc >= 50 else '⚠高')
    risk_c = 'var(--green-down)' if sc >= 70 else ('var(--gold)' if sc >= 50 else 'var(--red-up)')

    if sc >= 70: vd = f'📈偏多——短{st_t}中{mt_t}'
    elif sc >= 50: vd = f'📊中性——短{st_t}中{mt_t}'
    elif sc >= 30: vd = f'⚠谨慎——短{st_t}中{mt_t}'
    else: vd = f'📉规避——短{st_t}中{mt_t}'

    if sc >= 60: adv = '可逢回调关注，严格止损。'
    elif sc >= 40: adv = '轻仓试探。'
    else: adv = '观望，等待右侧信号。'

    # 目标价字符串（用于KPI行）
    tp_val_str = tp
    
    # AI 分析覆盖
    verdict_detail = ""
    if ai:
        sc = ai.get('score', sc)
        gd = ai.get('grade', gd)
        sd = f'{sc}分({gd}级)'
        vd = ai.get('verdict', vd)
        adv = ai.get('advice', adv)
        risk_lv = ai.get('risk', risk_lv)
        buy_r = ai.get('buy_range', buy_r)
        sl_v = ai.get('stop_loss', sl_v)
        tp = ai.get('target', tp)
        rr = ai.get('rr', rr)
        tp1 = ai.get('target', tp1)
        tp2 = '—'
        verdict_detail = ai.get('verdict_detail', '')
        if ai.get('risks'): rs = ai['risks']
        if ai.get('score_display'): sd = ai['score_display']

    uc = 'dn' if chg < 0 else 'up'
    dt = datetime.now().strftime('%Y-%m-%d')
    fs = f'营收{rev/1e8:.1f}亿 净利{npr/1e8:.1f}亿 ROE{roe:.1f}% 毛利率{gm:.1f}% EPS{eps:.2f}。'

    rs = []
    if '死叉' in str(macd): rs.append('MACD死叉——动能减弱')
    if not rs: rs.append('暂无显著风险')
    sct_items = [
        ('短期趋势', '多头' in str(st_t), '+10/-10'),
        ('中期趋势', '多头' in str(mt_t), '+10/-5'),
        ('MACD', '金叉' in str(macd), '+8/-8'),
        ('ROE', roe > 20, f'+{10 if roe>20 else 5 if roe>10 else -5 if roe<=5 else 0}'),
        ('毛利率', gm > 50, f'+{8 if gm>50 else 4 if gm>30 else 0}'),
    ]
    sct = ''.join(f'<tr><td>{n}</td><td class="{"val-up"if ok else"val-dn"}">{"✓"if ok else"✗"}</td><td>{p}</td></tr>' for n, ok, p in sct_items)

    t10 = b.get('top10', [])[:10]
    t10h = ''.join(f'<tr><td>{r.get("股东名称","")}</td><td>{r.get("持股比例","")}</td></tr>' for r in t10) if t10 else '<tr><td colspan=2>暂无</td></tr>'

    fyh = ''
    if fi:
        keys = ['报告期', '营业总收入', '净利润', '基本每股收益', '净资产收益率', '销售毛利率']
        fr = ''.join('<tr>' + ''.join(f'<td>{r.get(k,"—")}</td>' for k in keys) + '</tr>' for r in fi[-5:])
        fyh = f'<h3 style="color:var(--gold);margin:8px 0">关键财务(近5期)</h3><table class="cns"><thead><tr>{"".join(f"<th>{k}</th>" for k in keys)}</tr></thead><tbody>{fr}</tbody></table>'

    html = f'''<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><title>{name}·研报</title>{CSS}</head><body>
<nav class="top-nav">
<div class="logo"><div class="logo-icon">{name[0]}</div><span class="stock-name">{name}</span><span class="stock-code">{code}.{"SH"if code.startswith("6")else"SZ"}</span></div>
<div class="nav-links">{NAV}</div>
<span style="font-size:12px;color:var(--text-muted)">📅{dt}</span>
<button class="theme-toggle" id="tb" onclick="toggleTheme()">☀浅色</button>
</nav>

<div class="hero" id="hero">
<div class="hero-price-block"><span class="hero-price">{price:.2f}</span><span class="hero-change {uc}">{chg:+.2f}%</span></div>
<div class="hero-meta">
<div class="hero-meta-item"><div class="val">{dt}</div><div class="label">基准日</div></div>
<div class="hero-meta-item"><div class="val">{sd}</div><div class="label">公司质地</div></div>
<div class="hero-meta-item"><div class="val">{tp}</div><div class="label">目标价</div></div>
<div class="hero-meta-item"><div class="val">{rr}</div><div class="label">盈亏比</div></div>
<div class="hero-meta-item"><div class="val" style="color:{risk_c}">{risk_lv}</div><div class="label">风险</div></div>
</div>
{tags_html and f'<div class="hero-tags">{tags_html}</div>'}
</div>

<div class="conclusion-top" id="conclusion-top">
<div class="big-verdict">🎯{vd}</div>
<div class="verdict-detail">{verdict_detail}</div>
<div class="verdict-tags" style="display:flex;gap:12px;margin-top:12px;flex-wrap:wrap">{_vtags_html(ai)}</div>
<div style="display:flex;gap:20px;margin-top:14px;padding-top:12px;border-top:1px dashed var(--border);flex-wrap:wrap">
<div style="text-align:center"><div style="font-size:11px;color:var(--text-muted)">买入区间</div><div style="font-weight:700;color:var(--green-down);font-size:15px">{buy_r}</div></div>
<div style="text-align:center"><div style="font-size:11px;color:var(--text-muted)">止损位</div><div style="font-weight:700;color:var(--green-down);font-size:15px">{sl_v}</div></div>
<div style="text-align:center"><div style="font-size:11px;color:var(--text-muted)">目标价</div><div style="font-weight:700;color:var(--red-up);font-size:15px">{tp}</div></div>
<div style="text-align:center"><div style="font-size:11px;color:var(--text-muted)">建议仓位</div><div style="font-weight:700;color:var(--gold-light);font-size:15px">{_pos(ai)}</div></div>
<div style="text-align:center"><div style="font-size:11px;color:var(--text-muted)">盈亏比</div><div style="font-weight:700;color:var(--gold-light);font-size:15px">{rr}</div></div>
</div></div>

<!-- 公司画像 + 近期动态 -->
<div class="grid-2" id="profile">
<div class="card"><div class="card-header"><span class="icon">🏢</span><h2>公司画像</h2></div>
<p style="color:var(--text-secondary)"><strong style="color:var(--red-up)">主营业务：</strong>{_biz_line(zyg)}</p>
<div style="margin:12px 0"><span class="tag">{name}</span>{_biz_tags_html(zyg)}</div>
<dl class="info-grid" style="margin-top:12px">
<dt>公司全称</dt><dd>{name}</dd>
<dt>上市日期</dt><dd>{_basic_field(b,'上市日期')}</dd>
<dt>所属行业</dt><dd>{_basic_field(b,'行业')}</dd>
<dt>总股本</dt><dd>{_spot_field(sp,'总股本','—')}</dd>
<dt>实际控制人</dt><dd>{_basic_field(b,'实际控制人')}</dd>
</dl>
</div>
<div class="card"><div class="card-header"><span class="icon">📰</span><h2>近期动态</h2></div>
<p style="color:var(--text-muted)">暂无新闻数据（API限制），请参考WebSearch搜索结果。</p></div>
</div>

<!-- 主营业务饼图 + 关键财务指标 -->
<div class="grid-2">
<div class="card"><div class="card-header"><span class="icon">📊</span><h2>主营业务构成</h2><span class="sub">{_latest_report(zyg)}</span></div>
<div style="width:100%;height:200px;display:flex;align-items:center;justify-content:center;color:var(--text-muted);background:var(--card-bg-alt);border-radius:8px">📊 饼图区域</div>
<div style="font-size:11px;color:var(--text-muted);text-align:center;margin-top:6px">{_biz_ratio_text(zyg)}</div>
</div>
<div class="card"><div class="card-header"><span class="icon">📈</span><h2>关键财务指标</h2><span class="sub">近5期</span></div>
{_fi_table(fi)}
</div>
</div>

<!-- K线图 -->
<div class="card" id="kline-section"><div class="card-header"><span class="icon">📈</span><h2>K线图 · 近120交易日</h2><span class="sub">前复权日K</span></div>
<p style="color:var(--text-muted);text-align:center;padding:40px">请在Streamlit页面查看K线图表</p>
<div class="kpi-info-row" style="display:flex;justify-content:space-around;margin-top:18px;padding-top:14px;border-top:2px solid var(--border)">
<div class="kpi-info-item" style="text-align:center"><div class="label" style="font-size:12px;color:var(--text-muted)">向上空间(目标价)</div><div class="value" style="font-size:20px;font-weight:700;color:var(--gold-light)">{_up_space(price, tp_val_str)}</div></div>
<div class="kpi-info-item" style="text-align:center"><div class="label" style="font-size:12px;color:var(--text-muted)">盈亏比</div><div class="value" style="font-size:20px;font-weight:700;color:var(--gold-light)">{rr}</div></div>
<div class="kpi-info-item" style="text-align:center"><div class="label" style="font-size:12px;color:var(--text-muted)">目标价(中期)</div><div class="value" style="font-size:20px;font-weight:700;color:var(--gold-light)">{tp}</div></div>
<div class="kpi-info-item" style="text-align:center"><div class="label" style="font-size:12px;color:var(--text-muted)">建议周期</div><div class="value" style="font-size:20px;font-weight:700;color:var(--gold-light)">3-6月</div></div>
</div></div>

<!-- Step 0: 任务锁定 -->
{_step0_html(ai0)}

<!-- Step 1: 宏观与周期定位 -->
{_step1_html(ai1)}

<!-- Step 2: 产业链深度拆解 -->
{_step2_html(ai)}

<!-- Step 3: 公司筛选与质量评分 -->
<div class="card" id="quality"><div class="card-header"><span class="icon">⭐</span><h2>公司筛选与质量评分</h2><span class="sub">{sc}/100 · {grade_text(gd)}</span></div>
{_score_card_html(fi, st_t, mt_t, macd)}
<div class="rating"><div class="badge">{sc}</div><div class="body"><div class="title">{vd}</div><div class="desc">{adv}</div></div></div></div>

<!-- Step 4-8: 占位卡片（逐步填充） -->
{_step4_html(ai4, zyg)}
<div class="card" id="risk"><div class="card-header"><span class="icon">⚠️</span><h2>风险分析</h2><span class="sub">Step 5</span></div><ul class="alert-list">{''.join(f'<li>{r}</li>' for r in rs)}</ul></div>
<div class="card" id="valuation"><div class="card-header"><span class="icon">💎</span><h2>估值与买卖时机</h2><span class="sub">Step 6</span></div><p style="color:var(--text-muted)">待AI分析补充</p></div>
<div class="card" id="compare"><div class="card-header"><span class="icon">⚖️</span><h2>对标分析</h2><span class="sub">Step 7</span></div><p style="color:var(--text-muted)">待AI分析补充</p></div>
<div class="card" id="tracking"><div class="card-header"><span class="icon">📋</span><h2>跟踪计划与综合结论</h2><span class="sub">Step 8</span></div><p style="color:var(--text-muted)">待AI分析补充</p></div>

<div class="card" id="technical"><div class="card-header"><span class="icon">📈</span><h2>技术面与资金面分析</h2><span class="sub">Step 9</span></div><p style="color:var(--text-muted)">待AI分析补充</p></div>

<footer><p>⚠仅供研究参考，不构成投资建议</p><p>📅{datetime.now().strftime('%Y-%m-%d %H:%M')} · 数据:akshare</p></footer>
</body></html>'''
    return html


def _step0_html(ai0):
    if not ai0: return ''
    items = ''.join('<div style="background:var(--card-bg-alt);padding:10px 16px;border-radius:8px;text-align:center"><div style="font-size:11px;color:var(--text-muted)">' + i["label"] + '</div><div style="font-weight:700;color:var(--text-primary)">' + i["value"] + '</div></div>' for i in ai0.get('items',[]))
    return '<div class="card" id="mission"><div class="card-header"><span class="icon">🎯</span><h2>' + ai0.get("title","任务锁定") + '</h2></div><p style="color:var(--text-secondary);line-height:1.8">' + ai0.get("body","") + '</p><div style="margin-top:14px;display:flex;gap:16px;flex-wrap:wrap">' + items + '</div></div>'

def _step1_html(ai1):
    if not ai1: return ''
    cyc = ''.join('<li style="padding:4px 0">• ' + l + '</li>' for l in ai1.get('cycle',[]))
    pol = ''.join('<li style="padding:4px 0">• ' + l + '</li>' for l in ai1.get('policy',[]))
    return '<div class="card" id="macro"><div class="card-header"><span class="icon">🌍</span><h2>' + ai1.get("title","宏观定位") + '</h2></div><div style="margin-bottom:16px"><h3 style="font-size:15px;color:var(--gold-light);margin-bottom:8px">经济周期映射</h3><ul style="list-style:none;padding:0;font-size:13px;color:var(--text-secondary)">' + cyc + '</ul></div><div style="margin-bottom:16px"><h3 style="font-size:15px;color:var(--gold-light);margin-bottom:8px">政策与环境扫描</h3><ul style="list-style:none;padding:0;font-size:13px;color:var(--text-secondary)">' + pol + '</ul></div><div style="background:var(--card-bg-alt);padding:14px 18px;border-radius:8px;border-left:4px solid var(--gold)"><h3 style="font-size:15px;color:var(--gold-light);margin-bottom:6px">核心矛盾</h3><p style="font-size:14px;color:var(--text-secondary)">' + ai1.get("contradiction","") + '</p></div></div>'

def _step2_html(ai):
    if not ai: return ''
    srcs = ''
    for i, s in enumerate(ai.get('sources',[])):
        srcs += '<p style="font-size:13px;color:var(--text-secondary);line-height:1.8">' + str(i+1) + '. <strong style="color:' + s["color"] + ';">' + s["name"] + '：</strong>' + s["desc"] + '<br></p>'
    # SVG
    up = (ai.get('svg_upstream') or [{}])[0]
    mid = (ai.get('svg_midstream') or [{}])[0]
    dn = (ai.get('svg_downstream') or [{}])[0]
    up_it = ''.join('<text x="85" y="' + str(62+16*j) + '" text-anchor="middle" font-size="11" class="svg-sub">' + t + '</text>' for j,t in enumerate(up.get('items',[])))
    mid_it = ''.join('<text x="345" y="' + str(52+16*j) + '" text-anchor="middle" font-size="12" class="svg-sub">' + t + '</text>' for j,t in enumerate(mid.get('items',[])))
    dn_it = ''.join('<text x="655" y="' + str(62+16*j) + '" text-anchor="middle" font-size="11" class="svg-sub">' + t + '</text>' for j,t in enumerate(dn.get('items',[])))
    svg = '<div class="chain-svg"><svg viewBox="0 0 800 150" xmlns="http://www.w3.org/2000/svg"><defs><marker id="ar" markerWidth="10" markerHeight="10" refX="9" refY="4" orient="auto"><polygon points="0 0,10 4,0 8" fill="#d4a853"/></marker></defs><rect x="10" y="25" width="150" height="100" fill="var(--card-bg-alt)" stroke="#d4a853" stroke-width="2" rx="10"/><text x="85" y="50" text-anchor="middle" font-weight="700" font-size="14" class="svg-hdr">' + up['header'] + '</text>' + up_it + '<line x1="160" y1="75" x2="230" y2="75" stroke="#d4a853" stroke-width="2" marker-end="url(#ar)"/><rect x="235" y="10" width="220" height="130" fill="var(--card-bg-alt)" stroke="#f55656" stroke-width="3" rx="12"/><text x="345" y="35" text-anchor="middle" font-weight="800" font-size="16" fill="#f55656">' + mid['header'] + '</text>' + mid_it + '<line x1="455" y1="75" x2="525" y2="75" stroke="#d4a853" stroke-width="2" marker-end="url(#ar)"/><rect x="530" y="25" width="250" height="100" fill="var(--card-bg-alt)" stroke="#d4a853" stroke-width="2" rx="10"/><text x="655" y="50" text-anchor="middle" font-weight="700" font-size="14" class="svg-hdr">' + dn['header'] + '</text>' + dn_it + '</svg></div>'
    # Tables
    tr = ''.join('<tr><td>' + r[0] + '</td><td>' + r[1] + '</td><td>' + r[2] + '</td></tr>' for r in ai.get('trend_table',[]))
    vr = ''.join('<tr><td>' + r[0] + '</td><td>' + r[1] + '</td><td>' + r[2] + '</td></tr>' for r in ai.get('value_chain',[]))
    kj = ai.get('key_judgment','')
    return '<div class="card" id="chain"><div class="card-header"><span class="icon">🔗</span><h2>' + ai.get("title","") + '</h2></div><div style="margin-bottom:16px"><h3 style="font-size:15px;color:var(--gold-light);margin-bottom:8px">题材来源判断</h3>' + srcs + '</div><h3 style="font-size:15px;color:var(--gold-light);margin-bottom:8px">产业链图谱</h3>' + svg + '<div class="grid-2" style="margin-top:16px"><div><h3 style="font-size:15px;color:var(--gold-light);margin-bottom:8px">趋势三要素</h3><table class="cns"><thead><tr><th>维度</th><th>评估</th><th>打分</th></tr></thead><tbody>' + tr + '</tbody></table></div><div><h3 style="font-size:15px;color:var(--gold-light);margin-bottom:8px">价值链利润分布</h3><table class="cns"><thead><tr><th>环节</th><th>代表企业</th><th>毛利率</th></tr></thead><tbody>' + vr + '</tbody></table></div></div><p style="font-size:13px;color:var(--text-secondary);margin-top:12px;padding:10px 14px;background:var(--card-bg-alt);border-radius:6px">💡 <strong>关键判断：</strong>' + kj + '</p></div>'

def _vtags_html(ai):
    if ai and ai.get('verdict_tags'):
        return ''.join('<span class="tag">' + t + '</span>' for t in ai['verdict_tags'])
    return ''

def _pos(ai):
    if ai and ai.get('position'): return ai['position']
    return '—'

def _biz_line(zyg):
    if not zyg: return '—'
    items = []
    for r in zyg[:5]:
        b = str(r.get('主营构成', r.get('经营项目', '')))
        if b and len(b)>2: items.append(b)
    return ', '.join(items[:3]) if items else '—'

def _biz_tags_html(zyg):
    if not zyg: return ''
    seen = set()
    tags = ''
    for r in zyg[:5]:
        b = str(r.get('主营构成', r.get('经营项目', '')))
        if b and len(b)>2 and b not in seen:
            tags += '<span class="tag">' + b[:8] + '</span>'
            seen.add(b)
    return tags

def _basic_field(b, key):
    basic = b.get('basic_info', [])
    for r in basic:
        if r.get('item','') == key or r.get('项目','') == key:
            return str(r.get('value', r.get('内容', '—')))
    return '—'

def _spot_field(sp, key, d='—'):
    v = sp.get(key)
    return str(v) if v else d

def _latest_report(zyg):
    if not zyg: return ''
    d = str(zyg[0].get('报告日期', ''))[:10] if zyg else ''
    return d if d else ''

def _biz_ratio_text(zyg):
    if not zyg: return ''
    parts = []
    for r in zyg[:3]:
        b = str(r.get('主营构成', r.get('经营项目', '')))[:8]
        p = str(r.get('收入占比', r.get('利润占比', '')))
        if b and len(b)>2: parts.append(f'{b}({p})')
    return ' | '.join(parts) if parts else ''

def _fi_table(fi):
    if not fi: return '<p style="color:var(--text-muted)">暂无</p>'
    keys = ['报告期','营业总收入','净利润','基本每股收益','净资产收益率','销售毛利率']
    fr = ''.join('<tr>' + ''.join('<td>' + str(r.get(k,'—')) + '</td>' for k in keys) + '</tr>' for r in fi[-5:])
    return '<table class="cns"><thead><tr>' + ''.join('<th>' + k + '</th>' for k in keys) + '</tr></thead><tbody>' + fr + '</tbody></table>'

def _up_space(price, tp_str):
    try:
        tp_parts = tp_str.replace('元','').split('-')
        tp_num = float(tp_parts[-1]) if tp_parts[-1] != '—' else 0
        if tp_num > 0 and price > 0:
            return f'+{(tp_num-price)/price*100:.1f}%'
    except: pass
    return '—'

def _score_card_html(fi, st_t, mt_t, macd):
    last = fi[-1] if fi else {}
    roe = float(str(last.get('净资产收益率',0)).replace('%','')) if fi else 0
    gm = float(str(last.get('销售毛利率',0)).replace('%','')) if fi else 0
    items = [
        ('短期趋势', '多头' in str(st_t), '+10/-10'),
        ('中期趋势', '多头' in str(mt_t), '+10/-5'),
        ('MACD', '金叉' in str(macd), '+8/-8'),
        ('ROE', roe>20, ('+10' if roe>20 else '+5' if roe>10 else '-5' if roe<=5 else '+0')),
        ('毛利率', gm>50, ('+8' if gm>50 else '+4' if gm>30 else '+0')),
    ]
    rows = ''.join('<tr><td>' + n + '</td><td class="' + ('val-up' if ok else 'val-dn') + '">' + ('✓' if ok else '✗') + '</td><td>' + p + '</td></tr>' for n,ok,p in items)
    return '<table class="cns"><thead><tr><th>维度</th><th>状态</th><th>加减分</th></tr></thead><tbody>' + rows + '</tbody></table>'

def grade_text(gd):
    m = {'A':'优秀','B':'良好','C':'一般','D':'较差'}
    return m.get(gd, gd)


    if ai and ai.get('verdict_tags'):
        return ''.join('<span class="tag">' + t + '</span>' for t in ai['verdict_tags'])
    return ''
def _pos(ai):
    if ai and ai.get('position'): return ai['position']
    return '—'

def _step4_html(ai4, zyg):
    if not ai4: return '<div class="card" id="elasticity"><div class="card-header"><span class="icon">⚡</span><h2>业绩弹性测算</h2></div><p style="color:var(--text-muted)">待AI分析补充</p></div>'
    # 弹性树
    branches_html = ''
    level_styles = {
        'core': 'background:rgba(245,86,86,0.08);border:1px solid rgba(245,86,86,0.3)',
        'secondary': 'background:rgba(212,168,83,0.08);border:1px solid rgba(212,168,83,0.3)',
        'other': 'background:rgba(255,255,255,0.03);border:1px solid var(--border)'
    }
    level_colors = {'core': 'var(--red-up)', 'secondary': 'var(--gold-light)', 'other': 'var(--text-secondary)'}
    level_icons = {'core': '🔴', 'secondary': '🟡', 'other': '⚪'}
    # 3-column flex for branches
    fle = ai4.get('branches', [])
    if fle:
        cols = ''.join(
            '<div style="flex:1;' + level_styles.get(b.get('level','other'),'') + ';border-radius:8px;padding:12px;text-align:center">'
            '<div style="font-weight:700;color:' + level_colors.get(b.get('level','other'),'var(--text-secondary)') + ';font-size:13px">' + level_icons.get(b.get('level','other'),'⚪') + ' ' + b.get('name','') + '</div>'
            '<div style="font-size:11px;color:var(--text-muted)">' + b.get('share','') + '·' + b.get('margin','') + '</div>'
            '<div style="font-size:12px;color:var(--text-secondary);margin-top:4px">' + '<br>'.join(b.get('products',[])) + '</div>'
            '<div style="font-size:11px;color:var(--text-muted);margin-top:4px">' + b.get('factor','') + '</div></div>'
            for b in fle)
        branches_html = '<div style="display:flex;gap:10px;width:100%;margin-top:10px">' + cols + '</div>'
    # 弹性树顶部
    tree = '<div style="background:var(--card-bg-alt);border:2px solid var(--gold);border-radius:10px;padding:16px;margin-bottom:16px"><div style="display:flex;flex-direction:column;align-items:center"><div style="background:linear-gradient(135deg,#1e1a10,#2c1a1a);border:2px solid var(--gold);border-radius:10px;padding:10px 24px;font-weight:700;font-size:15px;color:var(--text-primary)">中国巨石 FY2025营收 ' + ai4.get('total_revenue','') + '</div><div style="display:flex;width:100%;margin-top:6px"><div style="flex:2;text-align:center;border-top:2px solid var(--gold)"></div><div style="flex:1;border-top:2px solid var(--gold)"></div><div style="flex:1;border-top:2px solid var(--gold)"></div></div>' + branches_html + '</div></div>'
    # 情景分析
    scs = ai4.get('scenarios', [])
    sc_html = ''
    if scs:
        sc_cards = ''
        for s in scs:
            bg = 'rgba(40,199,91,0.06)' if s.get('type')=='悲观' else ('rgba(245,86,86,0.06)' if s.get('type')=='乐观' else 'rgba(212,168,83,0.06)')
            color = 'var(--green-down)' if s.get('type')=='悲观' else ('var(--red-up)' if s.get('type')=='乐观' else 'var(--gold-light)')
            sc_cards += '<div style="' + bg + ';border-radius:8px;padding:12px;text-align:center"><div style="font-size:11px;color:var(--text-muted);margin-bottom:4px">' + s.get('type','') + ': ' + s.get('desc','') + '</div><div style="font-size:12px;font-family:var(--font-mono);color:var(--text-secondary)">营收' + s.get('revenue','') + ' 净利' + s.get('profit','') + '</div><div style="font-weight:700;color:' + color + ';font-size:14px;margin-top:2px">目标价 ' + s.get('price','') + ' (PE ' + s.get('pe','') + ')</div></div>'
        sc_html = '<div class="grid-2" style="margin-top:12px">' + sc_cards[:1000] + '</div>'
    # 公式
    formula_html = '<h3 style="font-size:15px;color:var(--gold-light);margin:16px 0 10px">价格敏感度公式</h3><div style="background:var(--card-bg-alt);border-radius:8px;padding:14px 18px;margin-bottom:12px"><div style="font-size:12px;color:var(--text-muted);margin-bottom:8px;text-align:center">核心公式</div><div style="font-family:var(--font-mono);font-size:14px;color:var(--text-primary);text-align:center;padding:10px 16px;background:rgba(245,86,86,0.06);border-radius:8px;margin-bottom:10px"><strong>' + ai4.get('formula','') + '</strong></div>' + sc_html + '</div>'
    return '<div class="card" id="elasticity"><div class="card-header"><span class="icon">⚡</span><h2>' + ai4.get('title','业绩弹性测算') + '</h2></div><h3 style="font-size:15px;color:var(--gold-light);margin-bottom:10px">分业务弹性树</h3>' + tree + formula_html + '</div>'

def save_report(code, name, html):
    d = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
    os.makedirs(d, exist_ok=True)
    fp = os.path.join(d, f"研报-{name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html")
    with open(fp, "w", encoding="utf-8") as f: f.write(html)
    return fp
