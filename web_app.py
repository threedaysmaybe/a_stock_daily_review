"""量化选股 Web 版（04 内嵌引擎）：手机/电脑浏览器访问，点「跑选股」手动触发。

手动触发的完整流程与定时任务一致：选股 + 昨日验证 + 股票池 + 微信推送（Server酱）。
数据全部来自内嵌的 stock_choose 引擎（实时拉 Tushare），不依赖「更新数据」按钮。
"""
import contextlib
import glob
import io
import json
import os
import threading
from datetime import datetime

import pandas as pd
from flask import Flask, jsonify, request

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SC_OUT = os.path.join(BASE_DIR, "stock_choose", "output")

app = Flask(__name__)

_run_state = {"running": False, "started": None, "finished": None, "log": ""}


def _run_pick(date_str: str = None):
    _run_state["running"] = True
    _run_state["started"] = datetime.now().strftime("%H:%M:%S")
    _run_state["finished"] = None
    try:
        from stock_choose import main as stock_choose_main
        cfg = stock_choose_main.load_config("config.yaml")
        if date_str and date_str.strip():
            date_str = date_str.strip()
            if not stock_choose_main.is_trading_day(date_str):
                _run_state["log"] = f"{date_str} 非交易日（周末/节假日），请换一个交易日"
                return
            date = date_str
        else:
            date = stock_choose_main.default_run_date()
            if date is None:
                _run_state["log"] = "今天休市（周末/节假日），不跑选股"
                return
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            stock_choose_main.run_daily_pipeline(cfg, date, push=True)
        _run_state["log"] = f"✅ 已完成 {date}\n" + buf.getvalue()
    except Exception as e:  # noqa: BLE001
        _run_state["log"] = str(e)
    finally:
        _run_state["running"] = False
        _run_state["finished"] = datetime.now().strftime("%H:%M:%S")


