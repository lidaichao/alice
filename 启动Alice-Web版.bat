@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo.
echo ╔════════════════════════════════════╗
echo ║     Alice Local Hub               ║
echo ║     启动中...                     ║
echo ╚════════════════════════════════════╝
echo.
set NODE_OPTIONS=
node src\server.js
echo.
echo 服务端已停止。
pause
