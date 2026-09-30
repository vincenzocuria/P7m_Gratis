[Setup]
AppId={{D82F91A2-4301-4F2A-A81E-2B6A56E2140A}
AppName=P7M Viewer PA
AppVersion=2.1.0
AppPublisher=Vincenzo Curia
DefaultDirName={userpf}\P7M Viewer PA
DefaultGroupName=P7M Viewer PA
DisableProgramGroupPage=yes
DisableDirPage=yes
UsePreviousAppDir=no
OutputDir=dist
OutputBaseFilename=P7MViewer_Setup
SetupIconFile=app_icon.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "it"; MessagesFile: "compiler:Languages\Italian.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; Flags: unchecked
Name: "assocp7m"; Description: "Associa i file .p7m a P7M Viewer PA per l'apertura automatica"

[Files]
Source: "dist\P7MViewer\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\P7M Viewer PA"; Filename: "{app}\P7MViewer.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\P7M Viewer PA"; Filename: "{app}\P7MViewer.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Classes\.p7m"; ValueType: string; ValueData: "P7MViewer.Document"; Flags: uninsdeletevalue; Tasks: assocp7m
Root: HKCU; Subkey: "Software\Classes\P7MViewer.Document"; ValueType: string; ValueData: "Documento Firmato Digitalmente P7M"; Flags: uninsdeletekey; Tasks: assocp7m
Root: HKCU; Subkey: "Software\Classes\P7MViewer.Document\DefaultIcon"; ValueType: string; ValueData: "{app}\P7MViewer.exe,0"; Flags: uninsdeletekey; Tasks: assocp7m
Root: HKCU; Subkey: "Software\Classes\P7MViewer.Document\shell\open\command"; ValueType: string; ValueData: """{app}\P7MViewer.exe"" ""%1"""; Flags: uninsdeletekey; Tasks: assocp7m

[Run]
Filename: "{app}\P7MViewer.exe"; WorkingDir: "{app}"; Description: "{cm:LaunchProgram,P7M Viewer PA}"; Flags: nowait postinstall skipifsilent

[Code]
procedure InitializeWizard();
begin
  // Rimuovi il bordo grigio ed evita il taglio del checkbox/testo nella lista delle task
  WizardForm.TasksList.BorderStyle := bsNone;
  WizardForm.TasksList.Left := WizardForm.TasksList.Left + ScaleX(4);
  WizardForm.TasksList.Width := WizardForm.TasksList.Width - ScaleX(8);
  WizardForm.TasksList.Height := ScaleY(90);

  // Rimuovi il bordo grigio, riposiziona ed evita il taglio del checkbox/testo nella schermata finale
  WizardForm.RunList.BorderStyle := bsNone;
  WizardForm.RunList.Left := WizardForm.RunList.Left + ScaleX(4);
  WizardForm.RunList.Width := WizardForm.RunList.Width - ScaleX(8);
  WizardForm.RunList.Height := ScaleY(45);
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if CurPageID = wpFinished then
  begin
    // Posiziona RunList perfettamente sotto FinishedLabel per evitare qualsiasi sovrapposizione col testo
    WizardForm.RunList.Top := WizardForm.FinishedLabel.Top + WizardForm.FinishedLabel.Height + ScaleY(12);
  end;
end;
