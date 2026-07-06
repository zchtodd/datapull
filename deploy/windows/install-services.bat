@echo off
REM ============================================================================
REM Register datapull as Windows services via NSSM (headless, session 0 — so it
REM survives sign-out and reboots, no interactive desktop needed).
REM
REM RUN AS ADMINISTRATOR. Prerequisites:
REM   * nssm.exe on PATH            (https://nssm.cc)
REM   * .venv created + deps installed, .env present at the repo root
REM   * .env has PARAM_HEADED=false and PLAYWRIGHT_BROWSERS_PATH set, and you ran
REM     `playwright install chromium` with that PLAYWRIGHT_BROWSERS_PATH set
REM   * Memurai + external SQL Server reachable
REM ============================================================================
setlocal
cd /d "%~dp0..\.."
set "ROOT=%CD%"
set "PY=%ROOT%\.venv\Scripts\python.exe"
set "NSSM=nssm"

if not exist "%PY%" ( echo ERROR: venv python not found at %PY% & pause & exit /b 1 )
if not exist "%ROOT%\.env" ( echo ERROR: .env not found in %ROOT% & pause & exit /b 1 )
where %NSSM% >nul 2>&1 || ( echo ERROR: nssm not on PATH. Get it from https://nssm.cc & pause & exit /b 1 )
if not exist "%ROOT%\logs" mkdir "%ROOT%\logs"

REM --- web (waitress via serve.py) ---
%NSSM% install datapull-web "%PY%" serve.py
%NSSM% set datapull-web AppDirectory "%ROOT%"
%NSSM% set datapull-web AppStdout "%ROOT%\logs\web.log"
%NSSM% set datapull-web AppStderr "%ROOT%\logs\web.log"
%NSSM% set datapull-web Start SERVICE_AUTO_START
%NSSM% set datapull-web AppExit Default Restart

REM --- worker (spawns the headless browser subprocesses) ---
%NSSM% install datapull-worker "%PY%" -m celery -A celery_worker.celery_app worker --loglevel=info --pool=threads --concurrency=4
%NSSM% set datapull-worker AppDirectory "%ROOT%"
%NSSM% set datapull-worker AppStdout "%ROOT%\logs\worker.log"
%NSSM% set datapull-worker AppStderr "%ROOT%\logs\worker.log"
%NSSM% set datapull-worker Start SERVICE_AUTO_START
%NSSM% set datapull-worker AppExit Default Restart
%NSSM% set datapull-worker DependOnService Memurai

REM --- beat (scheduler tick) ---
%NSSM% install datapull-beat "%PY%" -m celery -A celery_worker.celery_app beat --loglevel=info --schedule "%ROOT%\logs\celerybeat-schedule"
%NSSM% set datapull-beat AppDirectory "%ROOT%"
%NSSM% set datapull-beat AppStdout "%ROOT%\logs\beat.log"
%NSSM% set datapull-beat AppStderr "%ROOT%\logs\beat.log"
%NSSM% set datapull-beat Start SERVICE_AUTO_START
%NSSM% set datapull-beat AppExit Default Restart
%NSSM% set datapull-beat DependOnService Memurai

%NSSM% start datapull-web
%NSSM% start datapull-worker
%NSSM% start datapull-beat

echo.
echo Installed + started: datapull-web, datapull-worker, datapull-beat
echo   config: the services load .env from %ROOT% automatically (AppDirectory)
echo   logs:   %ROOT%\logs\{web,worker,beat}.log
echo   manage: nssm restart datapull-worker  ^|  sc query datapull-web  ^|  nssm status datapull-web
endlocal
