@echo off
REM First-time setup: create venv, install deps, run migrations
cd /d "%~dp0"

echo === Kapa Artwork Approval System — setup ===
echo.

if exist "venv\Scripts\python.exe" (
    echo Virtual environment already exists at %CD%\venv
    set /p RECREATE="Recreate venv from scratch? (y/N): "
    if /I "%RECREATE%"=="Y" (
        echo Removing old venv...
        rmdir /s /q venv
    )
)

if not exist "venv\Scripts\python.exe" (
    echo Creating virtual environment...
    where py >nul 2>&1
    if %errorlevel%==0 (
        py -3.11 -m venv venv 2>nul
        if errorlevel 1 py -3 -m venv venv
    ) else (
        python -m venv venv
    )
    if not exist "venv\Scripts\python.exe" (
        echo ERROR: Could not create venv. Install Python 3.11+ and try again.
        pause
        exit /b 1
    )
)

echo.
echo Installing dependencies...
venv\Scripts\python.exe -m pip install --upgrade pip
venv\Scripts\python.exe -m pip install -r requirements.txt

if not exist ".env" (
    if exist ".env.example" (
        echo Copying .env.example to .env — edit DB and LDAP settings before production use.
        copy /Y .env.example .env >nul
    )
)

set DJANGO_SETTINGS_MODULE=config.settings.development
set PYTHONPATH=%CD%

echo.
echo Running migrations...
venv\Scripts\python.exe manage.py migrate
venv\Scripts\python.exe manage.py dedupe_users

echo.
echo === Setup complete ===
echo.
echo   Activate:  venv\Scripts\activate
echo   Run app:   runserver.bat
echo   Or:        venv\Scripts\python.exe manage.py runserver
echo.
pause
