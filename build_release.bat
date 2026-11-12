@echo off
setlocal enabledelayedexpansion

cd /d "%~dp0"

for /f "tokens=2 delims==" %%A in ('findstr /R "^__version__" version.py') do set VERSION_RAW=%%A
set VERSION=%VERSION_RAW:"=%
set VERSION=%VERSION: =%

echo Building Gestion de Carnicerias v%VERSION%

python -m pip install -r requirements_win.txt
if errorlevel 1 exit /b 1

python manage.py collectstatic --noinput --clear
if errorlevel 1 exit /b 1

rem Traducciones (espanol / chino): compila los .po a .mo. Requiere GNU gettext en el PATH.
python manage.py compilemessages -l es -l zh_Hans --ignore=venv
if errorlevel 1 exit /b 1

python -m PyInstaller gestion_de_carnicerias.spec --clean --noconfirm
if errorlevel 1 exit /b 1

rem Verificacion: toda carpeta <app>\templates del proyecto tiene que estar en el paquete.
python verificar_build.py
if errorlevel 1 exit /b 1

rem Binarios de PostgreSQL que viajan en el instalador (vendor\pgsql: bin, lib, share).
rem Se copian de PGSQL_HOME o, si no esta definida, de un PostgreSQL 18 instalado en esta PC.
if exist "vendor\pgsql\bin\pg_ctl.exe" goto pgsql_listo
set "PGSQL_ORIGEN=%PGSQL_HOME%"
if not defined PGSQL_ORIGEN if exist "C:\Program Files\PostgreSQL\18\bin\pg_ctl.exe" set "PGSQL_ORIGEN=C:\Program Files\PostgreSQL\18"
if not defined PGSQL_ORIGEN goto pgsql_falta
echo Copiando PostgreSQL desde %PGSQL_ORIGEN%
for %%D in (bin lib share) do (
    robocopy "%PGSQL_ORIGEN%\%%D" "vendor\pgsql\%%D" /E /NFL /NDL /NJH /NJS /NP >nul
    if errorlevel 8 exit /b 1
)
goto pgsql_listo

:pgsql_falta
echo Faltan los binarios de PostgreSQL en vendor\pgsql.
echo Defini PGSQL_HOME con la carpeta de un PostgreSQL 18 para Windows x64 que tenga bin, lib y share.
exit /b 1

:pgsql_listo

set "MAKENSIS=makensis"
where makensis >nul 2>nul
if errorlevel 1 goto find_nsis
goto run_nsis

:find_nsis
if exist "C:\Program Files (x86)\NSIS\makensis.exe" set "MAKENSIS=C:\Program Files (x86)\NSIS\makensis.exe"
if exist "C:\Program Files\NSIS\makensis.exe" set "MAKENSIS=C:\Program Files\NSIS\makensis.exe"
if not exist "%MAKENSIS%" (
    echo No se encontro makensis.exe. Instala NSIS o agregalo al PATH.
    exit /b 1
)

:run_nsis

"%MAKENSIS%" /DAPP_VERSION=%VERSION% /DAPP_BUILD=%VERSION%.0 installer.nsi
if errorlevel 1 exit /b 1

set "INSTALLER=GestionDeCarnicerias_Installer_v%VERSION%.exe"
set "HASH_FILE=%INSTALLER%.sha256"
set "OUT_DIR=exe\%VERSION%"

if not exist "%INSTALLER%" (
    echo No se encontro %INSTALLER% despues de compilar NSIS.
    exit /b 1
)

if not exist "exe" mkdir "exe"
if not exist "%OUT_DIR%" mkdir "%OUT_DIR%"

powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-FileHash '%INSTALLER%' -Algorithm SHA256 | ForEach-Object { $_.Hash } | Set-Content '%HASH_FILE%'"
if errorlevel 1 exit /b 1

copy /Y "%INSTALLER%" "%OUT_DIR%\%INSTALLER%"
if errorlevel 1 exit /b 1

copy /Y "%HASH_FILE%" "%OUT_DIR%\%HASH_FILE%"
if errorlevel 1 exit /b 1

echo Release listo en %OUT_DIR%
endlocal