def _load_summary() -> dict:
    p = os.path.join(SC_OUT, "summary.json")
    if os.path.exists(p):
        try:
            return json.load(open(p, encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return {}
    return {}


def _latest_result():
    files = sorted(glob.glob(os.path.join(SC_OUT, "短期选股_*.xlsx")))
    if not files:
        return None, None
    latest = files[-1]
    df = pd.read_excel(latest)
    date = os.path.basename(latest).replace("短期选股_", "").replace(".xlsx", "")
    return date, df


def _picks_for_date(date_str: str):
    """读取指定日期的选股结果（date_str 支持 YYYY-MM-DD 或 YYYYMMDD）。"""
    ds = str(date_str).replace("-", "")
    p = os.path.join(SC_OUT, f"短期选股_{ds}.xlsx")
    if not os.path.exists(p):
        return pd.DataFrame()
    try:
        return pd.read_excel(p)
    except Exception:  # noqa: BLE001
        return pd.DataFrame()


def _verify_for_date(date_str: str):
    """从 验证记录.csv 读取该日验证结果（验证的是前一日的选股）。返回 (verify, market_avg)。"""
    p = os.path.join(SC_OUT, "验证记录.csv")
    if not os.path.exists(p):
        return None, None
    try:
        recs = pd.read_csv(p)
    except Exception:  # noqa: BLE001
        return None, None
    row = recs[recs["日期"].astype(str).str.strip() == str(date_str)]
    if not len(row):
        return None, None
    r = row.iloc[0]

    def _f(v):
        try:
            return float(v)
        except Exception:  # noqa: BLE001
            return None

    verify = {
        "prev_date": str(r.get("前日", "")),
        "win_rate": _f(r.get("胜率")) or 0.0,
        "n": int(_f(r.get("总数")) or 0),
        "avg_ret": _f(r.get("组合涨幅")) or 0.0,
    }
    market_avg = _f(r.get("大盘涨幅"))
    return verify, market_avg


def _short(s, n=3):
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return ""
    s = str(s)
    parts = s.split()
    return " ".join(parts[:n]) + ("…" if len(parts) > n else "")


def _render_picks_table(df, is_cyb):
    sub = df[df["code"].astype(str).str.startswith(("300", "301", "688"))] if is_cyb else \
          df[~df["code"].astype(str).str.startswith(("300", "301", "688"))]
    if not len(sub):
        return ""
    rows = ""
    for _, r in sub.iterrows():
        code = str(r.get("code", "")).split(".")[0]
        score = r.get("final_score", 0)
        sign = "+" if pd.notna(score) and score >= 0 else ""
        pos = _short(r.get("pos_tags", ""))
        risk = _short(r.get("risk_tags", ""))
        rows += (f"<tr><td>{int(r.get('rank', 0))}</td><td>{r.get('name','')}</td>"
                 f"<td>{code}</td><td>{sign}{score:.2f}</td>"
                 f"<td class='pos'>{pos}</td><td class='risk'>{risk}</td></tr>")
    return rows


def _render_sentiment(sentiment):
    if not sentiment:
        return ""
    up = sentiment.get("up_ratio")
    up_str = f"{up:.0%}" if up is not None else "N/A"
    html = (f"<div class='box'><h2>市场情绪</h2>"
            f"<p><b>{sentiment.get('level','')}</b>｜上涨 {up_str}｜{sentiment.get('advice','')}</p>")
    if sentiment.get("overseas_risk"):
        ov = sentiment.get("overseas") or {}
        parts = []
        for k, label in [("us_nasdaq", "纳指"), ("us_sp500", "标普")]:
            if ov.get(k) is not None:
                parts.append(f"{label} {ov[k]:+.2%}")
        op = []
        for k, label in [("kr_open", "韩国开盘"), ("jp_open", "日经开盘")]:
            if ov.get(k) is not None:
                op.append(f"{label} {ov[k]:+.2%}")
        us_str = "、".join(parts) if parts else "无"
        op_str = "、".join(op) if op else "无"
        html += f"<p class='warn'>⚠️ 外围风险：美股[{us_str}]，日韩开盘[{op_str}]，建议空仓</p>"
    html += ("<p>明日参考（任一触发建议别买）：美股收盘跌超2%、韩国开盘跌超2%、日经开盘跌超2%</p>"
             "</div>")
    return html


def _render_verify(verify, market_avg=None):
    if not verify:
        return ""
    win = verify.get("win_rate", 0) or 0
    up = int(win * (verify.get("n", 0) or 0))
    avg = verify.get("avg_ret", 0) or 0
    mkt = market_avg
    excess = (avg - mkt) if mkt is not None else None
    mkt_s = f"{mkt:+.2%}" if mkt is not None else "N/A"
    excess_s = f"{excess:+.2%}" if excess is not None else "N/A"
    return (f"<div class='box'><h2>昨日({verify.get('prev_date','')})选股表现</h2>"
            f"<table><tr><th>胜率</th><th>上涨数</th><th>总数</th><th>组合</th><th>大盘</th><th>超额</th></tr>"
            f"<tr><td>{win:.0%}</td><td>{up}</td><td>{verify.get('n','')}</td>"
            f"<td>{avg:+.2%}</td><td>{mkt_s}</td><td>{excess_s}</td></tr></table></div>")


def _render_watchlist():
    p = os.path.join(SC_OUT, "股票池.csv")
    if not os.path.exists(p):
        return ""
    wl = pd.read_csv(p)
    wl = wl[wl["移除日期"].fillna("").astype(str).str.strip() == ""]
    if not len(wl):
        return ""
    main = wl[~wl["code"].astype(str).str.startswith(("300", "301", "688", "920"))]
    cyb = wl[wl["code"].astype(str).str.startswith(("300", "301", "688"))]
    html = "<div class='box'><h2>股票池（共 %d 只）</h2>" % len(wl)
    for title, sub in [("主板", main), ("创业板/科创板", cyb)]:
        if not len(sub):
            continue
        rows = ""
        for _, r in sub.iterrows():
            code = str(r.get("code", "")).split(".")[0]
            rows += f"<tr><td>{r.get('name','')}</td><td>{code}</td><td>{r.get('加入日期','')}</td></tr>"
        html += (f"<h3>{title}（{len(sub)}只）</h3>"
                 f"<table><tr><th>名称</th><th>代码</th><th>加入日期</th></tr>{rows}</table>")
    html += "</div>"
    return html


def _render_health(health):
    if not health:
        return ""
    body = health.replace("```", "")
    return f"<div class='box'><h2>因子健康度（方向×IC）</h2><pre>{body}</pre></div>"


_trade_cal_cache = {"dates": None}


def _trade_dates() -> list:
    """全市场交易日历（akshare，缓存一次）。"""
    if _trade_cal_cache["dates"] is None:
        try:
            import akshare as ak
            _trade_cal_cache["dates"] = sorted(ak.tool_trade_date_hist_sina()["trade_date"].astype(str).tolist())
        except Exception:  # noqa: BLE001
            _trade_cal_cache["dates"] = []
    return _trade_cal_cache["dates"]


def _result_dates() -> set:
    dates = set()
    for f in glob.glob(os.path.join(SC_OUT, "短期选股_*.xlsx")):
        stem = os.path.basename(f).replace("短期选股_", "").replace(".xlsx", "")
        if len(stem) == 8 and stem.isdigit():
            dates.add(f"{stem[:4]}-{stem[4:6]}-{stem[6:]}")
    return dates


@app.route("/calendar")
def calendar():
    import calendar as _cal
    year = int(request.args.get("year", datetime.now().year))
    month = int(request.args.get("month", datetime.now().month))
    result_dates = _result_dates()
    trade_dates = set(_trade_dates())
    days = []
    for day in range(1, _cal.monthrange(year, month)[1] + 1):
        ds = f"{year:04d}-{month:02d}-{day:02d}"
        days.append({
            "day": day,
            "date": ds,
            "has_result": ds in result_dates,
            "is_trading_day": ds in trade_dates,
        })
    return jsonify({
        "year": year,
        "month": month,
        "days": days,
        "today": datetime.now().strftime("%Y-%m-%d"),
    })


@app.route("/")
def index():
    summary = _load_summary()
    latest_date, latest_df = _latest_result()

    # 日历选中日期（YYYY-MM-DD）；未选则默认显示最新结果
    sel = (request.args.get("quant_date") or "").strip()
    if sel:
        df = _picks_for_date(sel)
        title_date = sel
    else:
        df = latest_df
        title_date = (f"{latest_date[:4]}-{latest_date[4:6]}-{latest_date[6:]}"
                      if latest_date else "")
        sel = title_date

    # 情绪只保存最近一次运行（summary.json），只有切到最近那次才显示
    sentiment = summary.get("sentiment", {}) if summary.get("date") == sel else {}
    health = summary.get("health", "")
    verify, market_avg = _verify_for_date(sel) if sel else (None, None)

    picks_html = ""
    if df is not None and len(df):
        main_rows = _render_picks_table(df, is_cyb=False)
        cyb_rows = _render_picks_table(df, is_cyb=True)
        picks_html = f"<div class='box'><h2>{title_date} 精选</h2>"
        if main_rows:
            picks_html += ("<h3>主板</h3><table><tr><th>排名</th><th>名称</th><th>代码</th>"
                           "<th>得分</th><th>看多</th><th>风险</th></tr>" + main_rows + "</table>")
        if cyb_rows:
            picks_html += ("<h3>创业板/科创板</h3><table><tr><th>排名</th><th>名称</th><th>代码</th>"
                           "<th>得分</th><th>看多</th><th>风险</th></tr>" + cyb_rows + "</table>")
        picks_html += "</div>"
    else:
        picks_html = f"<div class='box'><h2>{title_date} 精选</h2><p>该日期暂无选股结果，点上面按钮跑一次</p></div>"

    html = _HTML.replace("{{date}}", title_date or "-")
    html = html.replace("{{sel}}", sel)
    html = html.replace("{{sentiment}}", _render_sentiment(sentiment))
    html = html.replace("{{picks}}", picks_html)
    html = html.replace("{{verify}}", _render_verify(verify, market_avg))
    html = html.replace("{{watchlist}}", _render_watchlist())
    html = html.replace("{{health}}", _render_health(health))
    return html


@app.route("/run", methods=["POST"])
def run():
    if _run_state["running"]:
        return jsonify({"ok": False, "msg": "正在跑，请稍候"})
    date_arg = None
    try:
        data = request.get_json(silent=True) or {}
        date_arg = (data.get("date") or "").strip() or None
    except Exception:  # noqa: BLE001
        date_arg = None
    threading.Thread(target=_run_pick, kwargs={"date_str": date_arg}, daemon=True).start()
    return jsonify({"ok": True, "msg": "已开始跑选股"})


@app.route("/status")
def status():
    return jsonify(_run_state)


_HTML = """<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>量化选股</title>
<style>
body{font-family:-apple-system,sans-serif;margin:0;padding:12px;background:#f7f8fa;color:#333}
h1{font-size:20px;margin:8px 0}
h2{font-size:16px;margin:0 0 8px}
h3{font-size:14px;margin:12px 0 6px;color:#555}
button{font-size:18px;padding:14px;width:100%;background:#1677ff;color:#fff;border:none;border-radius:10px;cursor:pointer}
button:disabled{background:#a0c4ff}
#status{margin:10px 0;color:#666;font-size:14px}
.box{background:#fff;border-radius:10px;padding:12px;margin:10px 0}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{border:1px solid #e5e5e5;padding:6px;text-align:center}
th{background:#f0f2f5}
.pos{color:#d4380d}
.risk{color:#0958d9}
.warn{color:#d4380d;font-weight:bold}
pre{font-size:12px;overflow-x:auto;background:#fafafa;padding:8px;border-radius:6px;line-height:1.5}
p{margin:6px 0}
.cal{background:#fff;border-radius:10px;padding:6px;margin:8px 0;max-width:320px}
.calHead{display:flex;justify-content:space-between;align-items:center;margin-bottom:6px}
.calHead button{width:auto;padding:4px 10px;font-size:13px;background:#f0f2f5;color:#333}
.calTitle{font-weight:bold;font-size:14px}
.calGrid{display:grid;grid-template-columns:repeat(7,1fr);gap:3px}
.calCell{aspect-ratio:1;display:flex;align-items:center;justify-content:center;border-radius:6px;font-size:12px;cursor:pointer;border:1px solid #eee}
.calCell.green{background:#52c41a;color:#fff;border-color:#52c41a}
.calCell.sel{outline:2px solid #1677ff}
.calCell.ntd{opacity:.35;cursor:not-allowed}
.calCell.today{font-weight:bold;border-color:#1677ff}
#selLabel{margin:8px 0;font-size:13px;color:#555}
details.box summary{cursor:pointer;font-weight:bold;font-size:14px;color:#333}
details.box[open] summary{margin-bottom:4px}
</style>
</head>
<body>
<h1>📈 每日量化选股 · {{date}}</h1>
<details class="box" id="calDetails">
  <summary>📅 选择日期（点击展开日历，绿色=有数据）</summary>
  <div class="cal" id="calBox"></div>
  <p id="selLabel">未选择日期（留空=默认：收盘后跑当天）</p>
</details>
<button id="btn" onclick="runPick()">▶ 跑选股</button>
<p id="status"></p>
{{sentiment}}
{{picks}}
{{verify}}
{{watchlist}}
{{health}}
<script>
let calYear = new Date().getFullYear();
let calMonth = new Date().getMonth() + 1;
let selectedDate = '{{sel}}';
if(selectedDate){ calYear=parseInt(selectedDate.slice(0,4)); calMonth=parseInt(selectedDate.slice(5,7)); }

function prevMonth(){calMonth--;if(calMonth<1){calMonth=12;calYear--;}renderCal();}
function nextMonth(){calMonth++;if(calMonth>12){calMonth=1;calYear++;}renderCal();}

function renderCal(){
  fetch('/calendar?year='+calYear+'&month='+calMonth).then(r=>r.json()).then(d=>{
    const box=document.getElementById('calBox');
    let html='<div class="calHead"><button onclick="prevMonth()">◀</button><span class="calTitle">'+d.year+'年'+d.month+'月</span><button onclick="nextMonth()">▶</button></div>';
    html+='<div class="calGrid">';
    ['一','二','三','四','五','六','日'].forEach(w=>{html+='<div class="calCell" style="font-weight:bold;background:#f0f2f5;cursor:default">'+w+'</div>';});
    const first=new Date(d.year,d.month-1,1);
    const startDow=(first.getDay()+6)%7;
    for(let i=0;i<startDow;i++){html+='<div class="calCell" style="border:none;cursor:default"></div>';}
    d.days.forEach(day=>{
      let cls='calCell';
      if(day.has_result)cls+=' green';
      if(!day.is_trading_day)cls+=' ntd';
      if(day.date===d.today)cls+=' today';
      if(day.date===selectedDate)cls+=' sel';
      const onclick=day.is_trading_day?`onclick="selectDate('${day.date}')"`:'';
      html+='<div class="'+cls+'" '+onclick+'>'+day.day+'</div>';
    });
    html+='</div>';
    box.innerHTML=html;
    if(selectedDate){ document.getElementById('selLabel').textContent='已选择：'+selectedDate+'（点「跑选股」将跑这一天）'; }
  });
}
function selectDate(ds){
  selectedDate=ds;
  document.getElementById('selLabel').textContent='已选择：'+ds+'（点「跑选股」将跑这一天）';
  renderCal();
}
function runPick(){
  const btn=document.getElementById('btn');
  btn.disabled=true;btn.textContent='⏳ 跑选中...';
  document.getElementById('status').textContent='选股运行中（约2-3分钟）...';
  fetch('/run',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({date:selectedDate})}).then(r=>r.json()).then(d=>{
    if(!d.ok){document.getElementById('status').textContent=d.msg;btn.disabled=false;btn.textContent='▶ 跑选股';return;}
    poll();
  });
}
function poll(){
  fetch('/status').then(r=>r.json()).then(s=>{
    if(s.running){
      document.getElementById('status').textContent='选股运行中... 开始于 '+s.started;
      setTimeout(poll,3000);
    }else{
      document.getElementById('status').textContent='✅ 完成（'+s.finished+'），刷新结果...';
      setTimeout(()=>location.reload(),1000);
    }
  });
}
renderCal();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=False)
