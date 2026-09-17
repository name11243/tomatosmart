@echo off
setlocal
chcp 65001 >nul
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\change-ip.ps1"
set "change_ip_result=%errorlevel%"
echo.
pause
exit /b %change_ip_result%
