; Per-user installer for the PyInstaller onedir build.
; The build supplies the version, source, and output directory with ISCC /D switches.

#ifndef MyAppVersion
  #error MyAppVersion must be supplied by build.ps1
#endif
#ifndef MySourceDir
  #define MySourceDir "..\build\installer-payload\btText"
#endif
#ifndef MyOutputDir
  #define MyOutputDir "..\build"
#endif
#ifndef MyOutputBaseFilename
  #define MyOutputBaseFilename "btText-" + MyAppVersion + "-setup-windows"
#endif

#define MyAppName "btText"
#define MyAppPublisher "Adrian Kurz"
#define MyAppExeName "btText.exe"

[Setup]
AppId=btText.AdrianKurz
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
DirExistsWarning=no
PrivilegesRequired=lowest
SetupArchitecture=x64
OutputDir={#MyOutputDir}
OutputBaseFilename={#MyOutputBaseFilename}
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=force
RestartApplications=no
VersionInfoVersion={#MyAppVersion}
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription={#MyAppName} Setup
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "german"; MessagesFile: "compiler:Languages\German.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; \
    GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "autostart"; Description: "{cm:AutoStartProgram,{#MyAppName}}"; \
    GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#MySourceDir}\*"; DestDir: "{app}"; \
    Flags: ignoreversion recursesubdirs createallsubdirs
Source: "bttext-install-mode.json"; DestDir: "{app}\_internal"; \
    Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; \
    Tasks: desktopicon
Name: "{userstartup}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; \
    Tasks: autostart

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; \
    Flags: nowait postinstall skipifsilent

[CustomMessages]
english.AutoStartProgram=Start %1 automatically when I sign in
german.AutoStartProgram=%1 bei der Anmeldung automatisch starten
english.RemoveUserDataPrompt=Do you also want to permanently delete all btText settings and databases stored in {userappdata}\btText? External databases will not be deleted. This cannot be undone.
german.RemoveUserDataPrompt=Möchten Sie zusätzlich alle btText-Einstellungen und Datenbanken unter {userappdata}\btText dauerhaft löschen? Externe Datenbanken werden nicht gelöscht. Dies kann nicht rückgängig gemacht werden.
english.RemoveUserDataFailed=Not all btText user data could be removed. Please delete {userappdata}\btText manually.
german.RemoveUserDataFailed=Nicht alle btText-Nutzerdaten konnten entfernt werden. Bitte löschen Sie {userappdata}\btText manuell.
english.ApplicationStillRunning=btText is still running. Close btText before uninstalling it, then click Retry.
german.ApplicationStillRunning=btText wird noch ausgeführt. Schließen Sie btText vor der Deinstallation und klicken Sie anschließend auf Wiederholen.

[Code]
var
  RemoveUserData: Boolean;

const
  EVENT_MODIFY_STATE = $0002;
  UpdateShutdownEventName = 'Local\btText.UpdateShutdown';

function OpenEvent(
  DesiredAccess: LongWord;
  InheritHandle: Boolean;
  Name: string
): THandle;
  external 'OpenEventW@kernel32.dll stdcall';
function SetEvent(Event: THandle): Boolean;
  external 'SetEvent@kernel32.dll stdcall';
function CloseHandle(Handle: THandle): Boolean;
  external 'CloseHandle@kernel32.dll stdcall';

procedure SignalRunningApplicationToExit;
var
  ShutdownEvent: THandle;
begin
  ShutdownEvent := OpenEvent(
    EVENT_MODIFY_STATE,
    False,
    UpdateShutdownEventName
  );
  if ShutdownEvent <> 0 then
  begin
    SetEvent(ShutdownEvent);
    CloseHandle(ShutdownEvent);
  end;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  if CurPageID = wpReady then
    SignalRunningApplicationToExit;
  Result := True;
end;

function PrepareToInstall(var NeedsRestart: Boolean): string;
begin
  SignalRunningApplicationToExit;
  Result := '';
end;

function InitializeUninstall: Boolean;
var
  MutexName: String;
  WaitAttempt: Integer;
begin
  MutexName := ExpandConstant('{#MyAppName}-{username}');
  while CheckForMutexes(MutexName) do
  begin
    SignalRunningApplicationToExit;
    for WaitAttempt := 1 to 50 do
    begin
      if not CheckForMutexes(MutexName) then
        Break;
      Sleep(100);
    end;
    if not CheckForMutexes(MutexName) then
      Break;
    if SuppressibleMsgBox(
      ExpandConstant(CustomMessage('ApplicationStillRunning')),
      mbError,
      MB_RETRYCANCEL,
      IDRETRY
    ) <> IDRETRY then
    begin
      Result := False;
      Exit;
    end;
  end;
  Result := True;
end;

procedure CurUninstallStepChanged(
  CurUninstallStep: TUninstallStep
);
begin
  if CurUninstallStep = usUninstall then
  begin
    RemoveUserData :=
      SuppressibleMsgBox(
        ExpandConstant(CustomMessage('RemoveUserDataPrompt')),
        mbConfirmation,
        MB_YESNO,
        IDNO
      ) = IDYES;
  end;
  if (CurUninstallStep = usPostUninstall) and RemoveUserData then
  begin
    if not DelTree(
      ExpandConstant('{userappdata}\btText'),
      True,
      True,
      True
    ) then
    begin
      SuppressibleMsgBox(
        ExpandConstant(CustomMessage('RemoveUserDataFailed')),
        mbError,
        MB_OK,
        IDOK
      );
    end;
  end;
end;
