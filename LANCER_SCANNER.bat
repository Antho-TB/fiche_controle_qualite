@echo off
title Scanner Qualite - Lancement automatique
color 0A

echo ======================================================
echo      LANCEMENT DE L'OUTIL SCANNER QUALITE
echo ======================================================
echo.
echo [1/2] Verification des dependances...
python -m pip install -r requirements.txt --quiet

echo [2/2] Demarrage de l'application...
echo.
python src/scanner_app.py

echo.
echo Application terminee.
pause
