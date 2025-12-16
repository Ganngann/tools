@echo off
echo ===================================
echo   Construction de Inventaire AI
echo ===================================
echo.

:: 1. Verifier PyInstaller
pip show pyinstaller >nul 2>&1
if %errorlevel% neq 0 (
    echo [INFO] PyInstaller non trouve. Installation...
    pip install pyinstaller
) else (
    echo [INFO] PyInstaller est deja installe.
)

:: 2. Nettoyer les anciens builds
echo [INFO] Nettoyage...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist *.spec del *.spec

:: 3. Lancer la construction
echo [INFO] Generation de l'executable...
:: --onefile : Un seul fichier .exe
:: --windowed : Pas de fenetre noire de console
:: --name : Nom de l'exe
:: --hidden-import : Force l'inclusion de depedances cachees
echo.
pyinstaller --noconfirm --onefile --windowed --name "InventaireAI" ^
    --hidden-import=pandas ^
    --hidden-import=PIL ^
    --hidden-import=tkinter ^
    --collect-all=tcl ^
    --collect-all=tk ^
    app.py

if %errorlevel% neq 0 (
    echo [ERREUR] La construction a echoue.
    pause
    exit /b %errorlevel%
)

echo.

echo [INFO] Copie des fichiers de configuration...
copy ".env" "dist\.env"
copy "categories.csv" "dist\categories.csv"

echo.
echo ===================================
echo   CONSTRUCTION REUSSIE !
echo ===================================
echo L'application se trouve dans le dossier 'dist'.
echo.
echo L'executable et les fichiers de configuration sont prets.
echo.
pause
