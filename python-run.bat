@echo off

REM Change directory to the folder this batch file is in
cd /d "%~dp0"

REM Activate the virtual environment
call venv\Scripts\activate

REM Run the Python entry point
python main.py

REM Wait for keypress before closing
pause
