# Start datapull natively (no Docker): web (waitress) + Celery worker + beat.
#
# RUN THIS IN YOUR INTERACTIVE RDP SESSION, not as a session-0 service —
# the browser jobs run HEADED and need the interactive desktop to draw on.
#
#   .\deploy\windows\start-datapull.ps1
. (Join-Path $PSScriptRoot "_env.ps1")
Set-Location $DatapullRoot

$waitress = ".\.venv\Scripts\waitress-serve.exe"
$celery   = ".\.venv\Scripts\celery.exe"
$beatFile = Join-Path $env:TEMP "celerybeat-schedule"

# Web / JSON API / operator console. Front with a TLS reverse proxy for real use.
Start-Process -FilePath $waitress `
  -ArgumentList "--listen=0.0.0.0:5000", "wsgi:app" `
  -WorkingDirectory $DatapullRoot -WindowStyle Minimized

# Celery worker: threads pool works on Windows and each thread just spawns +
# monitors a browser subprocess (the actual Chromium is a child process).
Start-Process -FilePath $celery `
  -ArgumentList "-A", "celery_worker.celery_app", "worker", "--loglevel=info", "--pool=threads", "--concurrency=4" `
  -WorkingDirectory $DatapullRoot -WindowStyle Minimized

# Celery beat: fires the once-a-minute scheduler tick.
Start-Process -FilePath $celery `
  -ArgumentList "-A", "celery_worker.celery_app", "beat", "--loglevel=info", "--schedule", $beatFile `
  -WorkingDirectory $DatapullRoot -WindowStyle Minimized

Write-Host "datapull started:" -ForegroundColor Green
Write-Host "  web    -> http://localhost:5000/"
Write-Host "  worker -> Celery (threads pool); browser jobs run headed on this desktop"
Write-Host "  beat   -> scheduler tick"
Write-Host "Stop with:  Get-Process waitress-serve,celery | Stop-Process"
