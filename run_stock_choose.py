"""内嵌量化选股引擎入口（原 02_stock_choose 工具，现已内嵌到 04 项目）。

用法：
    python run_stock_choose.py                # 默认日期：收盘后跑当天，否则上一交易日
    python run_stock_choose.py --date 2026-10-09
    python run_stock_choose.py --long         # 同时跑长期表

定时任务（Windows 任务计划）指向本文件或 run_task.bat 即可。
"""
from stock_choose.main import main

if __name__ == "__main__":
    main()
