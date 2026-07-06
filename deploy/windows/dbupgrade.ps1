# Apply DB migrations and create the operator login. Run once after install
# (and again after any update that adds migrations).
. (Join-Path $PSScriptRoot "_env.ps1")
Set-Location $DatapullRoot
$py = ".\.venv\Scripts\python.exe"

& $py -m flask --app wsgi db upgrade
& $py -m flask --app wsgi bootstrap-admin
