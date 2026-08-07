@echo off
setlocal
cd /d "%~dp0"
python -c "import sys; assert sys.version_info >= (3,12), 'Python 3.12+ required'" || exit /b 1
python -m venv .venv || exit /b 1
call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip || exit /b 1
python -m pip install -e ".[dev]" || exit /b 1
if not exist ".env" copy ".env.example" ".env" >nul
alembic upgrade head || exit /b 1
echo Setup complete. Add API credentials to .env, then run start.bat.

