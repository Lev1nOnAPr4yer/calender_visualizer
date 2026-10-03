@echo off
REM Builds dist\CalendarVisualizer.exe on Windows. Requires Python 3.10+ on PATH.
cd /d "%~dp0"
python -m venv .venv || goto :error
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements-dev.txt || goto :error
python -m pytest -q || goto :error
pyinstaller --noconfirm --clean calviz.spec || goto :error
echo.
echo Done: dist\CalendarVisualizer.exe
goto :eof
:error
echo Build failed.
exit /b 1
