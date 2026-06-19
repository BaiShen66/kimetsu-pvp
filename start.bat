@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo.
echo ========================================
echo   极限格斗 PVP 鬼灭之刀
echo   服务器启动中...
echo ========================================
echo.
echo   浏览器打开 http://localhost:8000
echo   按 Ctrl+C 停止服务器
echo ========================================
echo.
c:\Users\34303\anaconda3\python.exe main.py
pause
