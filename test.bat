@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 正在运行自动化测试（C1-C10 + 边界用例）...
".venv\Scripts\python.exe" -m pytest -q
pause
