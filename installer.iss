; Inno Setup script for Hearsay
; Compile with Inno Setup 6+: iscc installer.iss

[Setup]
AppName=Hearsay
AppVersion=1.0.0
AppPublisher=Hearsay
AppPublisherURL=https://github.com/parkscloud/Hearsay
DefaultDirName={autopf}\Hearsay
DefaultGroupName=Hearsay
OutputDir=installer_output
OutputBaseFilename=HearsaySetup
SetupIconFile=src\assets\icon.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
CloseApplications=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\Hearsay.exe

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"
Name: "startupicon"; Description: "Start Hearsay with Windows"; GroupDescription: "Startup:"; Flags: checked

[Files]
Source: "dist\Hearsay\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Hearsay"; Filename: "{app}\Hearsay.exe"
Name: "{group}\Uninstall Hearsay"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Hearsay"; Filename: "{app}\Hearsay.exe"; Tasks: desktopicon
Name: "{commonstartup}\Hearsay"; Filename: "{app}\Hearsay.exe"; Tasks: startupicon

[Run]
Filename: "{app}\Hearsay.exe"; Description: "Launch Hearsay"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{localappdata}\Hearsay"
