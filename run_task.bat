@echo off
cd /d %~dp0
echo [%date% %time%] 开始跑选股 >> stock_choose\output\task_log.txt
python run_stock_choose.py >> stock_choose\output\task_log.txt 2>&1
echo [%date% %time%] 运行结束，退出码 %errorlevel% >> stock_choose\output\task_log.txt
echo [%date% %time%] 推送数据到 GitHub >> stock_choose\output\task_log.txt
python push_output.py >> stock_choose\output\task_log.txt 2>&1
echo [%date% %time%] 推送结束，退出码 %errorlevel% >> stock_choose\output\task_log.txt
