; ==============================================================================
; TRINETRA Windows Installer Template (Inno Setup 6 Script)
; Professional customer-specific deployment with isolated runtime configuration
; ==============================================================================

#define MyAppName "TRINETRA"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Veronic"
#define MyAppURL "https://veronic.in"
#define MyAppExeName "TRINETRA.exe"

[Setup]
AppId={{E83B5E09-7A8E-4E9A-A37F-4B7415D430C1}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\TRINETRA
DisableProgramGroupPage=yes
OutputBaseFilename=TRINETRA-Setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
OutputDir=output
SetupIconFile=trinetra.ico
UninstallIconFile=trinetra.ico

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Dirs]
Name: "{app}\data"; Permissions: users-full
Name: "{app}\snapshots"; Permissions: users-full
Name: "{app}\config"; Permissions: users-full

[Files]
; Packaged application binaries and bundled frontend assets
Source: "..\backend\dist\TRINETRA\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

; Customer-specific configuration files
Source: "..\backend\.env"; DestDir: "{app}"; Flags: ignoreversion onlyifdoesntexist; Check: FileExists(ExpandConstant('{src}\.env'))
Source: "..\backend\serviceAccountKey.json"; DestDir: "{app}"; Flags: ignoreversion onlyifdoesntexist; Check: FileExists(ExpandConstant('{src}\serviceAccountKey.json'))

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon; IconFilename: "{app}\{#MyAppExeName}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Preserve customer sqlite database and snapshots during uninstall
