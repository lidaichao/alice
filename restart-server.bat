@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo [AliceV2] Restarting Hub...
taskkill /F /IM node.exe 2>nul
timeout /t 2 >nul
start "AliceV2 Hub" /B npm start
echo [AliceV2] Hub restarted. Check http://127.0.0.1:3000/health
pause
