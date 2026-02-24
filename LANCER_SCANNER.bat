@echo off
title Scanner Qualite - Lancement automatique
color 0A

:: 1. S'assurer qu'on est dans le bon dossier (celui du script)
cd /d "%~dp0"

echo ======================================================
echo      LANCEMENT DE L'OUTIL SCANNER QUALITE
echo ======================================================
echo.

:: (Optionnel) Activation de l'environnement virtuel s'il existe
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
)

echo [1/2] Verification / Installation des dependances (Patientez quelques secondes)...
python -m pip install -r requirements.txt --quiet --disable-pip-version-check


echo [2/2] Demarrage de l'application...
echo.
echo L'application est prete a scanner !
echo.
python src/scanner_app.py

echo.
echo [FIN] Application terminee.
pause
