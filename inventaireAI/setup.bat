@echo off
echo ==========================================
echo      INSTALLATION DES DEPENDANCES
echo ==========================================
echo.

py -3.12 --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERREUR] Python 3.12 n'est pas detecte !
    echo Veuillez installer Python 3.12.
    echo.
    pause
    exit /b
)

echo Mise a jour de pip...
py -3.12 -m pip install --upgrade pip

echo.
echo Installation des bibliotheques requises...
py -3.12 -m pip install -r requirements.txt

if %errorlevel% neq 0 (
    echo.
    echo [ERREUR] Une erreur est survenue lors de l'installation.
    pause
    exit /b
)

echo.
echo ==========================================
echo      INSTALLATION REUSSIE !
echo ==========================================
echo Vous pouvez maintenant utiliser start.bat
echo.
pause
