@echo off
echo ==========================================
echo      LANCEMENT DE INVENTAIRE AI (DEV)
echo ==========================================
echo.

:: Launch the main GUI launcher
py -3.12 app.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERREUR] L'application s'est fermee avec une erreur.
    echo Essayez 'python app.py' si 'py -3.12' ne fonctionne pas.
    pause
)
