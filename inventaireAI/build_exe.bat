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

:: 3. Mettre a jour la date de build
echo [INFO] Mise a jour de la date dans version_info.py...
python -c "import datetime; d = datetime.datetime.now().strftime('%%Y-%%m-%%d'); lines = open('version_info.py').readlines(); open('version_info.py', 'w').writelines([l if not l.startswith('BUILD_DATE') else f'BUILD_DATE = \"{d}\"\n' for l in lines]); print(f'Build date updated to {d}')"

:: 3a. Mettre a jour la version dans le code
python -c "import json; v = json.load(open('version_info.json'))['version']; lines = open('version_info.py').readlines(); open('version_info.py', 'w').writelines([l if not l.startswith('VERSION') else f'VERSION = \"{v}\"\n' for l in lines]); print(f'Version updated to {v}')"

:: 3b. Recuperer la version
for /f "delims=" %%i in ('python -c "import json; print(json.load(open('version_info.json'))['version'])"') do set APP_VERSION=%%i
echo [INFO] Version detectee : %APP_VERSION%

:: 4. Lancer la construction
echo [INFO] Generation de l'executable...
:: --onefile : Un seul fichier .exe
:: --windowed : Pas de fenetre noire de console
:: --name : Nom de l'exe
:: --hidden-import : Force l'inclusion de depedances cachees
echo.
pyinstaller --noconfirm --onefile --windowed --name "InventaireAI_v%APP_VERSION%" ^
    --hidden-import=pandas ^
    --hidden-import=PIL ^
    --hidden-import=tkinter ^
    --hidden-import=counter ^
    --hidden-import=review_gui ^
    --hidden-import=inventory_ai ^
    --hidden-import=ui_utils ^
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
