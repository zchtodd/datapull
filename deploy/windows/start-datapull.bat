@echo off
REM ============================================================================
REM Start datapull natively (no Docker): web + Celery worker + beat.
REM
REM Run this by DOUBLE-CLICKING it or from a cmd/PowerShell prompt IN YOUR RDP
REM SESSION -- the browser jobs run headed and need the interactive desktop.
REM Batch files are NOT subject to PowerShell execution policy.
REM ============================================================================
setlocal

REM Go to the repo root (this file lives in deploy\windows\).
cd /d "%~dp0..\.."

set "PY=%CD%\.venv\Scripts\python.exe"

if not exist "%PY%" (
  echo ERROR: %PY% not found.
  echo Create the venv first:  python -m venv .venv  ^&^&  .venv\Scripts\python.exe -m pip install -r requirements.txt
  pause
  exit /b 1
)
if not exist ".env" (
  echo ERROR: .env not found in %CD%.
  echo Copy deploy\windows\.env.native.example to .env and fill it in first.
  pause
  exit /b 1
)

REM Load .env into the environment. KEY=VALUE lines; '#' comment lines skipped.
REM tokens=1,* keeps the whole value after the first '=' (URLs, base64 '=' pad).
for /f "usebackq eol=# tokens=1,* delims==" %%A in (".env") do set "%%A=%%B"

REM This box runs jobs as native subprocesses, not containers.
set "DATAPULL_LAUNCHER=native"

echo Starting datapull from %CD% ...
start "datapull web"    "%PY%" serve.py
start "datapull worker" "%PY%" -m celery -A celery_worker.celery_app worker --loglevel=info --pool=threads --concurrency=4
start "datapull beat"   "%PY%" -m celery -A celery_worker.celery_app beat --loglevel=info --schedule "%TEMP%\celerybeat-schedule"

echo.
echo datapull started in 3 windows.  Open http://localhost:5000/
echo To stop: close those 3 windows (titled "datapull web/worker/beat").
endlocal
