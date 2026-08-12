[Setup]
AppId={{D82F91A2-4301-4F2A-A81E-2B6A56E2140A}
AppName=P7M Viewer PA
AppVersion=2.0.0
AppPublisher=Antigravity PA
DefaultDirName={userpf}\P7M Viewer PA
DefaultGroupName=P7M Viewer PA
DisableProgramGroupPage=yes
DisableDirPage=yes
UsePreviousAppDir=no
OutputDir=dist
OutputBaseFilename=P7MViewer_Setup_v2.0
SetupIconFile=app_icon.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest

[Languages]
Name: "it"; MessagesFile: "compiler:Languages\Italian.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; Flags: unchecked
Name: "assocp7m"; Description: "Associa i file .p7m a P7M Viewer PA per l'apertura automatica"

[Files]
Source: "dist\P7MViewer.exe"; DestDir: "{app}"; Flags: ignoreversion

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
var
  HeaderLabel: TNewStaticText;
  DesktopCheck: TNewCheckBox;
  AssocCheck: TNewCheckBox;
  RunCheck: TNewCheckBox;

procedure DesktopCheckClick(Sender: TObject);
begin
  if WizardForm.TasksList.Items.Count > 0 then
    WizardForm.TasksList.Checked[0] := DesktopCheck.Checked;
end;

procedure AssocCheckClick(Sender: TObject);
begin
  if WizardForm.TasksList.Items.Count > 1 then
    WizardForm.TasksList.Checked[1] := AssocCheck.Checked;
end;

procedure RunCheckClick(Sender: TObject);
begin
  if WizardForm.RunList.Items.Count > 0 then
    WizardForm.RunList.Checked[0] := RunCheck.Checked;
end;

procedure InitializeWizard();
var
  BaseLeft, BaseTop: Integer;
begin
  // Nascondi completamente il controllo TasksList (la ListBox col bordo grigio)
  WizardForm.TasksList.Visible := False;

  // Utilizza posizione e larghezza trasmesse da Inno Setup per la TasksList
  BaseLeft := WizardForm.TasksList.Left;
  BaseTop := WizardForm.TasksList.Top;

  // Intestazione del gruppo "Icone ed integrazioni aggiuntive:"
  HeaderLabel := TNewStaticText.Create(WizardForm);
  HeaderLabel.Parent := WizardForm.SelectTasksPage;
  HeaderLabel.Left := BaseLeft;
  HeaderLabel.Top := BaseTop;
  HeaderLabel.Font.Style := [fsBold];
  HeaderLabel.Caption := 'Icone ed integrazioni aggiuntive:';

  // Checkbox 1: Icona Desktop
  DesktopCheck := TNewCheckBox.Create(WizardForm);
  DesktopCheck.Parent := WizardForm.SelectTasksPage;
  DesktopCheck.Left := BaseLeft;
  DesktopCheck.Top := BaseTop + ScaleY(28);
  DesktopCheck.Width := WizardForm.TasksList.Width;
  DesktopCheck.Height := ScaleY(22);
  DesktopCheck.Caption := 'Crea un''icona sul desktop';
  DesktopCheck.Checked := False;
  DesktopCheck.OnClick := @DesktopCheckClick;

  // Checkbox 2: Associazione File P7M
  AssocCheck := TNewCheckBox.Create(WizardForm);
  AssocCheck.Parent := WizardForm.SelectTasksPage;
  AssocCheck.Left := BaseLeft;
  AssocCheck.Top := BaseTop + ScaleY(56);
  AssocCheck.Width := WizardForm.TasksList.Width;
  AssocCheck.Height := ScaleY(28);
  AssocCheck.Caption := 'Associa i file .p7m a P7M Viewer PA per l''apertura automatica';
  AssocCheck.Checked := True;
  AssocCheck.OnClick := @AssocCheckClick;

  // Nascondi completamente il controllo RunList nella schermata finale (la box col bordo grigio)
  WizardForm.RunList.Visible := False;

  // Checkbox personalizzato "Avvia P7M Viewer PA" nella schermata finale
  RunCheck := TNewCheckBox.Create(WizardForm);
  RunCheck.Parent := WizardForm.FinishedPage;
  RunCheck.Left := WizardForm.RunList.Left;
  RunCheck.Top := WizardForm.RunList.Top;
  RunCheck.Width := WizardForm.RunList.Width;
  RunCheck.Height := ScaleY(28);
  RunCheck.Caption := 'Avvia P7M Viewer PA';
  RunCheck.Checked := True;
  RunCheck.OnClick := @RunCheckClick;
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if CurPageID = wpSelectTasks then
  begin
    WizardForm.TasksList.Visible := False;
    if WizardForm.TasksList.Items.Count > 0 then
      WizardForm.TasksList.Checked[0] := DesktopCheck.Checked;
    if WizardForm.TasksList.Items.Count > 1 then
      WizardForm.TasksList.Checked[1] := AssocCheck.Checked;
  end;
  if CurPageID = wpFinished then
  begin
    WizardForm.RunList.Visible := False;
    if WizardForm.RunList.Items.Count > 0 then
      WizardForm.RunList.Checked[0] := RunCheck.Checked;
  end;
end;
