@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo  CampusEvent 校园活动报名与管理系统
echo  正在启动，请在浏览器打开 http://127.0.0.1:5000
echo  按 Ctrl+C 可停止服务
echo ============================================
".venv\Scripts\python.exe" app.py
pause
