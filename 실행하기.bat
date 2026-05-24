@echo off
cd /d "%~dp0"
if exist "%~dp0.venv\Scripts\pythonw.exe" (
    start "" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0app.py"
    exit
)
where pythonw.exe >nul 2>nul
if %errorlevel%==0 (
    start "" pythonw.exe "%~dp0app.py"
    exit
)
where pyw.exe >nul 2>nul
if %errorlevel%==0 (
    start "" pyw.exe "%~dp0app.py"
    exit
)
where py.exe >nul 2>nul
if %errorlevel%==0 (
    start "" py.exe -3 "%~dp0app.py"
) else (
    start "" python.exe "%~dp0app.py"
)
exit
