@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo.
echo  Alice 协调者评测 - 正在运行，请稍候...
echo.
py -3 scripts\run_coordinator_eval.py
if errorlevel 1 (
  echo.
  echo 运行出错。若提示找不到 py，请先安装 Python 3。
  pause
  exit /b 1
)
echo.
echo 报告已生成: eval\reports\协调者报告_latest.md
echo.
pause
