# Shared helper: load .env into the current process environment and force
# native launcher mode. Dot-sourced by the other scripts:  . .\deploy\windows\_env.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)   # deploy\windows -> repo root

$envFile = Join-Path $root ".env"
if (Test-Path $envFile) {
  Get-Content $envFile | ForEach-Object {
    $line = $_.Trim()
    if ($line -and -not $line.StartsWith("#") -and $line.Contains("=")) {
      $parts = $line.Split("=", 2)
      [Environment]::SetEnvironmentVariable($parts[0].Trim(), $parts[1].Trim())
    }
  }
} else {
  Write-Warning "No .env found at $envFile — services will use defaults / may fail."
}

# This box runs jobs as native subprocesses, not containers.
[Environment]::SetEnvironmentVariable("DATAPULL_LAUNCHER", "native")
$script:DatapullRoot = $root
