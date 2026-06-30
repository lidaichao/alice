@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo [AliceV2] Starting Hub...
echo [AliceV2] Health: http://127.0.0.1:3000/health
npm start
pause
