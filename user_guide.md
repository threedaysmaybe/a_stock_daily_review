# 每日 A 股复盘工具 · 用户指南

> 项目目录：`D:\03_AI\04_a_stock_daily_review`
> 维护原则：只维护本目录（04），02 已停用；所有分析功能桌面与手机共享同一套代码、权重、数据。

---

## 1. 系统组成

| 模块 | 说明 | 入口 |
|---|---|---|
| Streamlit 复盘应用 | 大盘走势 / 板块分析 / 资金情绪 / 持仓分析 / 选股决策 / 生成报告 / 板块龙头 | `app.py` + `pages/` |
| 内嵌选股引擎 | 权重打分 + 信号加减分 + 情绪仓位 + 每周一自进化 | `stock_choose/` |
| 选股 CLI | 命令行跑选股 | `run_stock_choose.py` |
| 定时任务入口 | 跑选股 + 推送 GitHub | `run_task.bat` |
| 每日数据下载 | 下载当天行情到 `data/` 并推送（每天 23:00 计划任务） | `daily_update.py` |
| 网页版选股 | 手机浏览器可点「跑选股」 | `web_app.py` + `run_web.bat` |
| 数据推送 | 把 `data/` + 选股结果推 GitHub | `push_output.py` |

---

## 2. 日常使用流程（推荐）

```
桌面端（生产数据）
   │  1. 双击「启动复盘工具.bat」看盘复盘
   │  2. 每天 23:00 定时任务自动下载当天数据并推送
   │  3. 手动跑选股：双击 run_task.bat
   ▼
GitHub（数据中转，公开仓库）
   │
   ▼
手机端（随时查看，Streamlit Cloud）
```

- 手机端打开 Cloud 地址即可看**最新数据**（大盘/板块/资金/持仓/选股结果全都有）
- 手机端也可以点「跑选股」（需先配 Secrets，见第 6 节）
- 手机端**不做**「更新数据」——原始行情抓取只在桌面

---

## 3. 手动运行速查

在项目目录打开命令行（或直接双击 bat）：

| 操作 | 命令 / 文件 | 说明 |
|---|---|---|
| 跑选股 + 推手机 | 双击 `run_task.bat` | 最常用；跑完自动推 GitHub |
| 只跑选股 | `python run_stock_choose.py` | 不推送 |
| 指定日期跑 | `python run_stock_choose.py --date 2026-10-20` | 补跑某一天 |
| 跑长期表 | `python run_stock_choose.py --long` | 每周一自动跑，可手动强制 |
| 只推数据 | `python push_output.py` | 把本地数据/结果推 GitHub |
| 下载当天数据+推送 | `python daily_update.py` | 每天 23:00 计划任务执行的就是它 |

### 日期规则（自动）

- 收盘后（15:30 起）运行 → 跑**当天**数据
- 盘中 / 盘前运行 → 跑**上一交易日**（用于预测当天）
- 周末 / 节假日运行 → 自动跳过

---

## 4. 各服务端口

| 服务 | 地址 | 启动方式 |
|---|---|---|
| 复盘 Streamlit | http://localhost:8599 | 双击 `启动复盘工具.bat` |
| 04 网页选股 | http://127.0.0.1:8000 | `python web_app.py` 或 `run_web.bat` |
| 02 网页选股（已弃用） | http://127.0.0.1:8001 | 一般不需要开 |
| 手机 Cloud | https://astockdailyreview-kzwqdydcspexuydappnqhqh.streamlit.app/ | 无需本地服务 |

> 端口冲突：8503 曾被游戏「三角洲行动」启动器占用，已改为 8599。
> 报 "Port xxx is not available" 时，`netstat -ano | findstr :xxx` 查占用进程。

---

## 5. 选股决策页说明（桌面 + 手机一致）

- 日历：绿色 = 该日有选股结果；点日期切换查看那天的结果
- 主板 / 创业板·科创板分表、昨日表现、股票池、因子健康度都会跟着日期切换
- 「跑选股」用当前选中日期跑完整引擎（全市场数据 + 打分 + 信号 + 情绪仓位）
- **空仓是正常现象**：外围风险触发（纳指/韩国开盘/日经开盘跌超 2%）会强制空仓

### 每周一：因子权重自进化

- 每周一跑选股时自动执行：按近期 IC 调整因子权重、收纳/退役候选因子
- 周一若休市，那一周进化跳过（不顺延）
- 进化后的权重会随 `config_public.yaml` 自动推送，手机端同步生效

---

## 6. 手机端配置（只配一次）

### 6.1 Streamlit Cloud Secrets

Cloud 上「跑选股」需要两个密钥（权重等公开配置自动从 GitHub 读取）：

```toml
[stock_choose]
tushare_token = "你的Tushare token"
sendkey = "你的Server酱 sendkey"
```

配置位置：Cloud app → Settings → Secrets → 保存 → Reboot。

### 6.2 发布新代码后

每次 push 新代码后，Cloud 上 **Redeploy / Reboot** 一次即可。

---

## 7. 配置与权重

| 文件 | 内容 | 是否提交 GitHub |
|---|---|---|
| `stock_choose/config.yaml` | 完整配置（含 token/sendkey） | 否（本地，gitignore） |
| `stock_choose/config_public.yaml` | 权重/门槛/因子（无密钥） | 是（自动生成并同步） |

修改权重：改本地 `config.yaml` → 跑一次选股 → 自动生成 `config_public.yaml` 并推送 → 手机端生效。

---

## 8. 数据文件

| 路径 | 内容 |
|---|---|
| `data/YYYYMMDD/` | 每天行情：指数/板块/概念/涨停/资金流/北向/龙虎榜/个股 |
| `data/manifest.json` | 手机端判断数据新不新、下载哪些文件 |
| `data/portfolio.json` | 持仓（桌面维护，手机只读） |
| `stock_choose/output/` | 选股结果 xlsx、summary.json、验证记录、股票池、交易日历 |

---

## 9. 常见问题

| 问题 | 处理 |
|---|---|
| git push 失败（连不上 github） | 开代理（127.0.0.1:1080）；脚本已自动「代理失败→直连」重试 |
| 手机报 tushare_token 找不到 | 检查 Secrets：`[stock_choose]` 段 + 小写 `tushare_token` + 双引号 |
| 手机选股慢 | 正常：完整流程 2-3 分钟，Cloud 在美西访问国内数据源更慢；建议日常靠桌面定时任务，手机只看 |
| 游资龙虎榜为空 | 已修：筛选直接认 Tushare 格式；若仍空，检查 `data/<当日>/lhb.csv` 是否下载成功 |
| 选股结果为空 | 大概率是外围风险空仓（看 summary.json 的 overseas_risk）；也可能是该日未跑 |
| 端口被占 | `netstat -ano | findstr :端口` 找 PID，`taskkill /PID xxx /F` |
| 23:00 任务在休市日还跑吗 | 不会：`daily_update.py` 已加休市跳过 |

---

## 10. 定时任务

| 任务 | 时间 | 作用 |
|---|---|---|
| 每日数据下载 | 每天 23:00 | `daily_update.py`：下载当天数据 + 推 GitHub |
| 选股任务 | 收盘后（计划任务） | `run_task.bat`：跑选股 + 推 GitHub |

> 查看计划任务：`schtasks /query | findstr -i daily`
