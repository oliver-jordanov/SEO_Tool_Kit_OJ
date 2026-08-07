@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo First run: executing setup.bat
  call setup.bat || exit /b 1
)
call ".venv\Scripts\activate.bat"
alembic upgrade head || exit /b 1
start "" "http://127.0.0.1:8765"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8765

