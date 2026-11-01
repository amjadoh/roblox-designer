@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist requirements.txt (
  echo ERROR: requirements.txt not found next to run.bat.
  echo You probably ran run.bat from inside the ZIP. Right-click the ZIP, choose Extract All, then open run.bat from the extracted folder.
  pause & exit /b 1
)
if not exist app\main.py (
  echo ERROR: app folder missing. Extract the whole ZIP first.
  pause & exit /b 1
)
set PY=
where py >nul 2>nul && set PY=py -3
if "%PY%"=="" where python >nul 2>nul && set PY=python
if "%PY%"=="" (
  echo Python is not installed. Install Python 3.11-3.13 from python.org with "Add to PATH", then run again.
  pause & exit /b 1
)
%PY% --version
if not exist .venv\Scripts\python.exe (
  %PY% -m venv .venv || (echo venv failed & pause & exit /b 1)
)
call .venv\Scripts\activate
python -m pip install --upgrade pip >nul 2>nul
pip install -r requirements.txt > install.log 2>&1
if errorlevel 1 (
  echo.
  echo Package install FAILED. Last lines of install.log:
  powershell -NoProfile -Command "Get-Content install.log -Tail 15"
  echo.
  echo Send this window's text to Claude.
  pause & exit /b 1
)
echo Starting server... browser opens in 4 seconds.
start "" /b powershell -NoProfile -Command "Start-Sleep 4; Start-Process 'http://127.0.0.1:8765'"
python -m app.vendor_fetch
python -m uvicorn app.main:app --host 127.0.0.1 --port 8765
echo.
echo Server stopped. Read the messages above for the error.
pause
