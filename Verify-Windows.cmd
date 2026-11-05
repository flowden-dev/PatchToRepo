@echo off
setlocal DisableDelayedExpansion
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\Verify.ps1" -IncludeCompiled %*
set "VERIFY_RESULT=%ERRORLEVEL%"
if not "%VERIFY_RESULT%"=="0" echo Verification failed. Read the messages and build\test-logs.
pause
exit /b %VERIFY_RESULT%
