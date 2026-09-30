param(
    [switch]$DesktopShortcut,
    [string]$PythonPath = $env:PYTHON_BIN
)

$ErrorActionPreference = "Stop"

$RootDir = Split-Path -Parent $PSScriptRoot
$RequirementsPath = Join-Path $RootDir "requirements-windows.txt"

if (-not $PythonPath) {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3.12 -c "import sys" 2>$null
        if ($LASTEXITCODE -eq 0) {
            $PythonPath = "py -3.12"
        } else {
            & py -3.11 -c "import sys" 2>$null
            if ($LASTEXITCODE -eq 0) {
                $PythonPath = "py -3.11"
            }
        }
    } else {
        $PythonPath = (Get-Command python -ErrorAction SilentlyContinue).Source
    }
}

if (-not $PythonPath) {
    throw "Python 3.11 or 3.12 was not found. Install Python from python.org and run this installer again."
}

function Invoke-Python {
    param([string[]]$Arguments)
    if ($PythonPath -match '^py (-3\.(11|12))$') {
        & py $Matches[1] @Arguments
    } else {
        & $PythonPath @Arguments
    }
}

$Version = (Invoke-Python @("-c", "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"))
if ($Version -notin @("3.11", "3.12")) {
    throw "LocalVoiceFlow requires Python 3.11 or 3.12; found $Version. Set PYTHON_BIN to a compatible interpreter if needed."
}

Invoke-Python @("-c", "import tkinter")
if ($LASTEXITCODE -ne 0) {
    throw "The selected Python does not include Tk support. Install a Python build with Tk and try again."
}

$VenvPython = Join-Path $RootDir ".venv\Scripts\python.exe"
Write-Host "Creating the LocalVoiceFlow Python environment with Python $Version..."
Invoke-Python @("-m", "venv", (Join-Path $RootDir ".venv"))
if ($LASTEXITCODE -ne 0) { throw "Could not create the Python virtual environment." }
& $VenvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "Could not upgrade pip." }
& $VenvPython -m pip install -r $RequirementsPath
if ($LASTEXITCODE -ne 0) { throw "Could not install the Windows dependencies." }
& $VenvPython -m pip check
if ($LASTEXITCODE -ne 0) { throw "The installed dependencies did not pass pip check." }

$DataRoot = if ($env:LOCALVOICEFLOW_DATA_DIR) { $env:LOCALVOICEFLOW_DATA_DIR } else { Join-Path $env:USERPROFILE "Documents\LocalVoiceFlow" }
$CacheRoot = if ($env:LOCALVOICEFLOW_CACHE_DIR) { $env:LOCALVOICEFLOW_CACHE_DIR } else { Join-Path $env:LOCALAPPDATA "LocalVoiceFlow" }
New-Item -ItemType Directory -Force -Path $DataRoot, (Join-Path $CacheRoot "huggingface") | Out-Null

if ($DesktopShortcut) {
    $Desktop = [Environment]::GetFolderPath("Desktop")
    $ShortcutPath = Join-Path $Desktop "LocalVoiceFlow.lnk"
    $Index = 1
    while (Test-Path $ShortcutPath) {
        $Index++
        $ShortcutPath = Join-Path $Desktop "LocalVoiceFlow ($Index).lnk"
    }

    $Shell = New-Object -ComObject WScript.Shell
    $Shortcut = $Shell.CreateShortcut($ShortcutPath)
    $Shortcut.TargetPath = (Join-Path $RootDir "LocalVoiceFlow.cmd")
    $Shortcut.WorkingDirectory = $RootDir
    $Shortcut.Description = "LocalVoiceFlow — local live transcription"
    $Shortcut.Save()
    Write-Host "Desktop shortcut created: $ShortcutPath"
}

Write-Host ""
Write-Host "LocalVoiceFlow is installed."
Write-Host "First launch downloads the selected Qwen3-ASR GGUF model from Hugging Face."
Write-Host "Run .\LocalVoiceFlow.cmd or use the Desktop shortcut."
