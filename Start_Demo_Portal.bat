@echo off
echo ========================================================
echo Demo-Modus — PM Evidence AI Portal (synthetische Daten)
echo ========================================================

cd /d "%~dp0"

where git >nul 2>&1
if %ERRORLEVEL%==0 (
    git rev-parse --verify demo/public >nul 2>&1
    if %ERRORLEVEL%==0 (
        for /f "delims=" %%B in ('git branch --show-current') do set CURRENT_BRANCH=%%B
        if /I not "%CURRENT_BRANCH%"=="demo/public" (
            echo Wechsle auf Branch demo/public fuer synthetische Demo-Daten...
            git checkout demo/public
        )
    )
)

IF NOT EXIST "venv" (
    echo Erstes Setup: virtuelle Python-Umgebung...
    python -m venv venv
)

call venv\Scripts\activate.bat
set PYTHONIOENCODING=utf-8
set DEMO_MODE=true

echo Pakete pruefen...
pip install -r requirements.txt -q

echo.
echo Demo startet — kein gcp-key.json noetig.
streamlit run "PM Evidence AI Portal\Home.py"
pause
