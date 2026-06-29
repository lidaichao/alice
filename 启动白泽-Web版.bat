@echo off
chcp 65001 >nul
cd /d "H:\workbuddy\baize"
echo.
echo ╔════════════════════════════════════╗
echo ║     白泽 Baize Local Hub         ║
echo ║     启动中...                     ║
echo ╚════════════════════════════════════╝
echo.
set NODE_OPTIONS=
node src\server.js
echo.
echo 服务端已停止。
pause
