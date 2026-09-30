@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0LocalVoiceFlow.ps1" %*
endlocal
