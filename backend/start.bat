@echo off
echo ============================================
echo   WeCom-Jira Bridge Service
echo ============================================
echo.

REM 检查 .env 文件是否存在
if not exist .env (
    echo [ERROR] .env file not found!
    echo Please copy .env.example to .env and fill in your configuration.
    pause
    exit /b 1
)

REM 设置 Python 路径
set PYTHON=C:\Users\Administrator\.workbuddy\binaries\python\envs\default\Scripts\python.exe

REM 安装依赖
echo [1/2] Installing dependencies...
%PYTHON% -m pip install -r requirements.txt -q

REM 启动服务
echo [2/2] Starting server...
echo.
%PYTHON% ai_bridge.py

pause
