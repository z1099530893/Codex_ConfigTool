#define MyAppName "Codex 配置助手"
#define MyAppPublisher "k.x"
#define MyAppExeName "CodexConfigTool.exe"
#ifndef MyAppVersion
  #define MyAppVersion "1.4.0"
#endif

[Setup]
AppId={{0D5D6684-7E4C-4C56-B7D0-75DF8D03D2C0}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL=https://github.com/z1099530893/Codex_ConfigTool
AppSupportURL=https://github.com/z1099530893/Codex_ConfigTool/issues
AppUpdatesURL=https://github.com/z1099530893/Codex_ConfigTool/releases/latest
DefaultDirName={localappdata}\Programs\CodexConfigTool
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=CodexConfigTool-Setup-v{#MyAppVersion}
SetupIconFile=..\assets\app_icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
CloseApplications=force
RestartApplications=no
AppMutex=Local\z1099530893.CodexConfigTool
VersionInfoVersion={#MyAppVersion}.0
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription={#MyAppName} 安装程序
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}

[Languages]
Name: "chinesesimp"; MessagesFile: "compiler:Default.isl,ChineseSimplifiedOverrides.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: checkedonce

[Files]
Source: "..\dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{userdesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[Code]
var
  UninstallDataForm: TForm;
  KeepUserDataRadio: TNewRadioButton;
  DeleteUserDataRadio: TNewRadioButton;

function AskUninstallDataPolicy(): Boolean;
var
  PromptLabel: TNewStaticText;
  ButtonPanel: TPanel;
  ContinueButton: TNewButton;
  CancelButton: TNewButton;
begin
  UninstallDataForm := TForm.Create(nil);
  UninstallDataForm.Caption := ExpandConstant('{cm:UninstallDataTitle}');
  UninstallDataForm.ClientWidth := ScaleX(440);
  UninstallDataForm.ClientHeight := ScaleY(190);
  UninstallDataForm.Position := poScreenCenter;
  UninstallDataForm.BorderStyle := bsDialog;

  PromptLabel := TNewStaticText.Create(UninstallDataForm);
  PromptLabel.Parent := UninstallDataForm;
  PromptLabel.Caption := ExpandConstant('{cm:UninstallDataPrompt}');
  PromptLabel.Left := ScaleX(20);
  PromptLabel.Top := ScaleY(18);
  PromptLabel.Width := ScaleX(395);

  KeepUserDataRadio := TNewRadioButton.Create(UninstallDataForm);
  KeepUserDataRadio.Parent := UninstallDataForm;
  KeepUserDataRadio.Caption := ExpandConstant('{cm:KeepUserDataOption}');
  KeepUserDataRadio.Left := ScaleX(24);
  KeepUserDataRadio.Top := ScaleY(58);
  KeepUserDataRadio.Width := ScaleX(380);
  KeepUserDataRadio.Checked := True;

  DeleteUserDataRadio := TNewRadioButton.Create(UninstallDataForm);
  DeleteUserDataRadio.Parent := UninstallDataForm;
  DeleteUserDataRadio.Caption := ExpandConstant('{cm:DeleteUserDataOption}');
  DeleteUserDataRadio.Left := ScaleX(24);
  DeleteUserDataRadio.Top := ScaleY(88);
  DeleteUserDataRadio.Width := ScaleX(380);

  ButtonPanel := TPanel.Create(UninstallDataForm);
  ButtonPanel.Parent := UninstallDataForm;
  ButtonPanel.Align := alBottom;
  ButtonPanel.Height := ScaleY(52);
  ButtonPanel.BevelOuter := bvNone;

  CancelButton := TNewButton.Create(UninstallDataForm);
  CancelButton.Parent := ButtonPanel;
  CancelButton.Caption := ExpandConstant('{cm:ButtonCancel}');
  CancelButton.ModalResult := mrCancel;
  CancelButton.Left := ScaleX(320);
  CancelButton.Top := ScaleY(12);
  CancelButton.Width := ScaleX(95);

  ContinueButton := TNewButton.Create(UninstallDataForm);
  ContinueButton.Parent := ButtonPanel;
  ContinueButton.Caption := ExpandConstant('{cm:UninstallContinueButton}');
  ContinueButton.ModalResult := mrOk;
  ContinueButton.Left := ScaleX(215);
  ContinueButton.Top := ScaleY(12);
  ContinueButton.Width := ScaleX(95);
  UninstallDataForm.ActiveControl := KeepUserDataRadio;

  Result := UninstallDataForm.ShowModal = mrOk;
  if Result and DeleteUserDataRadio.Checked then
  begin
    DelTree(ExpandConstant('{userappdata}\CodexConfigTool'), True, True, True);
    DelTree(ExpandConstant('{userprofile}\.codex\backups'), True, True, True);
  end;
end;

function InitializeUninstall(): Boolean;
begin
  Result := AskUninstallDataPolicy();
end;
