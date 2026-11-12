; Copia la app (dist\GestionDeCarnicerias) y los binarios de PostgreSQL (vendor\pgsql).
; Los datos viven aparte, en C:\GestionDeCarnicerias: la base (pgdata), la configuracion
; de la PC (config.env), fotos y logs. Actualizar nunca los borra; solo migra.
; build_release.bat pasa la version con /DAPP_VERSION=X.Y.Z /DAPP_BUILD=X.Y.Z.0

!include "MUI2.nsh"
!include "LogicLib.nsh"

!define APP_NAME "GestionDeCarnicerias"
!define APP_EXE "GestionDeCarnicerias.exe"
!ifndef APP_VERSION
    !define APP_VERSION "0.1.2"
!endif
!ifndef APP_BUILD
    !define APP_BUILD "0.1.2.0"
!endif
!define COMPANY_NAME "Adema Sistemas"
!define APP_PORT "8250"
!define FIREWALL_RULE "GestionDeCarnicerias - tablets del mostrador"
!define DATA_ROOT "C:\GestionDeCarnicerias"
!define DB_DIR "C:\GestionDeCarnicerias\db"
!define LOG_DIR "C:\GestionDeCarnicerias\logs"
!define MEDIA_DIR "C:\GestionDeCarnicerias\media"
!define ICON_FILE "static\img\ico.ico"

Name "${APP_NAME}"
OutFile "${APP_NAME}_Installer_v${APP_VERSION}.exe"
InstallDir "$PROGRAMFILES64\${APP_NAME}"
InstallDirRegKey HKLM "Software\${COMPANY_NAME}\${APP_NAME}" "Install_Dir"
RequestExecutionLevel admin

VIProductVersion "${APP_BUILD}"
VIAddVersionKey "ProductName" "${APP_NAME}"
VIAddVersionKey "CompanyName" "${COMPANY_NAME}"
VIAddVersionKey "FileDescription" "${APP_NAME} Installer"
VIAddVersionKey "FileVersion" "${APP_VERSION}"
VIAddVersionKey "ProductVersion" "${APP_VERSION}"
VIAddVersionKey "LegalCopyright" "${COMPANY_NAME}"
Icon "${ICON_FILE}"
UninstallIcon "${ICON_FILE}"

!define MUI_ABORTWARNING
!define MUI_ICON "${ICON_FILE}"
!define MUI_UNICON "${ICON_FILE}"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "Spanish"

; Cierra la app y apaga su PostgreSQL antes de tocar archivos.
!macro DetenerApp
    nsExec::ExecToLog 'taskkill /F /T /IM ${APP_EXE}'
    ${If} ${FileExists} "$INSTDIR\pgsql\bin\pg_ctl.exe"
    ${AndIf} ${FileExists} "${DATA_ROOT}\pgdata\PG_VERSION"
        nsExec::ExecToLog '"$INSTDIR\pgsql\bin\pg_ctl.exe" stop -D "${DATA_ROOT}\pgdata" -m fast -w'
    ${EndIf}
!macroend

Section "Instalar ${APP_NAME}" SEC_INSTALL
    !insertmacro DetenerApp

    SetOutPath "$INSTDIR"
    File /r "dist\${APP_NAME}\*.*"
    SetOutPath "$INSTDIR\pgsql"
    File /r "vendor\pgsql\*.*"
    SetOutPath "$INSTDIR"

    CreateDirectory "${DATA_ROOT}"
    CreateDirectory "${DB_DIR}"
    CreateDirectory "${LOG_DIR}"
    CreateDirectory "${MEDIA_DIR}"
    nsExec::ExecToLog 'icacls "${DATA_ROOT}" /grant *S-1-1-0:(OI)(CI)F /T /C'

    ; Las tablets y celulares del mostrador entran por wifi al puerto de la app.
    nsExec::ExecToLog 'netsh advfirewall firewall delete rule name="${FIREWALL_RULE}"'
    nsExec::ExecToLog 'netsh advfirewall firewall add rule name="${FIREWALL_RULE}" dir=in action=allow protocol=TCP localport=${APP_PORT} profile=private,domain'

    ; Primera vez: crea el PostgreSQL local y la base. Actualizacion: solo migraciones.
    DetailPrint "Preparando la base de datos (la primera vez tarda un minuto)..."
    ${If} ${FileExists} "$INSTDIR\${APP_EXE}"
        nsExec::ExecToLog '"$INSTDIR\${APP_EXE}" --migrate-only'
        Pop $0
        ${If} $0 != 0
            MessageBox MB_ICONSTOP|MB_OK "No se pudieron aplicar las migraciones (codigo $0). Cierre Gestion de Carnicerias si esta abierto y vuelva a ejecutar el instalador."
            Abort
        ${EndIf}
    ${EndIf}

    CreateDirectory "$SMPROGRAMS\${APP_NAME}"
    CreateShortCut "$DESKTOP\${APP_NAME}.lnk" "$INSTDIR\${APP_EXE}" "" "$INSTDIR\${APP_EXE}" 0
    CreateShortCut "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk" "$INSTDIR\${APP_EXE}" "" "$INSTDIR\${APP_EXE}" 0
    CreateShortCut "$SMPROGRAMS\${APP_NAME}\Desinstalar ${APP_NAME}.lnk" "$INSTDIR\Uninstall.exe"
    ; Arranca sola al iniciar sesion: la sucursal no depende de que alguien abra la app.
    CreateShortCut "$SMSTARTUP\${APP_NAME}.lnk" "$INSTDIR\${APP_EXE}" "" "$INSTDIR\${APP_EXE}" 0

    WriteRegStr HKLM "Software\${COMPANY_NAME}\${APP_NAME}" "Install_Dir" "$INSTDIR"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" "DisplayName" "${APP_NAME}"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" "DisplayVersion" "${APP_VERSION}"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" "Publisher" "${COMPANY_NAME}"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" "InstallLocation" "$INSTDIR"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" "DisplayIcon" "$INSTDIR\${APP_EXE}"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" "UninstallString" '"$INSTDIR\Uninstall.exe"'
    WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" "NoModify" 1
    WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" "NoRepair" 1

    WriteUninstaller "$INSTDIR\Uninstall.exe"
SectionEnd

Section "Uninstall"
    !insertmacro DetenerApp
    nsExec::ExecToLog 'netsh advfirewall firewall delete rule name="${FIREWALL_RULE}"'

    Delete "$SMSTARTUP\${APP_NAME}.lnk"
    Delete "$DESKTOP\${APP_NAME}.lnk"
    Delete "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk"
    Delete "$SMPROGRAMS\${APP_NAME}\Desinstalar ${APP_NAME}.lnk"
    RMDir "$SMPROGRAMS\${APP_NAME}"

    DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}"
    DeleteRegKey HKLM "Software\${COMPANY_NAME}\${APP_NAME}"

    MessageBox MB_YESNO|MB_ICONQUESTION|MB_DEFBUTTON2 "Desea borrar la base de datos, media y logs de ${DATA_ROOT}? Se pierde lo que no se haya sincronizado con la central." IDYES delete_data IDNO keep_data
    delete_data:
        RMDir /r "${DATA_ROOT}"
    keep_data:

    Delete "$INSTDIR\Uninstall.exe"
    RMDir /r "$INSTDIR"
SectionEnd