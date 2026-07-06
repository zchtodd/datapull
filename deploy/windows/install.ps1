# One-time native setup for datapull on a Windows VM (no Docker, no reboot).
# Run from the repo root in your RDP session:  .\deploy\windows\install.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)   # deploy\windows -> repo root
Set-Location $root
Write-Host "datapull repo: $root"

# 1. Python virtual environment + dependencies.
if (-not (Test-Path .\.venv)) { python -m venv .venv }
$py = ".\.venv\Scripts\python.exe"
& $py -m pip install --upgrade pip
# Behind corporate TLS interception, add:  --cert C:\certs\corp-root.pem
& $py -m pip install -r requirements.txt

# 2. Playwright's Chromium (~150 MB download; needs egress / corp CA trusted).
& $py -m playwright install chromium

Write-Host ""
Write-Host "Install step done. Confirm these prerequisites manually:" -ForegroundColor Cyan
Write-Host "  * Microsoft ODBC Driver 18 for SQL Server installed (pyodbc needs it)"
Write-Host "  * Memurai (Windows-native Redis) installed and running on localhost:6379"
Write-Host "  * External SQL Server reachable, and the 'datapull' database created"
Write-Host "  * .env created from deploy\windows\.env.native.example (fresh keys!)"
Write-Host ""
Write-Host "Then initialize and start:" -ForegroundColor Cyan
Write-Host "  .\deploy\windows\dbupgrade.ps1        # apply migrations + bootstrap admin"
Write-Host "  .\deploy\windows\start-datapull.ps1   # launch web + worker + beat"
