# Start Alice Hub with E4 Hub-only Jira (production default)
$ErrorActionPreference = "Stop"
$env:ALICE_HUB_ONLY_JIRA = "1"
$env:PYTHONIOENCODING = "utf-8"
Set-Location (Join-Path $PSScriptRoot "..\backend")
Write-Host "[Alice] ALICE_HUB_ONLY_JIRA=1 — starting ai_bridge on :9099"
py -3 ai_bridge.py
