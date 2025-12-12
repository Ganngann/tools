@echo off
echo ==========================================
echo      REVISION MANUELLE INVENTAIRE
echo ==========================================
echo.

:: Check if a file was dragged onto the script
if "%~1"=="" (
    echo Veuillez glisser-deposer le fichier CSV de l'inventaire ci-dessous
    echo et appuyez sur ENTREE.
    echo.
    set /p file_path="Fichier CSV > "
) else (
    set file_path=%1
)

:: Remove quotes if present
set file_path=%file_path:"=%

if "%file_path%"=="" (
    echo.
    echo [ERREUR] Aucun fichier selectionne.
    pause
    exit /b
)

echo.
echo Lancement de l'interface de revision...
echo.

py -3.12 review_gui.py "%file_path%"

echo.
echo ==========================================
echo             REVISION TERMINEE
echo ==========================================
pause
