; Inno Setup script for Hermes WebUI (Windows x64).
; Driven by build.ps1, which passes these defines:
;   /DAppVersion=0.1.1  /DStaging=...\build\staging  /DPort=8787  /DOutputDir=...\build
; Manual build example:
;   iscc /DAppVersion=0.1.1 /DStaging=build\staging /DPort=8787 /DOutputDir=build hermes.iss

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef Staging
  #define Staging "build\staging"
#endif
#ifndef OutputDir
  #define OutputDir "build"
#endif
#ifndef Port
  #define Port "8787"
#endif

[Setup]
; Stable GUID so upgrades replace in place. Do not change once shipped.
AppId={{8F3C7A92-5D41-4B6E-9C2A-7E1D0B4F8A21}}
AppName=Hermes
AppVersion={#AppVersion}
AppPublisher=Nous Research
AppPublisherURL=https://hermes-agent.nousresearch.com/
DefaultDirName={autopf}\Hermes
DefaultGroupName=Hermes
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\Hermes.exe
SetupIconFile=Hermes.ico
OutputDir={#OutputDir}
OutputBaseFilename=Hermes-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; Per-user install (no admin prompt). autopf -> %LOCALAPPDATA%\Programs when lowest.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional icons:"

[Files]
; The entire staging tree: python\, webui\, agent\, Hermes.exe
Source: "{#Staging}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\Hermes"; Filename: "{app}\Hermes.exe"
Name: "{group}\Uninstall Hermes"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Hermes"; Filename: "{app}\Hermes.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Hermes.exe"; Description: "Launch Hermes now"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; The app dir holds bundled runtime + code; remove it fully on uninstall.
; User data under %LOCALAPPDATA%\hermes is intentionally left in place.
Type: filesandordirs; Name: "{app}"
