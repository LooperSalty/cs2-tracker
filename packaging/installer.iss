; Installeur Windows de CS2 Tracker (Inno Setup 6).
;
; Construit avec :
;   iscc packaging\installer.iss
;
; Prerequis : dist\CS2Tracker.exe et overlay\build\Release\CS2TrackerOverlay.exe
; doivent exister. Lance packaging\build.ps1 et overlay\build.ps1 avant.

#define AppName        "CS2 Tracker"
#define AppVersion     "1.8.0"
#define AppPublisher   "LooperSalty"
#define AppURL         "https://github.com/LooperSalty/cs2-tracker"
#define MainExe        "CS2Tracker.exe"
#define OverlayExe     "CS2TrackerOverlay.exe"

[Setup]
AppId={{7C4F1E2A-9B3D-4E51-A7C8-2F6D0B95E413}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}/issues
AppUpdatesURL={#AppURL}/releases

; Installation par utilisateur : aucune elevation demandee, donc aucune
; invite UAC. L'application n'ecrit que dans son propre dossier de donnees.
PrivilegesRequired=lowest
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename=CS2Tracker-Setup-{#AppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
ArchitecturesAllowed=x64compatible
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\{#MainExe}
LicenseFile=..\LICENSE

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; \
    GroupDescription: "{cm:AdditionalIcons}"
Name: "overlay"; Description: "Installer aussi l'overlay affiche par-dessus le jeu"; \
    GroupDescription: "Composants :"
Name: "startup"; Description: "Lancer CS2 Tracker au demarrage de Windows"; \
    GroupDescription: "Demarrage :"; Flags: unchecked

[Files]
Source: "..\dist\{#MainExe}"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\overlay\build\Release\{#OverlayExe}"; DestDir: "{app}"; \
    Flags: ignoreversion skipifsourcedoesntexist; Tasks: overlay
Source: "..\README.md";    DestDir: "{app}"; Flags: ignoreversion isreadme
Source: "..\README.fr.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\LICENSE";      DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#MainExe}"
Name: "{group}\Overlay en jeu"; Filename: "{app}\{#OverlayExe}"; Tasks: overlay
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#MainExe}"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
    ValueType: string; ValueName: "CS2Tracker"; \
    ValueData: """{app}\{#MainExe}"""; Flags: uninsdeletevalue; Tasks: startup

[Run]
Filename: "{app}\{#MainExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; \
    Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Le dossier de donnees survit volontairement a la desinstallation : il
; contient l'historique de statistiques, que l'utilisateur peut vouloir garder.
; Seuls les fichiers temporaires sont effaces.
Type: filesandordirs; Name: "{app}\_internal"

[Code]
{ L'application se ferme dans la zone de notification : une mise a jour
  echouerait silencieusement si une instance tournait encore. }
function InitializeSetup(): Boolean;
var
  ResultCode: Integer;
begin
  Exec('taskkill.exe', '/F /IM {#MainExe} /IM {#OverlayExe}', '',
       SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Result := True;
end;
