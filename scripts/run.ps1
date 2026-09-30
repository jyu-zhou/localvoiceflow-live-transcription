$ErrorActionPreference = "Stop"

$RootDir = Split-Path -Parent $PSScriptRoot
$PythonPath = Join-Path $RootDir ".venv\Scripts\python.exe"

if (-not (Test-Path $PythonPath)) {
    Write-Error "LocalVoiceFlow is not installed. Run .\scripts\install.ps1 -DesktopShortcut first."
}

$DataRoot = if ($env:LOCALVOICEFLOW_DATA_DIR) { $env:LOCALVOICEFLOW_DATA_DIR } else { Join-Path $env:USERPROFILE "Documents\LocalVoiceFlow" }
$CacheRoot = if ($env:LOCALVOICEFLOW_CACHE_DIR) { $env:LOCALVOICEFLOW_CACHE_DIR } else { Join-Path $env:LOCALAPPDATA "LocalVoiceFlow" }
$env:LOCALVOICEFLOW_DATA_DIR = $DataRoot
$env:LOCALVOICEFLOW_CACHE_DIR = $CacheRoot
$env:HF_HOME = if ($env:HF_HOME) { $env:HF_HOME } else { Join-Path $CacheRoot "huggingface" }

& $PythonPath (Join-Path $RootDir "src\macvoiceflow\realtime_app.py") @args
