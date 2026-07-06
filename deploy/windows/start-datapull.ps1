# Start datapull natively (no Docker): web (waitress) + Celery worker + beat.
#
# RUN THIS IN YOUR INTERACTIVE RDP SESSION, not as a session-0 service —
# the browser jobs run HEADED and need the interactive desktop to draw on.
#
#   .\deploy\windows\start-datapull.ps1
. (Join-Path $PSScriptRoot "_env.ps1")
Set-Location $DatapullRoot

# Use the venv's python directly (absolute path) — NOT the pip-generated
# waitress-serve.exe / celery.exe console-script shims, which fail with "cannot
# find the file specified" when the venv came from Microsoft Store Python.
$py       = Join-Path $DatapullRoot ".venv\Scripts\python.exe"
$beatFile = Join-Path $env:TEMP "celerybeat-schedule"

# Web / JSON API / operator console (waitress via serve.py). Front with a TLS
# reverse proxy for real use.
$web = Start-Process -FilePath $py -PassThru `
  -ArgumentList "serve.py" `
  -WorkingDirectory $DatapullRoot -WindowStyle Minimized

# Celery worker: threads pool works on Windows and each thread just spawns +
# monitors a browser subprocess (the actual Chromium is a child process).
$worker = Start-Process -FilePath $py -PassThru `
  -ArgumentList "-m", "celery", "-A", "celery_worker.celery_app", "worker", "--loglevel=info", "--pool=threads", "--concurrency=4" `
  -WorkingDirectory $DatapullRoot -WindowStyle Minimized

# Celery beat: fires the once-a-minute scheduler tick.
$beat = Start-Process -FilePath $py -PassThru `
  -ArgumentList "-m", "celery", "-A", "celery_worker.celery_app", "beat", "--loglevel=info", "--schedule", $beatFile `
  -WorkingDirectory $DatapullRoot -WindowStyle Minimized

# Record the PIDs so they can be stopped without killing every python.exe.
"$($web.Id) $($worker.Id) $($beat.Id)" | Set-Content (Join-Path $DatapullRoot ".datapull-pids")

Write-Host "datapull started:" -ForegroundColor Green
Write-Host "  web    (pid $($web.Id))    -> http://localhost:5000/"
Write-Host "  worker (pid $($worker.Id)) -> Celery (threads pool); browser jobs run headed on this desktop"
Write-Host "  beat   (pid $($beat.Id))   -> scheduler tick"
Write-Host "Stop with:  Stop-Process -Id $($web.Id),$($worker.Id),$($beat.Id)"
