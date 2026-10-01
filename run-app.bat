@echo off
setlocal
cd /d "%~dp0stegastiko"

where python >nul 2>&1
if errorlevel 1 (
    echo Python was not found on PATH. Install Python 3.13+ and try again.
    pause
    exit /b 1
)

echo Housing Scheme (stegastiko)
echo   Home:         http://127.0.0.1:8000/
echo   Admin:        http://127.0.0.1:8000/admin/
echo   Applications: http://127.0.0.1:8000/applications/
echo.
echo Press Ctrl+C to stop the server.
echo.

REM Django default is 8000 — port 8080 is often used by other tools (e.g. Node) on this machine.
python manage.py runserver 127.0.0.1:8000
pause
