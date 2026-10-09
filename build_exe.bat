@echo off
cd /d C:\Users\abezille\dev\fiche_de_controle
.venv\Scripts\python.exe -m PyInstaller --noconfirm --log-level=WARN --distpath dist --workpath build deploy\Scanner_Qualite.spec > build.log 2>&1
echo EXIT=%ERRORLEVEL% >> build.log
