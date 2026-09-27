; Inno Setup script for the Symple Windows installer.
; Build:  ISCC /DAppVersion=0.1.0 packaging\symple.iss   (after PyInstaller)

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{6E0B7C2A-4F0E-4B5B-9E8C-5D2F1A7C3B91}
AppName=Symple
AppVersion={#AppVersion}
AppVerName=Symple {#AppVersion}
AppPublisher=Ales Toman
AppPublisherURL=https://github.com/alestoman5/symple
AppSupportURL=https://github.com/alestoman5/symple/issues
DefaultDirName={autopf}\Symple
DefaultGroupName=Symple
DisableProgramGroupPage=yes
; Install for the current user without admin rights; the user may choose "all users".
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
LicenseFile=..\LICENSE
OutputDir=..\dist
OutputBaseFilename=Symple-{#AppVersion}-Setup
SetupIconFile=..\assets\symple.ico
UninstallDisplayIcon={app}\Symple.exe
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
ChangesAssociations=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "fileassoc"; Description: "Open .syw worksheets with Symple"; GroupDescription: "File types:"

[Files]
Source: "..\dist\Symple\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Symple"; Filename: "{app}\Symple.exe"
Name: "{group}\Example worksheet"; Filename: "{app}\Symple.exe"; Parameters: """{app}\examples\tour.syw"""
Name: "{group}\Uninstall Symple"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Symple"; Filename: "{app}\Symple.exe"; Tasks: desktopicon

[Registry]
Root: HKA; Subkey: "Software\Classes\.syw"; ValueType: string; ValueName: ""; ValueData: "Symple.Worksheet"; Flags: uninsdeletevalue; Tasks: fileassoc
Root: HKA; Subkey: "Software\Classes\Symple.Worksheet"; ValueType: string; ValueName: ""; ValueData: "Symple worksheet"; Flags: uninsdeletekey; Tasks: fileassoc
Root: HKA; Subkey: "Software\Classes\Symple.Worksheet\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\Symple.exe,0"; Tasks: fileassoc
Root: HKA; Subkey: "Software\Classes\Symple.Worksheet\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\Symple.exe"" ""%1"""; Tasks: fileassoc

[Run]
Filename: "{app}\Symple.exe"; Description: "{cm:LaunchProgram,Symple}"; Flags: nowait postinstall skipifsilent
