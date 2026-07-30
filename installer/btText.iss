; Per-user installer for the PyInstaller onedir build.
; The build supplies these values with ISCC /D switches in the full pipeline.

#ifndef MyAppVersion
  #define MyAppVersion "1.0"
#endif
#ifndef MySourceDir
  #define MySourceDir "..\build\installer-payload\btText"
#endif
#ifndef MyOutputDir
  #define MyOutputDir "..\build"
#endif
#ifndef MyOutputBaseFilename
  #define MyOutputBaseFilename "btText-" + MyAppVersion + "-setup"
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
CloseApplications=yes
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

[Files]
Source: "{#MySourceDir}\*"; DestDir: "{app}"; \
    Flags: ignoreversion recursesubdirs createallsubdirs
Source: "bttext-install-mode.json"; DestDir: "{app}\_internal"; \
    Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; \
    Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; \
    Flags: nowait postinstall skipifsilent

[CustomMessages]
english.RemoveUserDataPrompt=Do you also want to permanently delete all btText settings and databases stored in {userappdata}\btText? External databases will not be deleted. This cannot be undone.
german.RemoveUserDataPrompt=Möchten Sie zusätzlich alle btText-Einstellungen und Datenbanken unter {userappdata}\btText dauerhaft löschen? Externe Datenbanken werden nicht gelöscht. Dies kann nicht rückgängig gemacht werden.
english.RemoveUserDataFailed=Not all btText user data could be removed. Please delete {userappdata}\btText manually.
german.RemoveUserDataFailed=Nicht alle btText-Nutzerdaten konnten entfernt werden. Bitte löschen Sie {userappdata}\btText manuell.
english.ApplicationStillRunning=btText is still running. Close btText before uninstalling it, then click Retry.
german.ApplicationStillRunning=btText wird noch ausgeführt. Schließen Sie btText vor der Deinstallation und klicken Sie anschließend auf Wiederholen.

[Code]
var
  RemoveUserData: Boolean;

function InitializeUninstall: Boolean;
var
  MutexName: String;
begin
  MutexName := ExpandConstant('{#MyAppName}-{username}');
  while CheckForMutexes(MutexName) do
  begin
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
