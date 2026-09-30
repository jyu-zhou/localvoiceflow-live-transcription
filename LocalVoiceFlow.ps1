$ErrorActionPreference = "Stop"
$RootDir = Split-Path -Parent $MyInvocation.MyCommand.Path

if (-not (Test-Path (Join-Path $RootDir ".venv\Scripts\python.exe"))) {
    & (Join-Path $RootDir "scripts\install.ps1") -DesktopShortcut
}

& (Join-Path $RootDir "scripts\run.ps1") @args
