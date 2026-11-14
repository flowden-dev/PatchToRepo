@echo off
setlocal
where py.exe >nul 2>&1
if errorlevel 1 goto usepython
for %%V in (3.12 3.13 3.11) do (
    py -%%V -c "import struct; assert struct.calcsize('P') == 8" >nul 2>&1
    if not errorlevel 1 (
        py -%%V "%~dp0scripts\bootstrap_build.py"
        goto done
    )
)
:usepython
python "%~dp0scripts\bootstrap_build.py"
:done
if errorlevel 1 (
    echo.
    echo Operation failed. Review the error above. Python 3.12 x64 is recommended.
    pause
    exit /b 1
)
echo Build complete. See the dist folder.
pause
