@echo off
rem Builds dist\network_diag.exe (single file, console app with custom icon). Run from the project folder.
setlocal
cd /d "%~dp0"

echo Installing build tools (pyinstaller, speedtest-cli)...
python -m pip install --upgrade pip pyinstaller speedtest-cli || goto :error

echo.
echo Building network_diag.exe ...
python -m PyInstaller --noconfirm --clean --onefile --console --name network_diag --icon=app_icon.ico --hidden-import speedtest network_diag.py || goto :error

echo.
echo Done: dist\network_diag.exe
pause
exit /b 0

:error
echo.
echo BUILD FAILED - read the messages above.
pause
exit /b 1
