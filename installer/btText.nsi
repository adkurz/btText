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
!define INSTALL_MARKER "bttext-install-mode.json"
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
!include "nsDialogs.nsh"

!define MUI_ABORTWARNING
!define MUI_FINISHPAGE_RUN "$INSTDIR\${APP_EXE}"
!define MUI_FINISHPAGE_RUN_FUNCTION LaunchApplication

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "..\LICENSE"
Page custom ShowDirectoryPage LeaveDirectoryPage
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
LangString DirectoryPageTitle ${LANG_ENGLISH} "Choose Install Location"
LangString DirectoryPageTitle ${LANG_GERMAN} "Installationsort auswählen"
LangString DirectoryPageSubtitle ${LANG_ENGLISH} "Choose the folder in which to install btText."
LangString DirectoryPageSubtitle ${LANG_GERMAN} "Wählen Sie den Ordner aus, in dem btText installiert werden soll."
LangString DirectoryPageText ${LANG_ENGLISH} "Setup will install btText in the following folder. To choose a different folder, click Browse."
LangString DirectoryPageText ${LANG_GERMAN} "Setup installiert btText in den folgenden Ordner. Klicken Sie auf Durchsuchen, um einen anderen Ordner auszuwählen."
LangString InstallLocationLabel ${LANG_ENGLISH} "&Install location:"
LangString InstallLocationLabel ${LANG_GERMAN} "&Installationsordner:"
LangString BrowseButton ${LANG_ENGLISH} "&Browse..."
LangString BrowseButton ${LANG_GERMAN} "&Durchsuchen..."
LangString BrowseDialogTitle ${LANG_ENGLISH} "Select the btText install location"
LangString BrowseDialogTitle ${LANG_GERMAN} "Installationsordner für btText auswählen"
LangString InstallLocationRequired ${LANG_ENGLISH} "Enter an install location."
LangString InstallLocationRequired ${LANG_GERMAN} "Geben Sie einen Installationsordner ein."
LangString InstallLocationNotOwned ${LANG_ENGLISH} "The selected folder is not empty and does not contain btText.exe. Choose an empty folder or the folder of an existing btText installation. Existing files will not be overwritten."
LangString InstallLocationNotOwned ${LANG_GERMAN} "Der ausgewählte Ordner ist nicht leer und enthält keine btText.exe. Wählen Sie einen leeren Ordner oder den Ordner einer bestehenden btText-Installation. Vorhandene Dateien werden nicht überschrieben."

Var PreviousUninstaller
Var PreviousInstallDir
Var DirectoryDialog
Var DirectoryInput

Function ShowDirectoryPage
  !insertmacro MUI_HEADER_TEXT "$(DirectoryPageTitle)" "$(DirectoryPageSubtitle)"

  nsDialogs::Create 1018
  Pop $DirectoryDialog
  ${If} $DirectoryDialog == error
    Abort
  ${EndIf}

  ${NSD_CreateLabel} 0 0 100% 24u "$(DirectoryPageText)"
  Pop $0

  ; Keep this label immediately before the edit control so screen readers can
  ; expose it as the edit control's accessible name.
  ${NSD_CreateLabel} 0 30u 100% 12u "$(InstallLocationLabel)"
  Pop $0

  ${NSD_CreateDirRequest} 0 44u 78% 13u "$INSTDIR"
  Pop $DirectoryInput

  ${NSD_CreateBrowseButton} 80% 43u 20% 15u "$(BrowseButton)"
  Pop $0
  ${NSD_OnClick} $0 BrowseForInstallLocation

  ${NSD_SetFocus} $DirectoryInput
  nsDialogs::Show
FunctionEnd

Function BrowseForInstallLocation
  ${NSD_GetText} $DirectoryInput $0
  nsDialogs::SelectFolderDialog "$(BrowseDialogTitle)" "$0"
  Pop $0
  ${If} $0 != error
    ${NSD_SetText} $DirectoryInput "$0"
    ${NSD_SetFocus} $DirectoryInput
  ${EndIf}
FunctionEnd

Function LeaveDirectoryPage
  ${NSD_GetText} $DirectoryInput $0
  ${If} $0 == ""
    MessageBox MB_OK|MB_ICONEXCLAMATION "$(InstallLocationRequired)"
    Abort
  ${EndIf}
  Call NormalizeInstallDirectory
  ${If} $0 == ""
    MessageBox MB_OK|MB_ICONEXCLAMATION "$(InstallLocationRequired)"
    Abort
  ${EndIf}
  StrCpy $INSTDIR $0
  Call ValidateInstallDirectory
  Pop $0
  ${If} $0 = 0
    MessageBox MB_OK|MB_ICONEXCLAMATION "$(InstallLocationNotOwned)"
    Abort
  ${EndIf}
FunctionEnd

Function NormalizeInstallDirectory
  ; The NSIS GetFullPathName instruction clears its result when the target
  ; directory does not exist. The Windows API canonicalizes the same path
  ; without requiring any part of the new install directory to exist.
  System::Call 'kernel32::GetFullPathNameW(w r0, i ${NSIS_MAX_STRLEN}, w .r1, p 0) i.r2'
  ${If} $2 = 0
  ${OrIf} $2 >= ${NSIS_MAX_STRLEN}
    StrCpy $0 ""
  ${Else}
    StrCpy $0 $1
  ${EndIf}
FunctionEnd

Function ValidateInstallDirectory
  StrCpy $0 1
  ClearErrors
  FindFirst $1 $2 "$INSTDIR\*"
  IfErrors directory_validation_done
  directory_check_next_entry:
  StrCmp $2 "." directory_find_next
  StrCmp $2 ".." directory_find_next
  FindClose $1
  Goto directory_has_contents
  directory_find_next:
  ClearErrors
  FindNext $1 $2
  IfErrors directory_no_more_entries
  Goto directory_check_next_entry
  directory_no_more_entries:
  FindClose $1
  Goto directory_validation_done
  directory_has_contents:
  IfFileExists "$INSTDIR\${APP_EXE}" directory_validation_done directory_not_owned
  directory_not_owned:
  StrCpy $0 0
  directory_validation_done:
  Push $0
FunctionEnd

Function RequireSafeInstallDirectory
  StrCpy $0 $INSTDIR
  Call NormalizeInstallDirectory
  ${If} $0 == ""
    MessageBox MB_OK|MB_ICONEXCLAMATION "$(InstallLocationRequired)" /SD IDOK
    SetErrorLevel 2
    Abort
  ${EndIf}
  StrCpy $INSTDIR $0
  Call ValidateInstallDirectory
  Pop $0
  ${If} $0 = 0
    MessageBox MB_OK|MB_ICONEXCLAMATION "$(InstallLocationNotOwned)" /SD IDOK
    SetErrorLevel 2
    Abort
  ${EndIf}
FunctionEnd

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
  ; Custom page callbacks are skipped in silent mode, so enforce the same
  ; ownership check again before an upgrade or any payload write.
  Call RequireSafeInstallDirectory
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
  RMDir /r "$INSTDIR"

  IfSilent keep_user_data
  MessageBox MB_YESNO|MB_DEFBUTTON2|MB_ICONQUESTION "$(RemoveUserDataPrompt)" IDNO keep_user_data
  ClearErrors
  RMDir /r "$APPDATA\btText"
  IfErrors 0 keep_user_data
  MessageBox MB_OK|MB_ICONSTOP "$(RemoveUserDataFailed)" /SD IDOK
  SetErrorLevel 3
  keep_user_data:
SectionEnd
