@echo off
cd /d "%~dp0"

REM Auto-restore if electron was left in _e from previous crash
if exist "node_modules\_e" (
    move "node_modules\_e" "node_modules\electron" >nul 2>&1
)

set E=node_modules\electron\dist\electron.exe
if not exist "%E%" (
    echo [ERR] Electron not found! Run: npm install
    pause
    exit /b 1
)

echo Starting Alice Jira AI...
echo.

move node_modules\electron node_modules\_e >nul 2>&1
if not exist "node_modules\_e\dist\electron.exe" (
    echo [ERR] Cannot move electron folder.
    pause
    exit /b 1
)

"node_modules\_e\dist\electron.exe" main.js
set EC=%errorlevel%

move node_modules\_e node_modules\electron >nul 2>&1

if %EC% neq 0 (
    echo.
    echo [ERR] Exit code: %EC%
    echo Make sure AI Bridge backend is running on http://127.0.0.1:9099
    pause
)
