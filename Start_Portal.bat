@echo off
echo ========================================================
echo 🚀 Starte PM Evidence AI Portal (Initialisierung...)
echo ========================================================

:: Zwingt die Datei, genau dort zu arbeiten, wo sie entpackt wurde
cd /d "%~dp0"

:: Prüft, ob der Ordner den Google-Schlüssel hat
IF NOT EXIST "gcp-key.json" (
    echo 🛑 FEHLER: Die Datei 'gcp-key.json' fehlt in diesem Ordner!
    echo Bitte frage den Product Manager nach dem Google Cloud Schluessel.
    pause
    exit
)

:: Baut beim ersten Start automatisch die sichere Python-Umgebung beim Kollegen!
IF NOT EXIST "venv" (
    echo ⚙️  Erstes Setup: Baue virtuelle Python-Umgebung auf deinem Rechner...
    python -m venv venv
)

:: Umgebung aktivieren
call venv\Scripts\activate.bat
set PYTHONIOENCODING=utf-8

:: Installiert vollautomatisch alle Pakete aus deiner requirements.txt
echo 📦 Pruefe Software-Pakete im Hintergrund...
pip install -r requirements.txt -q

echo 🦙 Pruefe / starte Ollama...
python -c "from core.ollama_runtime import ensure_ollama_running; ensure_ollama_running()"

echo.
echo 🌟 Alles bereit! Das Portal oeffnet sich jetzt im Browser...
streamlit run "PM Evidence AI Portal\Home.py"
pause