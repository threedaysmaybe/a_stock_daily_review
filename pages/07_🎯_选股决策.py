"""选股决策：量化选股 / 涨停股分析 / 明日预测 三合一，统一入口。"""
import streamlit as st
import sys
import os
import json
import warnings
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
warnings.filterwarnings("ignore")

import config as cfg
import data_fetcher as df_
import data_manager as dm
import analyzer as anl
import visualizer as viz
import pandas as pd
import numpy as np
from datetime import datetime
from utils.formatters import fmt_dataframe
from utils.helpers import fmt_cn
from utils.ui import inject_css, conclusion
import streamlit.components.v1 as components

st.set_page_config(page_title="选股决策", page_icon="🎯", layout="wide")
inject_css()
st.title("🎯 选股决策")
st.caption(f"交易日：{(st.session_state.get('_trading_day') or pd.Timestamp.now()).strftime('%Y-%m-%d')} | 选股 + 涨停 + 预测，一站式决策")

tab_quant, tab_limit, tab_predict = st.tabs(["📊 量化选股", "🐉 涨停股分析", "🔮 明日预测"])


# ============================================================
# Tab 1: 量化选股（原 09 页）
# ============================================================
with tab_quant:
    from stock_choose import main as stock_choose_main
    from stock_choose import daily_verify as stock_choose_verify

    ENGINE_OUT = os.path.join(os.path.dirname(stock_choose_main.__file__), "output")

    # ---- 手机端（Cloud）数据源：GitHub 上的最新数据 ----
    _GH_BASE = "https://raw.githubusercontent.com/threedaysmaybe/a_stock_daily_review/main/stock_choose/output"
    _GH_FILES = ["manifest.json", "summary.json", "验证记录.csv", "股票池.csv",
                 "trade_calendar.txt", "ic_history.csv", "finance_cache.csv"]

    def _is_cloud() -> bool:
        # Cloud 上没有本地 config.yaml（gitignore 未提交）；桌面端有
        return not os.path.exists(os.path.join(os.path.dirname(stock_choose_main.__file__), "config.yaml"))

    @st.cache_data(ttl=600)
    def _gh_manifest() -> dict:
        try:
            import urllib.request
            with urllib.request.urlopen(_GH_BASE + "/manifest.json", timeout=10) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception:
            return {}

    @st.cache_data(ttl=600)
    def _gh_download(name: str, dest: str) -> bool:
        try:
            import urllib.request
            from urllib.parse import quote
            url = _GH_BASE + "/" + quote(name)
            with urllib.request.urlopen(url, timeout=25) as r:
                data = r.read()
            os.makedirs(dest, exist_ok=True)
            with open(os.path.join(dest, name), "wb") as f:
                f.write(data)
            return True
        except Exception:
            return False

    def _try_github_refresh(expected_date: str) -> str | None:
        """GitHub 数据已更新到预期交易日 → 下载到临时目录并返回路径；否则返回 None。"""
        manifest = _gh_manifest()
        if not expected_date or manifest.get("result_date") != expected_date:
            return None
        import glob
        import shutil
        import tempfile
        dest = os.path.join(tempfile.gettempdir(), "sc_github_out")
        os.makedirs(dest, exist_ok=True)
        # 1) 先把部署仓库里已有的历史结果复制过来，保证所有跑过的日期都标绿
        repo_out = os.path.join(os.path.dirname(stock_choose_main.__file__), "output")
        for f in glob.glob(os.path.join(repo_out, "短期选股_*.xlsx")):
            try:
                shutil.copy(f, os.path.join(dest, os.path.basename(f)))
            except Exception:
                pass
        # 2) 从 GitHub 下载 manifest 里列出的全部结果日期（覆盖为最新）
        for ds in manifest.get("result_dates", [expected_date]):
            _gh_download(f"短期选股_{ds.replace('-', '')}.xlsx", dest)
        # 3) 下载其它公共数据文件
        for name in _GH_FILES:
            _gh_download(name, dest)
        if os.path.exists(os.path.join(dest, "summary.json")) and \
           os.path.exists(os.path.join(dest, f"短期选股_{expected_date.replace('-', '')}.xlsx")):
            return dest
        return None

    def _load_verify_records() -> pd.DataFrame:
        p = os.path.join(ENGINE_OUT, "验证记录.csv")
        if not os.path.exists(p):
            return pd.DataFrame()
        try:
            return pd.read_csv(p)
        except Exception:
            return pd.DataFrame()

    @st.cache_data(ttl=3600)
    def _get_engine_cfg() -> dict:
        """加载内嵌引擎配置。

        桌面端：直接用本地 stock_choose/config.yaml（含 token/sendkey）。
        Cloud：加载 GitHub 提交的 config_public.yaml（权重/门槛等），
        再从 Secrets 注入 tushare_token / sendkey 两个敏感字段。
        """
        import yaml
        base_dir = os.path.dirname(stock_choose_main.__file__)
        cfg_path = os.path.join(base_dir, "config.yaml")
        if os.path.exists(cfg_path):
            return stock_choose_main.load_config(cfg_path)

        public_path = os.path.join(base_dir, "config_public.yaml")
        if os.path.exists(public_path):
            with open(public_path, encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
        else:
            cfg = {}

        def _secret(*names):
            for name in names:
                try:
                    node = st.secrets
                    for part in name.split("."):
                        node = node[part]
                    if node:
                        return node
                except Exception:
                    continue
            return None

        # 兼容写法 1：整个 config_yaml 作为 secret（老方式）
        full_yaml = _secret("stock_choose.config_yaml", "config_yaml")
        if full_yaml:
            loaded = yaml.safe_load(full_yaml)
            if isinstance(loaded, dict):
                cfg = loaded

        # 兼容写法 2：单独注入 token/sendkey（推荐方式）
        tok = _secret("stock_choose.tushare_token", "tushare_token")
        if tok:
            cfg.setdefault("short_term", {})["tushare_token"] = tok
        sendkey = _secret("stock_choose.sendkey", "sendkey")
        if sendkey:
            cfg.setdefault("push", {})["sendkey"] = sendkey

        if not cfg.get("short_term", {}).get("tushare_token"):
            # 诊断：把当前 Secrets 的键名（不含值）带进报错，方便排查写法问题
            try:
                detail = []
                for k in list(st.secrets.keys()):
                    v = st.secrets[k]
                    detail.append(f"{k}:{list(v.keys())}" if isinstance(v, dict) else f"{k}:<非字典>")
                keys_info = "；".join(detail) if detail else "（空）"
            except Exception:
                keys_info = "（读取失败）"
            raise FileNotFoundError(
                "找不到选股引擎配置。当前 Cloud Secrets 顶层键为：" + keys_info +
                "。正确写法：[stock_choose] 段下配 tushare_token = \"...\"（下划线），"
                "可选 sendkey = \"...\""
            )
        return cfg

    @st.cache_data(ttl=3600)
    def _default_trade_date() -> str:
        """与内嵌引擎一致：收盘后跑当天，否则上一交易日。"""
        return stock_choose_main.default_run_date() or stock_choose_main.last_trading_day()

    @st.cache_data(ttl=300)
    def _load_latest_summary() -> dict:
        import json as _json
        p = os.path.join(ENGINE_OUT, "summary.json")
        try:
            with open(p, encoding="utf-8") as f:
                return _json.load(f)
        except Exception:
            return {}

    @st.cache_data(ttl=300)
    def _load_latest_picks() -> pd.DataFrame:
        import glob
        files = sorted(glob.glob(os.path.join(ENGINE_OUT, "短期选股_*.xlsx")))
        if not files:
            return pd.DataFrame()
        try:
            return pd.read_excel(files[-1])
        except Exception:
            return pd.DataFrame()

    # ---- 纯 HTML 日历（绿色=有结果，点日期通过 URL 参数回传） ----
    @st.cache_data(ttl=3600)
    def _trade_cal_set() -> set:
        # 复用引擎进程内缓存：default_run_date / 日历共用一次 akshare 请求
        try:
            return stock_choose_main._trade_dates()
        except Exception:
            return set()

    @st.cache_data(ttl=300)
    def _result_date_set() -> set:
        import glob
        res = set()
        for f in glob.glob(os.path.join(ENGINE_OUT, "短期选股_*.xlsx")):
            stem = os.path.basename(f).replace("短期选股_", "").replace(".xlsx", "")
            if len(stem) == 8 and stem.isdigit():
                res.add(f"{stem[:4]}-{stem[4:6]}-{stem[6:]}")
        return res

    @st.cache_data(ttl=300)
    def _load_picks_for(date_str: str) -> pd.DataFrame:
        p = os.path.join(ENGINE_OUT, f"短期选股_{date_str.replace('-', '')}.xlsx")
        if not os.path.exists(p):
            return pd.DataFrame()
        try:
            return pd.read_excel(p)
        except Exception:
            return pd.DataFrame()

    def _verify_for(date_str: str):
        """从 验证记录.csv 读取该日的验证结果（验证的是前一日的选股）。"""
        recs = _load_verify_records()
        if recs is None or not len(recs):
            return None, None
        row = recs[recs["日期"].astype(str).str.strip() == date_str]
        if not len(row):
            return None, None
        r = row.iloc[0]

        def _f(v):
            try:
                return float(v)
            except Exception:
                return None

        verify = {
            "prev_date": str(r.get("前日", "")),
            "win_rate": _f(r.get("胜率")) or 0.0,
            "n": int(_f(r.get("总数")) or 0),
            "avg_ret": _f(r.get("组合涨幅")) or 0.0,
        }
        market_avg = _f(r.get("大盘涨幅"))
        return verify, market_avg

    def _green_cal_html(selected: str) -> str:
        """只读绿色日历：展示 selected 所在月份，带正确空位，绿色=有结果。"""
        import calendar as _cal
        tds = _trade_cal_set()
        res = _result_date_set()
        _sd = datetime.strptime(selected, "%Y-%m-%d")
        year, month = _sd.year, _sd.month
        total = _cal.monthrange(year, month)[1]
        start_dow = datetime(year, month, 1).weekday()
        today = datetime.now().strftime("%Y-%m-%d")
        cells = []
        for w in ["一", "二", "三", "四", "五", "六", "日"]:
            cells.append(f'<div class="qcal-cell qcal-wh">{w}</div>')
        for _ in range(start_dow):
            cells.append('<div class="qcal-cell qcal-empty"></div>')
        for d in range(1, total + 1):
            ds = f"{year:04d}-{month:02d}-{d:02d}"
            cls = "qcal-cell"
            if ds in res:
                cls += " qcal-green"
            if ds not in tds:
                cls += " qcal-ntd"
            if ds == selected:
                cls += " qcal-sel"
            if ds == today:
                cls += " qcal-today"
            cells.append(f'<div class="{cls}">{d}</div>')
        grid = "".join(cells)
        return f'''
<style>
.qcal{{font-family:-apple-system,sans-serif;background:#0F172A;color:#F1F5F9;padding:8px;border-radius:10px;max-width:340px}}
.qcal-title{{font-weight:bold;font-size:14px;display:block;margin-bottom:6px}}
.qcal-grid{{display:grid;grid-template-columns:repeat(7,1fr);gap:3px}}
.qcal-cell{{aspect-ratio:1;display:flex;align-items:center;justify-content:center;border-radius:6px;
font-size:12px;border:1px solid #334155;color:#E2E8F0}}
.qcal-wh{{background:#1E293B;font-weight:bold;color:#94A3B8}}
.qcal-empty{{border:none}}
.qcal-green{{background:#22c55e;color:#fff;border-color:#22c55e;font-weight:bold}}
.qcal-ntd{{opacity:.35}}
.qcal-sel{{outline:2px solid #1677ff}}
.qcal-today{{font-weight:bold;border-color:#1677ff}}
.qcal-label{{margin:8px 0 0;font-size:12px;color:#94A3B8}}
</style>
<div class="qcal">
  <span class="qcal-title">{year}年{month}月</span>
  <div class="qcal-grid">{grid}</div>
  <p class="qcal-label">绿色=已有结果；日期选择用上方日期组件（切月/选日期都在那里）</p>
</div>'''

    def _pick_cols(df: pd.DataFrame) -> pd.DataFrame:
        if df is None or not len(df):
            return pd.DataFrame()
        cols = ["rank", "name", "code", "total_score", "signal_score", "final_score", "pos_tags", "risk_tags"]
        out = df[[c for c in cols if c in df.columns]].copy()
        out["code"] = out["code"].astype(str)
        return out

    def _render_sentiment(sent: dict):
        level = sent.get("level", "未知")
        advice = sent.get("advice", "")
        up_ratio = sent.get("up_ratio")
        if up_ratio is not None:
            st.info(
                f"市场情绪：**{level}**（上涨家数占比 {up_ratio:.1%}）→ {advice}"
                + ("；⚠️ 外围风险 → 空仓" if sent.get("overseas_risk") else "")
            )

    def _render_picks(picks_df: pd.DataFrame):
        if not len(picks_df):
            st.warning("暂无选股结果（可能休市、空仓或全部被门槛过滤）。")
            return
        top1 = picks_df.iloc[0]
        signal_part = f"{top1['signal_score']:+.2f}" if pd.notna(top1.get("signal_score")) else ""
        conclusion(
            f"首选：<b>{top1['name']}</b>（{top1['code'].split('.')[0]}）",
            f"综合得分 <b>{top1['final_score']:.2f}</b>"
            + (f"（因子分 {top1['total_score']:.2f}，信号分 {signal_part}）" if signal_part else "")
            + f"，截面打分第 {int(top1['rank'])} 名。",
            tone="bull",
        )
        show = picks_df.copy()
        show["code"] = show["code"].str.split(".").str[0]
        show.columns = ["排名", "名称", "代码", "因子分", "信号分", "综合得分", "看多标签", "风险标签"]
        cyb_mask = show["代码"].str.startswith(("300", "301", "688"))
        main_df, cyb_df = show[~cyb_mask], show[cyb_mask]
        if len(main_df):
            st.markdown(f"#### 主板（{len(main_df)} 只）")
            st.dataframe(main_df, use_container_width=True, hide_index=True)
        if len(cyb_df):
            st.markdown(f"#### 创业板 / 科创板（{len(cyb_df)} 只）")
            st.dataframe(cyb_df, use_container_width=True, hide_index=True)
        st.caption("内嵌 stock_choose 引擎：6 因子加权 + 信号加减分 + 情绪仓位截断（含自进化权重/因子池）")

    def _render_thresholds():
        st.markdown("#### 🌍 明日参考阈值")
        st.markdown(
            "| 市场 | 触发建议别买 |\n"
            "|------|------|\n"
            "| 美股收盘 | 跌超 2% |\n"
            "| 韩国开盘 | 跌超 2% |\n"
            "| 日经开盘 | 跌超 2% |"
        )

    def _render_verify(verify: dict, market_avg):
        if not verify:
            st.info("暂无昨日选股验证（首次运行或昨日无选股结果）。")
            return
        win = verify.get("win_rate", 0)
        n = verify.get("n", 0)
        up = int(win * n)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("胜率", f"{win:.0%}（{up}/{n} 上涨）")
        c2.metric("组合涨幅", f"{verify.get('avg_ret', 0):+.2%}")
        if market_avg is not None:
            c3.metric("大盘涨幅", f"{market_avg:+.2%}")
            c4.metric("超额", f"{verify.get('avg_ret', 0) - market_avg:+.2%}")
        chart = stock_choose_verify.format_winrate_chart(_load_verify_records())
        if chart and chart != "（暂无胜率记录）":
            with st.expander("📈 近15日胜率曲线"):
                st.code(chart)

    def _render_watchlist():
        p = os.path.join(ENGINE_OUT, "股票池.csv")
        if not os.path.exists(p):
            st.info("股票池为空（暂无持仓关注）。")
            return
        try:
            wl = pd.read_csv(p)
        except Exception:
            st.info("股票池为空（暂无持仓关注）。")
            return
        if len(wl):
            wl = wl[wl["移除日期"].fillna("").astype(str).str.strip().eq("")]
        if not len(wl):
            st.info("股票池为空（暂无持仓关注）。")
            return
        wl = wl.copy()
        wl["code_short"] = wl["code"].astype(str).str.split(".").str[0]
        cyb_mask = wl["code"].astype(str).str.startswith(("300", "301", "688"))
        st.markdown("#### 💼 股票池")
        for title, sub in (("主板", wl[~cyb_mask]), ("创业板/科创板", wl[cyb_mask])):
            if not len(sub):
                continue
            st.markdown(f"**{title}（{len(sub)} 只）**")
            show = sub[["name", "code_short", "加入日期"]].copy()
            show.columns = ["名称", "代码", "加入日期"]
            st.dataframe(show, use_container_width=True, hide_index=True)

    def _render_health(health: str):
        if health:
            st.markdown("#### 🧬 因子健康度（方向×IC）")
            st.markdown(health)

    def _render_report(picks_df: pd.DataFrame, sent: dict, verify: dict, market_avg, health: str):
        _render_sentiment(sent)
        _render_picks(picks_df)
        _render_thresholds()
        st.markdown("#### 📋 昨日选股表现")
        _render_verify(verify, market_avg)
        _render_watchlist()
        _render_health(health)

    st.subheader("📊 量化选股（内嵌 stock_choose 引擎）")
    _default_str = _default_trade_date()
    _default_d = datetime.strptime(_default_str, "%Y-%m-%d").date()

    # Cloud 手机端：先看 GitHub 上的数据是否已更新到预期交易日，是就直接下载加载
    _data_hint = ""
    if _is_cloud():
        _expected = _default_trade_date()
        _gh_dir = _try_github_refresh(_expected) if _expected else None
        if _gh_dir and _gh_dir != ENGINE_OUT:
            ENGINE_OUT = _gh_dir
            _load_latest_summary.clear()
            _load_latest_picks.clear()
            _result_date_set.clear()
            _load_picks_for.clear()
        _data_hint = ("✅ 已加载 GitHub 最新数据" if ENGINE_OUT != os.path.join(os.path.dirname(stock_choose_main.__file__), "output")
                      else "⚠️ GitHub 数据未更新到最新交易日；可点「🔄 跑选股」抓取")

    _picked = st.date_input("数据日期（日历选择）", value=_default_d, key="quant_date")
    date_str = (_picked.strftime("%Y-%m-%d") if _picked else _default_str)

    st.markdown(_green_cal_html(date_str), unsafe_allow_html=True)
    if _data_hint:
        st.caption(_data_hint)
    st.caption(f"📅 已选数据日期：**{date_str}**（绿色=有结果，日历跟随所选月份）")
    run = st.button("🔄 跑选股", type="primary", use_container_width=True, key="quant_run")

    live = None
    if run:
        with st.spinner("内嵌引擎运行中：全市场数据 + 因子打分 + 信号加减分 + 情绪仓位 + 验证/股票池..."):
            try:
                sc_cfg = _get_engine_cfg()
                live = stock_choose_main.run_daily_pipeline(sc_cfg, date_str.strip(), push=False)
            except Exception as e:  # noqa: BLE001
                st.error(f"选股失败：{type(e).__name__}: {e}")
        if live:
            _load_latest_summary.clear()
            _load_latest_picks.clear()
            _result_date_set.clear()
            st.success(f"引擎完成：数据日期 {live['date']}")

    if live:
        _render_report(
            _pick_cols(live.get("top")),
            live.get("sentiment") or {},
            live.get("verify"),
            live.get("market_avg"),
            live.get("health") or "",
        )
    else:
        # 按所选日期展示：选股表/昨日表现从该日期文件读取；
        # 情绪只保存最近一次（summary.json），其余全局数据（股票池/阈值/健康度）照常显示
        summary = _load_latest_summary()
        picks = _pick_cols(_load_picks_for(date_str))
        sent = (summary.get("sentiment") or {}) if summary.get("date") == date_str else {}
        verify, market_avg = _verify_for(date_str)
        health = summary.get("health") or ""

        if not len(picks):
            st.warning(f"{date_str} 暂无选股结果（可能休市、未跑或全部被过滤）。点「🔄 跑选股」可生成该日结果。")
        _render_report(picks, sent, verify, market_avg, health)


# ============================================================
# Tab 2: 涨停股分析（原 04 页，去掉建仓建议）
# ============================================================
with tab_limit:
    if "_dragon_analyzed" not in st.session_state:
        st.session_state._dragon_analyzed = {}
    if "_dragon_loaded" not in st.session_state:
        st.session_state._dragon_loaded = False

    def parse_pct(val):
        if pd.isna(val) or val is None:
            return np.nan
        try:
            if isinstance(val, (int, float)):
                return float(val)
            return float(str(val).strip().replace("%", "").replace(" ", ""))
        except Exception:
            return np.nan

    def format_time(val):
        if pd.isna(val) or val is None or val == "":
            return ""
        try:
            if isinstance(val, (int, float)):
                s = str(int(val)).zfill(6)
                return s[:2] + ":" + s[2:4] + ":" + s[4:6]
            s = str(val).strip().replace(".0", "")
            if len(s) == 6 and s.isdigit():
                return s[:2] + ":" + s[2:4] + ":" + s[4:6]
            return s
        except Exception:
            return str(val)

    def render_stock_card(row):
        name = row.get("名称", "")
        code = row.get("代码", "")
        change_pct = parse_pct(row.get("涨跌幅", 0))
        if np.isnan(change_pct):
            change_pct = 0
        first_time = row.get("首次封板时间", "")
        is_blown = row.get("炸板次数", 0) > 0
        time_str = format_time(first_time)
        color = "#DC143C" if change_pct >= 0 else "#228B22"
        tags = []
        if is_blown:
            tags.append("炸板")
        if time_str and time_str not in ["00:00:00", "0:00:00"]:
            tags.append(time_str)
        tags_text = " | ".join(tags) if tags else ""
        st.markdown(f'''
        <div style="background:#1E293B;border-radius:8px;padding:10px 12px;min-height:85px;height:85px;
                    border-left:4px solid {color};border:1px solid #334155;display:flex;flex-direction:column;
                    justify-content:space-between;margin:4px 0;">
            <div style="display:flex;justify-content:space-between;align-items:center;">
                <span style="font-weight:bold;font-size:17px;color:#FFFFFF;">{name}</span>
                <span style="color:{color};font-weight:bold;font-size:16px;">{change_pct:+.2f}%</span>
            </div>
            <div><span style="font-size:12px;color:#94A3B8;">{code}</span>
            <span style="font-size:12px;color:#64748B;margin-left:8px;">{tags_text}</span></div>
        </div>''', unsafe_allow_html=True)

    def render_ladder_board(df):
        if df.empty or "连板数" not in df.columns:
            st.info("暂无连板数据")
            return
        board_groups = {}
        for _, row in df.iterrows():
            boards = int(row.get("连板数", 1))
            board_groups.setdefault(boards, []).append(row)
        max_board = max(board_groups.keys())
        st.subheader("📊 连板天梯")
        for board_num in range(max_board, 0, -1):
            if board_num not in board_groups:
                continue
            stocks = board_groups[board_num]
            if board_num >= 6:
                label = f"🔥 {board_num}板 🏆"
            elif board_num >= 4:
                label = f"⭐ {board_num}板"
            elif board_num >= 2:
                label = f"📌 {board_num}板"
            else:
                label = "📌 首板"
            st.markdown(f"### {label}  ({len(stocks)}只)")
            cols_per_row = 4
            for i in range(0, len(stocks), cols_per_row):
                row_stocks = stocks[i:i + cols_per_row]
                cols = st.columns(cols_per_row)
                for j, stock in enumerate(row_stocks):
                    with cols[j]:
                        render_stock_card(stock)
            st.divider()

    limit_up_df = st.session_state.get("_limit_up_df")
    if limit_up_df is None or limit_up_df.empty:
        with st.spinner("正在获取涨停板数据..."):
            limit_up_df = df_.get_limit_up_stocks()
            st.session_state["_limit_up_df"] = limit_up_df

    if limit_up_df.empty:
        st.warning("今日暂无涨停板数据（可能为非交易日）")
    else:
        _max_b = int(limit_up_df["连板数"].max()) if "连板数" in limit_up_df.columns else 0
        conclusion(f"今日涨停 <b>{len(limit_up_df)}</b> 家，最高 <b>{_max_b} 连板</b>",
                   "涨停家数反映情绪热度，连板高度反映题材持续性。",
                   tone="bull" if len(limit_up_df) >= 50 else "neutral")
        col1, col2, col3, col4, col5 = st.columns(5)
        col1.metric("📈 涨停家数", len(limit_up_df))
        if "连板数" in limit_up_df.columns:
            col2.metric("🏆 最高连板", f"{limit_up_df['连板数'].max()}连板")
            col3.metric("📌 连板股数", len(limit_up_df[limit_up_df["连板数"] > 1]))
            if "炸板次数" in limit_up_df.columns:
                blown_count = len(limit_up_df[limit_up_df["炸板次数"] > 0])
                col4.metric("💥 炸板率", f"{blown_count / len(limit_up_df) * 100:.1f}%")
            if "一字板" in limit_up_df.columns:
                col5.metric("🔒 一字板", len(limit_up_df[limit_up_df["一字板"] == True]))

        # 一次性分析所有涨停股
        if not st.session_state._dragon_loaded:
            with st.spinner("正在分析所有涨停股技术指标..."):
                progress_bar = st.progress(0, text="分析进度")
                total = len(limit_up_df)
                for idx, (_, row) in enumerate(limit_up_df.iterrows()):
                    code = str(row.get("代码", "")).zfill(6)
                    name = row.get("名称", "")
                    local_k = dm.load_local(f"stock_{code}.csv")
                    kdf = local_k if (local_k is not None and not (hasattr(local_k, 'empty') and local_k.empty)) else df_.get_stock_kline(code, days=120)
                    if not kdf.empty:
                        kdf = anl.calc_all_indicators(kdf)
                        pred = anl.predict_next_day(kdf)
                        trend = anl.classify_trend(kdf)
                        sr = anl.calc_stop_loss_take_profit(kdf, "中等")
                        st.session_state._dragon_analyzed[code] = {"kline": kdf, "pred": pred, "trend": trend, "sr": sr, "name": name}
                    progress_bar.progress((idx + 1) / total, text=f"分析中 ({idx+1}/{total}) {name}")
                progress_bar.empty()
                st.session_state._dragon_loaded = True
                # 不调用 st.rerun()（在 tabs 里会触发 DeltaGenerator 异常），结果已存 _dragon_analyzed，直接继续渲染

        render_ladder_board(limit_up_df)

        with st.expander("📊 查看完整涨停板数据"):
            ddf = limit_up_df.copy()
            display_cols = ["代码", "名称", "涨跌幅", "所属行业", "连板数", "炸板次数", "首次封板时间", "最后封板时间"]
            available_cols = [c for c in display_cols if c in ddf.columns]
            if "一字板" in ddf.columns:
                available_cols.append("一字板")
            ddf_display = ddf[available_cols].copy()
            for col in ddf_display.columns:
                if "封板时间" in str(col):
                    ddf_display[col] = ddf_display[col].apply(format_time)
                elif "涨跌幅" in str(col):
                    ddf_display[col] = ddf_display[col].apply(parse_pct)
                elif "一字板" in str(col):
                    ddf_display[col] = ddf_display[col].apply(lambda x: "✅" if x else "")
            st.dataframe(ddf_display, hide_index=True, use_container_width=True, height=400)

        st.subheader("🔍 涨停股技术分析")
        stock_options = [f"{str(r.get('代码','')).zfill(6)} — {r.get('名称','')} ({r.get('连板数',1)}连板)" for _, r in limit_up_df.iterrows()]
        selected = st.selectbox("选择涨停股进行深度分析", stock_options, key="dragon_select")
        if selected:
            parts = selected.split("—")
            code = parts[0].strip()
            name = parts[1].strip().split("(")[0].strip()
            analyzed = st.session_state._dragon_analyzed.get(code)
            if analyzed is None:
                st.warning(f"{name}({code}) 分析数据不存在")
            else:
                kdf = analyzed["kline"]
                pred = analyzed["pred"]
                trend = analyzed["trend"]
                sr = analyzed["sr"]
                rt = st.session_state.get("_realtime_cache", {}).get(code, {})
                lu_row = None
                _lu = st.session_state.get("_limit_up_df")
                if _lu is not None and not _lu.empty and "代码" in _lu.columns:
                    _mask = _lu["代码"].astype(str).str.zfill(6) == code
                    if _mask.any():
                        lu_row = _lu[_mask].iloc[0]

                def _f(v):
                    try:
                        return float(v)
                    except (TypeError, ValueError):
                        return 0

                latest_close = kdf["close"].iloc[-1] if not kdf.empty else 0
                price = rt.get("price", 0) or (_f(lu_row.get("最新价")) if lu_row is not None else 0) or latest_close
                change_pct = rt.get("change_pct", 0) or (_f(lu_row.get("涨跌幅")) if lu_row is not None else 0)
                amount = rt.get("amount", 0) or (_f(lu_row.get("成交额")) if lu_row is not None else 0)
                turnover = rt.get("turnover", 0) or (_f(lu_row.get("换手率")) if lu_row is not None else 0)
                pe = rt.get("pe", 0)
                pb = rt.get("pb", 0)
                total_mv = rt.get("total_mv", 0) or (_f(lu_row.get("总市值")) if lu_row is not None else 0)

                st.subheader(f"📊 {name} ({code}) 实时行情")
                metric_cols = st.columns(6)
                metric_cols[0].metric("最新价", f"{price:.2f}" if price else "—")
                metric_cols[1].metric("涨跌幅", f"{change_pct:+.2f}%" if change_pct else "—", delta_color="inverse")
                metric_cols[2].metric("成交额", fmt_cn(amount) if amount else "—")
                metric_cols[3].metric("换手率", f"{turnover:.2f}%" if turnover else "—")
                metric_cols[4].metric("PE/PB", f"{pe:.1f}/{pb:.1f}" if pe else "—")
                metric_cols[5].metric("总市值", fmt_cn(total_mv) if total_mv else "—")

                st.subheader("📈 K线图")
                kline_html = viz.plot_kline_echarts(kdf, title=f"{name}({code}) · 日K线", height=500)
                components.html(kline_html, height=530)

                st.subheader("🔧 技术指标")
                ind_type = st.radio("选择指标", ["MACD", "KDJ", "RSI", "BOLL"], horizontal=True, key="dragon_indicator")
                ind_html = viz.plot_indicator_echarts(kdf, ind_type, height=280)
                components.html(ind_html, height=310)

                st.subheader("📋 趋势研判")
                trend_cols = st.columns(4)
                trend_cols[0].info(f"**短期趋势**\n\n{trend.get('short_signal', '—')}")
                trend_cols[1].info(f"**中期趋势**\n\n{trend.get('mid_signal', '—')}")
                trend_cols[2].info(f"**MACD信号**\n\n{trend.get('macd_signal', '—')}")
                patterns = anl.detect_patterns(kdf)
                if patterns:
                    trend_cols[3].warning(f"**K线形态**\n\n" + "\n".join(patterns))
                else:
                    trend_cols[3].info("**K线形态**\n\n无明显形态")

                st.subheader("🔮 明日预测")
                pred_cols = st.columns(3)
                pred_cols[0].metric("预测方向", pred.get("direction", "—"))
                pred_cols[1].metric("置信度", f"{pred.get('confidence', 0)}%")
                pred_cols[2].metric("波动区间", pred.get("range", "—"))
                if pred.get("reasons"):
                    with st.expander("📝 预测依据"):
                        for reason in pred["reasons"]:
                            st.caption(f"• {reason}")

                if sr:
                    st.subheader("🎯 止盈止损位")
                    sr_cols = st.columns(5)
                    sr_cols[0].error(f"**止损（严格）**\n¥{sr.get('stop_loss_tight', '—')}")
                    sr_cols[1].warning(f"**止损（宽松）**\n¥{sr.get('stop_loss_loose', '—')}")
                    sr_cols[2].success(f"**止盈1**\n¥{sr.get('take_profit_1', '—')}")
                    sr_cols[3].success(f"**止盈2**\n¥{sr.get('take_profit_2', '—')}")
                    sr_cols[4].info(f"**建议仓位**\n{sr.get('suggested_position', '—')}")
                    st.caption("⚠️ 止盈止损是基于近期波动率（ATR）估算的参考位，不是精确预测。涨停股波动剧烈，结合分时承接执行。")


# ============================================================
# Tab 3: 明日预测（原 07 页）
# ============================================================
with tab_predict:
    _local_pf = dm.load_portfolio()

    st.subheader("📊 大盘明日预判")
    index_predictions = {}
    with st.spinner("正在分析大盘指数..."):
        for name, code in cfg.INDICES.items():
            df = df_.get_index_kline(code)
            if not df.empty:
                df = anl.calc_all_indicators(df)
                pred = anl.predict_next_day(df)
                trend = anl.classify_trend(df)
                index_predictions[name] = {"prediction": pred, "trend": trend}

    if index_predictions:
        cols = st.columns(len(index_predictions))
        for i, (name, data) in enumerate(index_predictions.items()):
            pred = data["prediction"]
            trend = data["trend"]
            with cols[i]:
                st.subheader(name)
                st.metric("方向", pred.get("direction", "—"))
                st.caption(f"置信度：{pred.get('confidence', 0)}%")
                st.caption(f"波动区间：{pred.get('range', '—')}")
                st.caption(f"MACD：{trend.get('macd_signal', '—')}")

    bullish = sum(1 for d in index_predictions.values() if "看涨" in d["prediction"].get("direction", "") or "偏强" in d["prediction"].get("direction", ""))
    bearish = sum(1 for d in index_predictions.values() if "看跌" in d["prediction"].get("direction", "") or "偏弱" in d["prediction"].get("direction", ""))
    if bullish > bearish:
        st.success(f"🎯 大盘综合判断：偏多（{bullish}/{len(index_predictions)}看涨）")
    elif bearish > bullish:
        st.error(f"🎯 大盘综合判断：偏空（{bearish}/{len(index_predictions)}看跌）")
    else:
        st.info("🎯 大盘综合判断：震荡")

    st.subheader("🌏 外围市场")
    with st.spinner("获取美股/日韩信号..."):
        try:
            import overseas as ov
            sig = ov.get_overseas_signal()
            if sig:
                cols = st.columns(4)
                cols[0].metric("纳指", f"{(sig.get('us_nasdaq') or 0)*100:+.2f}%")
                cols[1].metric("标普500", f"{(sig.get('us_sp500') or 0)*100:+.2f}%")
                cols[2].metric("韩国开盘", f"{(sig.get('kr_open') or 0)*100:+.2f}%")
                cols[3].metric("日经开盘", f"{(sig.get('jp_open') or 0)*100:+.2f}%")
                if ov.overseas_risk(sig):
                    st.error("⚠️ 外围风险：美股或日韩大跌，建议谨慎")
                else:
                    st.success("✅ 外围平稳")
            else:
                st.caption("外围数据暂不可用")
        except Exception:
            st.caption("外围数据获取失败")

    st.subheader("🔥 板块明日预判")
    with st.spinner("正在分析板块走势..."):
        sector_df = df_.get_sector_spot()
    if not sector_df.empty:
        top5 = sector_df.head(5)
        bottom5 = sector_df.tail(5)
        col_t, col_b = st.columns(2)
        with col_t:
            st.write("**🟢 强势板块（可能延续）**")
            for _, row in top5.iterrows():
                pct = row.get("change_pct", 0)
                note = "⚠️ 短期过热" if pct > 3 else "趋势延续" if pct > 1 else "温和上涨"
                st.write(f"🔥 **{row.get('sector_name','')}**：{pct:+.2f}% — {note}")
        with col_b:
            st.write("**🔴 弱势板块（可能反弹/续跌）**")
            for _, row in bottom5.iterrows():
                pct = row.get("change_pct", 0)
                note = "💡 超跌" if pct < -3 else "弱势延续" if pct < -1 else "小幅调整"
                st.write(f"📉 **{row.get('sector_name','')}**：{pct:+.2f}% — {note}")

    st.subheader("💼 持仓股明日预测")
    # 用 session_state 缓存，避免每次 rerun（切tab/拖拽排序）重复跑 31 只股票的循环
    _pf_key = "|".join(sorted(_local_pf.keys()))
    if st.session_state.get("holdings_pred_key") == _pf_key and "holdings_pred" in st.session_state:
        holdings_pred = st.session_state["holdings_pred"]
    else:
        holdings_pred = []
        _emotion = None
        try:
            _sent = df_.get_market_sentiment()
            if _sent and _sent.get("up_ratio") is not None:
                _emotion = {"up_ratio": _sent["up_ratio"] / 100}
        except Exception:
            _emotion = None

        for code, name in _local_pf.items():
            with st.spinner(f"正在分析 {name}({code})..."):
                df = df_.get_stock_kline(code)
                if df.empty:
                    continue
                df = anl.calc_all_indicators(df)
                fund_df = df_.get_stock_fund_factors(code)
                pred = anl.predict_next_day(df, fund_df if not fund_df.empty else None, _emotion)
                realtime = df_.get_stock_realtime(code)
                holdings_pred.append({
                    "code": code, "name": name,
                    "price": realtime.get("price", df["close"].iloc[-1]) if realtime else df["close"].iloc[-1],
                    "change_pct": realtime.get("change_pct", 0) if realtime else 0,
                    "direction": pred.get("direction", "—"),
                    "confidence": pred.get("confidence", 0),
                    "range": pred.get("range", "—"),
                    "score": pred.get("score", 0),
                })
        st.session_state["holdings_pred"] = holdings_pred
        st.session_state["holdings_pred_key"] = _pf_key

    if holdings_pred:
        pred_df = pd.DataFrame(holdings_pred)
        st.dataframe(fmt_dataframe(pred_df), hide_index=True, use_container_width=True)
        pred_df_sorted = pred_df.sort_values("score", ascending=False)
        st.subheader("📈 持仓股评分排行")
        for _, row in pred_df_sorted.iterrows():
            score = row["score"]
            bar_len = int(max(0, min(100, score + 5)) * 0.5)
            bar_color = "#DC143C" if score > 3 else "#FFD700" if score > 0 else "#228B22"
            st.write(f"**{row['name']}**({row['code']}) — {row['direction']} | 评分：{score:.1f}")
            st.markdown(f'<div style="background:{bar_color};height:6px;width:{bar_len}%;border-radius:3px;"></div>', unsafe_allow_html=True)
        best = pred_df_sorted.iloc[0]
        worst = pred_df_sorted.iloc[-1]
        conclusion(f"持仓预测：最看好 <b>{best['name']}</b>（评分 {best['score']:.1f}）",
                   f"最谨慎 <b>{worst['name']}</b>（评分 {worst['score']:.1f}）。评分越高次日越看好。",
                   tone="bull" if best["score"] > 3 else "neutral")

    # 综合操作建议（统一出口）
    st.subheader("📋 明日操作建议")
    market_signal = 1 if bullish > bearish else (-1 if bearish > bullish else 0)
    hold_avg_score = np.mean([h["score"] for h in holdings_pred]) if holdings_pred else 0
    conclusion(
        "操作建议："
        + ("🟢 大盘偏多，可适当提升仓位" if market_signal > 0 else "🔴 大盘偏空，控制仓位" if market_signal < 0 else "🟡 大盘震荡，高抛低吸"),
        f"持仓平均评分 <b>{hold_avg_score:.1f}</b> 分。"
        + ("持仓评分偏低，注意精选标的。" if hold_avg_score <= 0 else "持仓整体偏强，可关注强势板块轮动。"),
        tone="bull" if market_signal > 0 else ("bear" if market_signal < 0 else "neutral"),
    )
    st.caption("⚠️ 以上为 AI 基于技术指标的预判，不构成投资建议。市场有风险，投资需谨慎。")
