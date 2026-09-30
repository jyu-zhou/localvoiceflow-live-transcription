$ErrorActionPreference = "Stop"
$RootDir = Split-Path -Parent $MyInvocation.MyCommand.Path
& (Join-Path $RootDir "scripts\install.ps1") -DesktopShortcut
Read-Host "Press Enter to close"
