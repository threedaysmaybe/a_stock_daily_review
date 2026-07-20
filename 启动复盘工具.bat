@echo off
cd /d "%~dp0"
echo ================================
echo   每日A股复盘模型
echo ================================
echo.
streamlit run app.py --server.headless true --server.port 8503
pause
