@echo off
cd /d %~dp0
set PY=python
where py >nul 2>nul && set PY=py -3
if not exist .venv\Scripts\python.exe (
  echo First run: installing packages, this takes a minute...
  %PY% -m venv .venv || goto fail
  .venv\Scripts\python -m pip install -r requirements.txt || goto fail
)
.venv\Scripts\python run.py %*
if errorlevel 1 goto fail
goto end
:fail
echo.
echo Something went wrong. Check Python 3.10 or newer is installed ("python --version") and you are online for the first run.
pause
:end
