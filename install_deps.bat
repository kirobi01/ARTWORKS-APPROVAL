@echo off
REM Refresh Python packages in the project venv (run setup.bat for first-time setup)
cd /d "%~dp0"

if not exist "venv\Scripts\python.exe" (
    echo No venv found. Running setup.bat...
    call "%~dp0setup.bat"
    exit /b %errorlevel%
)

echo Refreshing dependencies in %CD%\venv
venv\Scripts\python.exe -m pip install --upgrade pip
venv\Scripts\python.exe -m pip install -r requirements.txt
echo.
echo Done. Run runserver.bat to start the app.
pause
