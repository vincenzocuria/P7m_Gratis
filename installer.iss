[Setup]
AppId={{D82F91A2-4301-4F2A-A81E-2B6A56E2140A}
AppName=P7M Viewer PA
AppVersion=1.0.0
AppPublisher=Antigravity PA
DefaultDirName={userpf}\P7M Viewer PA
DefaultGroupName=P7M Viewer PA
DisableProgramGroupPage=yes
OutputDir=dist
OutputBaseFilename=P7MViewer_Setup_v1.0
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest

[Languages]
Name: "it"; MessagesFile: "compiler:Languages\Italian.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "assocp7m"; Description: "Associa i file .p7m a P7M Viewer PA per l'apertura automatica"; GroupDescription: "Integrazione di sistema:"

[Files]
Source: "dist\P7MViewer.exe"; DestDir: "{app}"; Flags: ignoreversion


[Icons]
Name: "{group}\P7M Viewer PA"; Filename: "{app}\P7MViewer.exe"
Name: "{autodesktop}\P7M Viewer PA"; Filename: "{app}\P7MViewer.exe"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Classes\.p7m"; ValueType: string; ValueData: "P7MViewer.Document"; Flags: uninsdeletevalue; Tasks: assocp7m
Root: HKCU; Subkey: "Software\Classes\P7MViewer.Document"; ValueType: string; ValueData: "Documento Firmato Digitalmente P7M"; Flags: uninsdeletekey; Tasks: assocp7m
Root: HKCU; Subkey: "Software\Classes\P7MViewer.Document\DefaultIcon"; ValueType: string; ValueData: "{app}\P7MViewer.exe,0"; Flags: uninsdeletekey; Tasks: assocp7m
Root: HKCU; Subkey: "Software\Classes\P7MViewer.Document\shell\open\command"; ValueType: string; ValueData: """{app}\P7MViewer.exe"" ""%1"""; Flags: uninsdeletekey; Tasks: assocp7m

[Run]
Filename: "{app}\P7MViewer.exe"; Description: "{cm:LaunchProgram,P7M Viewer PA}"; Flags: nowait postinstall skipifsilent

[Code]
procedure InitializeWizard();
begin
  // Aumenta l'altezza e allinea il margine sinistro della lista dei task per evitare il taglio del checkbox o del testo
  WizardForm.TasksList.Left := WizardForm.TasksList.Left + 2;
  WizardForm.TasksList.Width := WizardForm.TasksList.Width - 4;
  WizardForm.TasksList.Height := WizardForm.TasksList.Height + 35;

  // Riposiziona ed espande il RunList nella schermata finale per mostrare chiaramente il checkbox "Esegui P7M Viewer PA"
  WizardForm.RunList.Top := WizardForm.RunList.Top - 15;
  WizardForm.RunList.Height := WizardForm.RunList.Height + 40;
  WizardForm.RunList.Left := WizardForm.RunList.Left + 2;
  WizardForm.RunList.Width := WizardForm.RunList.Width - 4;
end;

