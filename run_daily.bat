@echo off
REM ============================================
REM  中证500每日复盘分析 - 手动启动脚本
REM  用法: 双击运行, 或添加到 Windows 任务计划程序
REM ============================================
cd /d "%~dp0"
call .\venv\Scripts\activate.bat
set PYTHONIOENCODING=utf-8
python main.py
pause
