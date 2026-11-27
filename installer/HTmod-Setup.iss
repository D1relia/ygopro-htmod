[Setup]
AppId={{8D6E4A2F-3C91-4B7E-9F1A-5B2C8E4D1A90}
AppName=YGOPro KoishiPro-HTmod (萌卡美化版)
AppVersion=1.0.0
AppPublisher=HelloTCG / HTmod
DefaultDirName={userappdata}\MyCardLibrary\ygopro
AppendDefaultDirName=no
DisableDirPage=no
DirExistsWarning=no
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
UsePreviousAppDir=yes
CloseApplications=yes
OutputDir=..\bin\installer
OutputBaseFilename=KoishiPro-HTmod-Setup
Compression=lzma2/max
SolidCompression=yes
UninstallFilesDir={app}\HTmod_Uninstall
WizardStyle=modern
WizardSizePercent=125,115
WizardResizable=yes

[Languages]
Name: "default"; MessagesFile: "compiler:Default.isl"

[Messages]
SetupWindowTitle=安装 — %1
WelcomeLabel1=欢迎安装 [name]
WelcomeLabel2=本程序将为你的萌卡（MyCard）客户端安装深色现代界面与视角优化内核（HTmod）。%n%n安装前会自动备份萌卡官方原版 ygopro.exe，卸载时将自动恢复原版，安全无损。%n%n请先关闭正在运行的 YGOPro 游戏窗口，然后点击「下一步」继续。
WizardSelectDir=选择萌卡 YGOPro 目录
SelectDirDesc=请确认你的萌卡 YGOPro 所在文件夹。
SelectDirLabel3=安装程序会自动检测默认的 AppData\Roaming\MyCardLibrary\ygopro 目录；如果未找到，请点击「浏览」手动选择你的 ygopro 文件夹。
SelectDirBrowseLabel=确认路径无误后点击「下一步」开始安装。
ButtonBrowse=浏览(&R)...
ButtonBack=< 上一步(&B)
ButtonNext=下一步(&N) >
ButtonInstall=立即安装(&I)
ButtonCancel=取消
ButtonFinish=完成(&F)
WizardReady=准备就绪
ReadyLabel1=即将开始安装 [name] 到以下萌卡目录：
WizardInstalling=正在安装
InstallingLabel=正在备份官方内核并写入 HTmod 美化内核，请稍候...
FinishedHeadingLabel=安装完成！
FinishedLabel=YGOPro KoishiPro-HTmod 已成功安装到萌卡目录！%n%n提示：以后萌卡官方如果更新了 YGOPro 核心覆盖回原版，只需重新双击本安装包覆盖一次即可。
ConfirmUninstall=确定要卸载 %1 并还原萌卡官方原版 ygopro.exe 吗？
UninstalledAll=%1 已卸载，萌卡官方原版内核已恢复。

[Types]
Name: "full"; Description: "推荐安装（主程序 + 简中官方译名 + 高清卡图工具）"
Name: "compact"; Description: "仅安装主程序与字体"
Name: "custom"; Description: "自定义安装"; Flags: iscustom

[Components]
Name: "main"; Description: "KoishiPro-HTmod 主程序与 MiSans 字体（必选）"; Types: full compact custom; Flags: fixed
#ifexist "..\bin\installer\SC_Updater.exe"
Name: "sc"; Description: "简中官方译名更新器（更新简中官方译名.exe）"; Types: full
#endif
#ifexist "..\bin\installer\Pics_Updater.exe"
Name: "pics"; Description: "高清卡图替换工具（更新卡图.exe）"; Types: full
Name: "pics\jp"; Description: "日文卡图 (OCG)"; Types: full; Flags: exclusive
Name: "pics\sc"; Description: "简中卡图 (官方简中优先，最新卡包/先行卡自动补齐高清中文图)"; Flags: exclusive
#endif

[Files]
Source: "..\bin\release\x64\YGOPro.exe"; DestDir: "{app}"; DestName: "ygopro.exe"; Components: main; Flags: ignoreversion
#ifexist "fonts\MiSans-Medium.ttf"
Source: "fonts\MiSans-Medium.ttf"; DestDir: "{app}\fonts"; Components: main; Flags: ignoreversion
#endif
#ifexist "..\bin\installer\SC_Updater.exe"
Source: "..\bin\installer\SC_Updater.exe"; DestDir: "{app}"; DestName: "更新简中官方译名.exe"; Components: sc; Flags: ignoreversion
#endif
#ifexist "..\bin\installer\Pics_Updater.exe"
Source: "..\bin\installer\Pics_Updater.exe"; DestDir: "{app}"; DestName: "更新卡图.exe"; Components: pics; Flags: ignoreversion
#endif

[Run]
#ifexist "..\bin\installer\SC_Updater.exe"
Filename: "{app}\更新简中官方译名.exe"; WorkingDir: "{app}"; Components: sc; Description: "立即联网更新简体中文官方译名补丁"; Flags: postinstall nowait skipifsilent
#endif
#ifexist "..\bin\installer\Pics_Updater.exe"
Filename: "{app}\更新卡图.exe"; Parameters: "--lang jp"; WorkingDir: "{app}"; Components: pics\jp; Description: "立即联网同步日文卡图（可在弹出的窗口中选卡组或全卡池）"; Flags: postinstall nowait skipifsilent
Filename: "{app}\更新卡图.exe"; Parameters: "--lang sc"; WorkingDir: "{app}"; Components: pics\sc; Description: "立即联网同步简中官方卡图（可在弹出的窗口中选卡组或全卡池）"; Flags: postinstall nowait skipifsilent
#endif

[Code]
var
  DetectedLabel: TNewStaticText;
  AutoFound: Boolean;

function TryFindMyCardDir(var FoundPath: String): Boolean;
var
  Candidate: String;
begin
  Result := False;
  Candidate := ExpandConstant('{userappdata}\MyCardLibrary\ygopro');
  if FileExists(Candidate + '\ygopro.exe') or FileExists(Candidate + '\cards.cdb') then
  begin
    FoundPath := Candidate;
    Result := True;
    Exit;
  end;
  Candidate := 'C:\MyCardLibrary\ygopro';
  if FileExists(Candidate + '\ygopro.exe') or FileExists(Candidate + '\cards.cdb') then
  begin
    FoundPath := Candidate;
    Result := True;
    Exit;
  end;
  Candidate := 'D:\MyCardLibrary\ygopro';
  if FileExists(Candidate + '\ygopro.exe') or FileExists(Candidate + '\cards.cdb') then
  begin
    FoundPath := Candidate;
    Result := True;
    Exit;
  end;
  Candidate := 'E:\MyCardLibrary\ygopro';
  if FileExists(Candidate + '\ygopro.exe') or FileExists(Candidate + '\cards.cdb') then
  begin
    FoundPath := Candidate;
    Result := True;
    Exit;
  end;
end;

procedure InitializeWizard();
var
  DetectedDir: String;
begin
  AutoFound := False;
  if FileExists(AddBackslash(WizardForm.DirEdit.Text) + 'ygopro.exe') or
     FileExists(AddBackslash(WizardForm.DirEdit.Text) + 'cards.cdb') then
  begin
    AutoFound := True;
  end
  else if TryFindMyCardDir(DetectedDir) then
  begin
    WizardForm.DirEdit.Text := DetectedDir;
    AutoFound := True;
  end;

  DetectedLabel := TNewStaticText.Create(WizardForm.SelectDirPage);
  DetectedLabel.Parent := WizardForm.SelectDirPage;
  DetectedLabel.Left := WizardForm.DirEdit.Left;
  DetectedLabel.Top := WizardForm.DirEdit.Top + WizardForm.DirEdit.Height + 12;
  DetectedLabel.Width := WizardForm.SelectDirPage.Width - DetectedLabel.Left - 16;
  DetectedLabel.WordWrap := True;
  DetectedLabel.AutoSize := True;
  if AutoFound then
    DetectedLabel.Caption := '已自动检测到萌卡 YGOPro 目录，直接点击「下一步」即可安装。'
  else
    DetectedLabel.Caption := '未在默认路径找到萌卡目录，请点击上方「浏览」手动选择你的 MyCardLibrary\ygopro 文件夹（可在萌卡大厅点「浏览本地文件」查看路径）。';
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  Dir: String;
begin
  Result := True;
  if CurPageID = wpSelectDir then
  begin
    Dir := AddBackslash(WizardDirValue);
    if (not FileExists(Dir + 'ygopro.exe')) and (not FileExists(Dir + 'cards.cdb')) then
    begin
      if MsgBox('当前目录中未检测到 ygopro.exe 或 cards.cdb，可能不是萌卡的 YGOPro 文件夹。' + #13#10 + #13#10 +
                '通常路径为：...\MyCardLibrary\ygopro' + #13#10 +
                '是否仍要强制安装到此目录？', mbConfirmation, MB_YESNO) = IDNO then
      begin
        Result := False;
      end;
    end;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  TargetExe, BackupExe: String;
begin
  if CurStep = ssInstall then
  begin
    TargetExe := ExpandConstant('{app}\ygopro.exe');
    BackupExe := ExpandConstant('{app}\ygopro_official.exe.bak');
    if FileExists(TargetExe) and (not FileExists(BackupExe)) then
    begin
      CopyFile(TargetExe, BackupExe, False);
    end;
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  TargetExe, BackupExe: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    TargetExe := ExpandConstant('{app}\ygopro.exe');
    BackupExe := ExpandConstant('{app}\ygopro_official.exe.bak');
    if FileExists(BackupExe) and (not FileExists(TargetExe)) then
    begin
      RenameFile(BackupExe, TargetExe);
    end;
  end;
end;
