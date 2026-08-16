; Per-user NSIS installer for the PyInstaller onedir build.
; build.ps1 supplies VERSION, SOURCE_DIR, OUTPUT_DIR, and MARKER_FILE.

Unicode true
RequestExecutionLevel user
ManifestSupportedOS Win10
CRCCheck on
SetCompressor /SOLID lzma

!ifndef VERSION
  !error "VERSION must be supplied by build.ps1"
!endif
!ifndef SOURCE_DIR
  !error "SOURCE_DIR must be supplied by build.ps1"
!endif
!ifndef OUTPUT_DIR
  !error "OUTPUT_DIR must be supplied by build.ps1"
!endif
!ifndef MARKER_FILE
  !error "MARKER_FILE must be supplied by build.ps1"
!endif
!ifndef FILE_VERSION
  !error "FILE_VERSION must be supplied by build.ps1"
!endif

!define APP_NAME "btText"
!define APP_PUBLISHER "Adrian Kurz"
!define APP_EXE "btText.exe"
!define APP_ID "btText.AdrianKurz"
!define INNO_UNINSTALL_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_ID}_is1"
!define NSIS_UNINSTALL_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_ID}"

Name "${APP_NAME} ${VERSION}"
OutFile "${OUTPUT_DIR}\btText-${VERSION}-setup-windows.exe"
InstallDir "$LOCALAPPDATA\Programs\${APP_NAME}"
InstallDirRegKey HKCU "${NSIS_UNINSTALL_KEY}" "InstallLocation"
BrandingText "${APP_NAME}"
Icon "..\assets\icon.ico"
UninstallIcon "..\assets\icon.ico"
VIProductVersion "${FILE_VERSION}"
VIAddVersionKey /LANG=1033 "ProductName" "${APP_NAME}"
VIAddVersionKey /LANG=1033 "CompanyName" "${APP_PUBLISHER}"
VIAddVersionKey /LANG=1033 "LegalCopyright" "Copyright ${APP_PUBLISHER}"
VIAddVersionKey /LANG=1033 "FileDescription" "${APP_NAME} Setup"
VIAddVersionKey /LANG=1033 "FileVersion" "${VERSION}"
VIAddVersionKey /LANG=1033 "ProductVersion" "${VERSION}"

!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "WinVer.nsh"
!include "x64.nsh"
!include "Sections.nsh"

!define MUI_ABORTWARNING
!define MUI_FINISHPAGE_RUN "$INSTDIR\${APP_EXE}"
!define MUI_FINISHPAGE_RUN_FUNCTION LaunchApplication

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "..\LICENSE"
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "English"
!insertmacro MUI_LANGUAGE "German"

LangString MainSection ${LANG_ENGLISH} "btText (required)"
LangString MainSection ${LANG_GERMAN} "btText (erforderlich)"
LangString DesktopShortcut ${LANG_ENGLISH} "Create a desktop shortcut"
LangString DesktopShortcut ${LANG_GERMAN} "Desktop-Symbol erstellen"
LangString StartupShortcut ${LANG_ENGLISH} "Start btText automatically when I sign in"
LangString StartupShortcut ${LANG_GERMAN} "btText bei der Anmeldung automatisch starten"
LangString InnoUpgradeFailed ${LANG_ENGLISH} "The existing Inno Setup installation could not be removed (exit code $0). Setup cannot continue. Your user data was not removed."
LangString InnoUpgradeFailed ${LANG_GERMAN} "Die bestehende Inno-Setup-Installation konnte nicht entfernt werden (Exitcode $0). Das Setup kann nicht fortgesetzt werden. Ihre Nutzerdaten wurden nicht entfernt."
LangString OldUpgradeFailed ${LANG_ENGLISH} "The existing btText installation could not be removed (exit code $0). Setup cannot continue. Your user data was not removed."
LangString OldUpgradeFailed ${LANG_GERMAN} "Die bestehende btText-Installation konnte nicht entfernt werden (Exitcode $0). Das Setup kann nicht fortgesetzt werden. Ihre Nutzerdaten wurden nicht entfernt."
LangString ApplicationStillRunning ${LANG_ENGLISH} "btText is still running. Close btText, then click Retry."
LangString ApplicationStillRunning ${LANG_GERMAN} "btText wird noch ausgeführt. Schließen Sie btText und klicken Sie anschließend auf Wiederholen."
LangString RemoveUserDataPrompt ${LANG_ENGLISH} "Do you also want to permanently delete all btText settings and databases stored in $APPDATA\btText? External databases will not be deleted. This cannot be undone."
LangString RemoveUserDataPrompt ${LANG_GERMAN} "Möchten Sie zusätzlich alle btText-Einstellungen und Datenbanken unter $APPDATA\btText dauerhaft löschen? Externe Datenbanken werden nicht gelöscht. Dies kann nicht rückgängig gemacht werden."
LangString RemoveUserDataFailed ${LANG_ENGLISH} "Not all btText user data could be removed. Please delete $APPDATA\btText manually."
LangString RemoveUserDataFailed ${LANG_GERMAN} "Nicht alle btText-Nutzerdaten konnten entfernt werden. Bitte löschen Sie $APPDATA\btText manuell."
LangString UnsupportedWindows ${LANG_ENGLISH} "Windows 10 or newer is required."
LangString UnsupportedWindows ${LANG_GERMAN} "Windows 10 oder neuer ist erforderlich."
LangString UnsupportedArchitecture ${LANG_ENGLISH} "64-bit Windows is required."
LangString UnsupportedArchitecture ${LANG_GERMAN} "64-Bit-Windows ist erforderlich."

