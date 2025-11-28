@echo off
echo ==========================================
echo      LANCEMENT DE L'INVENTAIRE
echo ==========================================
echo.

:: Check if a folder was dragged onto the script
if "%~1"=="" (
    echo Veuillez glisser-deposer le dossier contenant les photos ci-dessous
    echo et appuyez sur ENTREE.
    echo.
    set /p folder_path="Dossier > "
) else (
    set folder_path=%~1
)

:: Remove quotes if present (to avoid double quotes)
set folder_path=%folder_path:"=%

if "%folder_path%"=="" (
    echo.
    echo [ERREUR] Aucun dossier selectionne.
    pause
    exit /b
)

echo.
echo Traitement du dossier : "%folder_path%"
echo.

py -3.12 main.py "%folder_path%"

echo.
echo ==========================================
echo             TRAITEMENT TERMINE
echo ==========================================
pause
