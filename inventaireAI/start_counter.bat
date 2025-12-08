@echo off
echo ==========================================
echo      LANCEMENT DU COMPTEUR D'INVENTAIRE
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

:: Remove quotes if present
set folder_path=%folder_path:"=%

if "%folder_path%"=="" (
    echo.
    echo [ERREUR] Aucun dossier selectionne.
    pause
    exit /b
)

echo.
echo Voulez-vous compter un type d'objet specifique ? (Laissez vide pour tout compter)
set /p target_element="Objet a cibler (ex: 'vis', 'voiture') > "

echo.
echo Traitement du dossier : "%folder_path%"
if not "%target_element%"=="" echo Cible : "%target_element%"
echo.

if "%target_element%"=="" (
    py -3.12 counter.py "%folder_path%"
) else (
    py -3.12 counter.py "%folder_path%" --target "%target_element%"
)

echo.
echo ==========================================
echo             TRAITEMENT TERMINE
echo ==========================================
pause
