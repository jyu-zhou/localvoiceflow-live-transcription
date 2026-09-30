@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Install LocalVoiceFlow.ps1" %*
endlocal