Var PreviousUninstaller
Var PreviousInstallDir

Function SignalRunningApplicationToExit
  System::Call 'kernel32::OpenEventW(i 0x0002, i 0, w "Local\btText.UpdateShutdown") p.r0'
  ${If} $0 P<> 0
    System::Call 'kernel32::SetEvent(p r0)'
    System::Call 'kernel32::CloseHandle(p r0)'
  ${EndIf}
FunctionEnd

Function IsApplicationRunning
  StrCpy $2 ""
  System::Call 'advapi32::GetUserName(t .r2, *i ${NSIS_MAX_STRLEN} r3) i.r4'
  ${If} $4 = 0
    ReadEnvStr $2 "USERNAME"
  ${EndIf}
  System::Call 'kernel32::OpenMutexW(i 0x00100000, i 0, w "btText-$2") p.r0'
  ${If} $0 P<> 0
    System::Call 'kernel32::CloseHandle(p r0)'
    Push 1
  ${Else}
    Push 0
  ${EndIf}
FunctionEnd

Function WaitForApplication
  retry_running:
  Call SignalRunningApplicationToExit
  StrCpy $1 50
  wait_running:
    Call IsApplicationRunning
    Pop $0
    ${If} $0 = 0
      Return
    ${EndIf}
    Sleep 100
    IntOp $1 $1 - 1
    ${If} $1 > 0
      Goto wait_running
    ${EndIf}
  IfSilent abort_running
  MessageBox MB_RETRYCANCEL|MB_ICONEXCLAMATION "$(ApplicationStillRunning)" IDRETRY retry_running
  abort_running:
  SetErrorLevel 2
  Abort
FunctionEnd

Function ReadInnoUninstaller
  StrCpy $PreviousUninstaller ""
  SetRegView 32
  ReadRegStr $PreviousUninstaller HKCU "${INNO_UNINSTALL_KEY}" "UninstallString"
  ${If} $PreviousUninstaller == ""
    SetRegView 64
    ReadRegStr $PreviousUninstaller HKCU "${INNO_UNINSTALL_KEY}" "UninstallString"
  ${EndIf}
  SetRegView 32
FunctionEnd

Function RemovePreviousInstallations
  Call ReadInnoUninstaller
  ${If} $PreviousUninstaller != ""
    ExecWait '$PreviousUninstaller /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /SP-' $0
    ${If} $0 != 0
      MessageBox MB_OK|MB_ICONSTOP "$(InnoUpgradeFailed)" /SD IDOK
      SetErrorLevel 2
      Abort
    ${EndIf}
  ${EndIf}

  ReadRegStr $PreviousUninstaller HKCU "${NSIS_UNINSTALL_KEY}" "UninstallString"
  ReadRegStr $PreviousInstallDir HKCU "${NSIS_UNINSTALL_KEY}" "InstallLocation"
  ${If} $PreviousUninstaller != ""
    ExecWait '$PreviousUninstaller /S _?=$PreviousInstallDir' $0
    ${If} $0 != 0
      MessageBox MB_OK|MB_ICONSTOP "$(OldUpgradeFailed)" /SD IDOK
      SetErrorLevel 2
      Abort
    ${EndIf}
  ${EndIf}
FunctionEnd

Function LaunchApplication
  Exec '"$INSTDIR\${APP_EXE}"'
FunctionEnd

Section "$(MainSection)" MainSection
  SectionIn RO
  Call WaitForApplication
  Call RemovePreviousInstallations
  SetOutPath "$INSTDIR"
  File /r "${SOURCE_DIR}\*"
  SetOutPath "$INSTDIR\_internal"
  File "${MARKER_FILE}"

  CreateDirectory "$SMPROGRAMS\${APP_NAME}"
  CreateShortcut "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk" "$INSTDIR\${APP_EXE}"
  WriteUninstaller "$INSTDIR\uninstall.exe"

  WriteRegStr HKCU "${NSIS_UNINSTALL_KEY}" "DisplayName" "${APP_NAME}"
  WriteRegStr HKCU "${NSIS_UNINSTALL_KEY}" "DisplayVersion" "${VERSION}"
  WriteRegStr HKCU "${NSIS_UNINSTALL_KEY}" "Publisher" "${APP_PUBLISHER}"
  WriteRegStr HKCU "${NSIS_UNINSTALL_KEY}" "DisplayIcon" "$INSTDIR\${APP_EXE}"
  WriteRegStr HKCU "${NSIS_UNINSTALL_KEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "${NSIS_UNINSTALL_KEY}" "UninstallString" '"$INSTDIR\uninstall.exe"'
  WriteRegStr HKCU "${NSIS_UNINSTALL_KEY}" "QuietUninstallString" '"$INSTDIR\uninstall.exe" /S'
  WriteRegDWORD HKCU "${NSIS_UNINSTALL_KEY}" "NoModify" 1
  WriteRegDWORD HKCU "${NSIS_UNINSTALL_KEY}" "NoRepair" 1
  SectionGetSize ${MainSection} $0
  WriteRegDWORD HKCU "${NSIS_UNINSTALL_KEY}" "EstimatedSize" $0
