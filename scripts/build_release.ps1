# Alice Jira AI — Windows release build (Backend PyInstaller + Frontend Vite + Electron)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$env:PYTHONIOENCODING = "utf-8"

Write-Host "========================================"
Write-Host "  Alice Jira AI — Release Build (Windows)"
Write-Host "========================================"

# Step 1: Backend
Write-Host "`n[1/3] Backend PyInstaller..."
Push-Location (Join-Path $Root "backend")
py -3 -m pip install -q -r requirements.txt 2>$null
py -3 -m PyInstaller --noconfirm --onedir --windowed --name ai_bridge `
  --add-data "tools;tools" --add-data "skills;skills" --add-data "logic;logic" `
  --hidden-import flask --hidden-import flask_cors --hidden-import waitress --hidden-import yaml `
  ai_bridge.py
Pop-Location

# Step 2: Frontend
Write-Host "`n[2/3] Frontend Vite..."
Push-Location (Join-Path $Root "frontend")
npm install --silent
npm run build
Pop-Location

# Step 3: Desktop
Write-Host "`n[3/3] Electron pack..."
Push-Location (Join-Path $Root "desktop")
npm install --silent
npm run dist:win
Pop-Location

Write-Host "`nDone. Artifacts: $Root\desktop\dist\"
