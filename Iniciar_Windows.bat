@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" py -3 -m venv .venv
if errorlevel 1 goto erro
call ".venv\Scripts\activate.bat"
python -m pip install -r requirements.txt
if errorlevel 1 goto erro
python -m streamlit run app.py
pause
exit /b
:erro
echo Nao foi possivel iniciar. Confira a instalacao do Python 3.11 ou superior.
pause