SectionEnd

Section /o "$(DesktopShortcut)" DesktopSection
  CreateShortcut "$DESKTOP\${APP_NAME}.lnk" "$INSTDIR\${APP_EXE}"
SectionEnd

Section /o "$(StartupShortcut)" StartupSection
  CreateShortcut "$SMSTARTUP\${APP_NAME}.lnk" "$INSTDIR\${APP_EXE}"
SectionEnd

Function .onInit
  SetShellVarContext current
  ${IfNot} ${AtLeastWin10}
    MessageBox MB_OK|MB_ICONSTOP "$(UnsupportedWindows)" /SD IDOK
    SetErrorLevel 2
    Abort
  ${EndIf}
  ${IfNot} ${RunningX64}
    MessageBox MB_OK|MB_ICONSTOP "$(UnsupportedArchitecture)" /SD IDOK
    SetErrorLevel 2
    Abort
  ${EndIf}
  !insertmacro UnselectSection ${DesktopSection}
  !insertmacro UnselectSection ${StartupSection}
  IfFileExists "$DESKTOP\${APP_NAME}.lnk" desktop_shortcut_exists desktop_shortcut_done
  desktop_shortcut_exists:
  !insertmacro SelectSection ${DesktopSection}
  desktop_shortcut_done:
  IfFileExists "$SMSTARTUP\${APP_NAME}.lnk" startup_shortcut_exists startup_shortcut_done
  startup_shortcut_exists:
  !insertmacro SelectSection ${StartupSection}
  startup_shortcut_done:
FunctionEnd

Function un.onInit
  SetShellVarContext current
  Call un.WaitForApplication
FunctionEnd

Function un.SignalRunningApplicationToExit
  System::Call 'kernel32::OpenEventW(i 0x0002, i 0, w "Local\btText.UpdateShutdown") p.r0'
  ${If} $0 P<> 0
    System::Call 'kernel32::SetEvent(p r0)'
    System::Call 'kernel32::CloseHandle(p r0)'
  ${EndIf}
FunctionEnd

Function un.IsApplicationRunning
  StrCpy $2 ""
  System::Call 'advapi32::GetUserName(t .r2, *i ${NSIS_MAX_STRLEN} r3) i.r4'
  ${If} $4 = 0
    ReadEnvStr $2 "USERNAME"
  ${EndIf}
  System::Call 'kernel32::OpenMutexW(i 0x00100000, i 0, w "btText-$2") p.r0'
  ${If} $0 P<> 0
    System::Call 'kernel32::CloseHandle(p r0)'
    Push 1
  ${Else}
    Push 0
  ${EndIf}
FunctionEnd

Function un.WaitForApplication
  retry_uninstall_running:
  Call un.SignalRunningApplicationToExit
  StrCpy $1 50
  wait_uninstall_running:
    Call un.IsApplicationRunning
    Pop $0
    ${If} $0 = 0
      Return
    ${EndIf}
    Sleep 100
    IntOp $1 $1 - 1
    ${If} $1 > 0
      Goto wait_uninstall_running
    ${EndIf}
  IfSilent abort_uninstall_running
  MessageBox MB_RETRYCANCEL|MB_ICONEXCLAMATION "$(ApplicationStillRunning)" IDRETRY retry_uninstall_running
  abort_uninstall_running:
  SetErrorLevel 2
  Abort
FunctionEnd

Section "Uninstall"
  Delete "$DESKTOP\${APP_NAME}.lnk"
  Delete "$SMSTARTUP\${APP_NAME}.lnk"
  Delete "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk"
  RMDir "$SMPROGRAMS\${APP_NAME}"
  DeleteRegKey HKCU "${NSIS_UNINSTALL_KEY}"
  SetOutPath "$TEMP"
  Delete "$INSTDIR\${APP_EXE}"
  RMDir /r "$INSTDIR\_internal"
  Delete "$INSTDIR\uninstall.exe"
  RMDir "$INSTDIR"

  IfSilent keep_user_data
  MessageBox MB_YESNO|MB_DEFBUTTON2|MB_ICONQUESTION "$(RemoveUserDataPrompt)" IDNO keep_user_data
  ClearErrors
  RMDir /r "$APPDATA\btText"
  IfErrors 0 keep_user_data
  MessageBox MB_OK|MB_ICONSTOP "$(RemoveUserDataFailed)" /SD IDOK
  SetErrorLevel 3
  keep_user_data:
SectionEnd
