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

; No files below {userappdata}\btText are registered with Setup. Consequently,
; uninstalling removes program files and shortcuts but preserves user settings
; and databases managed by the application.
