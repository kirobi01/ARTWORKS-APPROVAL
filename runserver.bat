@echo off
REM Run the Kapa Artwork Approval System (always uses project venv)
cd /d "%~dp0"
set DJANGO_SETTINGS_MODULE=config.settings.development
set PYTHONPATH=%CD%

if not exist "venv\Scripts\python.exe" (
    echo Virtual environment not found. Running setup.bat...
    call "%~dp0setup.bat"
)

set PY=venv\Scripts\python.exe

REM Kill stale runserver instances (e.g. old PerformanceMS on port 8000)
call "%~dp0stopserver.bat"

REM Ensure PostgreSQL driver is present
%PY% -c "import psycopg" 2>nul
if errorlevel 1 (
    %PY% -c "import psycopg2" 2>nul
    if errorlevel 1 (
        echo Installing PostgreSQL driver...
        %PY% -m pip install "psycopg[binary]>=3.1" psycopg2-binary
    )
)

echo.
echo Project: %CD%
%PY% -c "import os,sys; os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings.development'); sys.path.insert(0,r'%CD%'); import django; django.setup(); from django.conf import settings; print('Settings:', settings.SETTINGS_MODULE); print('URLconf: ', settings.ROOT_URLCONF)"
echo.

%PY% manage.py migrate
%PY% manage.py dedupe_users
%PY% manage.py runserver %*
