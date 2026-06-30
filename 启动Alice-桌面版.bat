@echo off
chcp 65001 >nul
cd /d "H:\workbuddy\baize"
echo.
echo ╔════════════════════════════════════╗
echo ║     Alice Baize Desktop           ║
echo ║     启动 Electron 桌面客户端...   ║
echo ╚════════════════════════════════════╝
echo.
echo 注意：需要先启动服务端(启动Alice-Web版.bat)
echo.
set NODE_OPTIONS=
npx electron client/desktop/main.cjs
echo.
pause
