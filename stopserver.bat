@echo off
REM Stop Django dev servers listening on port 8000 (stale PerformanceMS / duplicate runserver)
echo Stopping processes listening on port 8000...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0stopserver.ps1"
echo Done.
