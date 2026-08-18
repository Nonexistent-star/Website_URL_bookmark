; WebJump 安装脚本（Inno Setup 6）
#define MyAppName "WebJump 网站快速跳转"
#define MyAppVersion "1.1.0"
#define MyAppPublisher "WebJump"
#define MyAppExeName "WebJump.exe"
#define AppGuid "{8F2B6C3A-9D4E-4F1B-8C7A-5745424A554D}"

[Setup]
AppId={{#AppGuid}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\WebJump
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=installer_out
OutputBaseFilename=WebJump-Setup-{#MyAppVersion}
SetupIconFile=app.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=commandline
ArchitecturesInstallIn64BitMode=x64
MinVersion=6.1sp1
ShowLanguageDialog=no

[Languages]
Name: "chs"; MessagesFile: "tools\ChineseSimplified.isl"

[Files]
Source: "dist\WebJump.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "web-kz\*"; DestDir: "{app}\web-kz"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "installer_res\网站列表.txt"; DestDir: "{app}"; Flags: onlyifdoesntexist uninsneveruninstall
Source: "tools\MicrosoftEdgeWebView2RuntimeInstallerX64.exe"; Flags: dontcopy

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\卸载 {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加选项："; Flags: unchecked

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "立即启动 {#MyAppName}"; Flags: nowait postinstall skipifsilent runascurrentuser

[Code]
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  rc: Integer;
begin
  Result := '';
  Exec('taskkill', '/IM WebJump.exe /F', '', SW_HIDE, ewWaitUntilTerminated, rc);
end;

function InitializeUninstall(): Boolean;
var
  rc: Integer;
begin
  Exec('taskkill', '/IM WebJump.exe /F', '', SW_HIDE, ewWaitUntilTerminated, rc);
  Result := True;
end;

function WebView2Installed(): Boolean;
var
  pv: String;
begin
  Result := False;
  if RegQueryStringValue(HKLM, 'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E2C5}', 'pv', pv) and (pv <> '') and (pv <> '0.0.0.0') then begin Result := True; Exit; end;
  if RegQueryStringValue(HKLM, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E2C5}', 'pv', pv) and (pv <> '') and (pv <> '0.0.0.0') then begin Result := True; Exit; end;
  if RegQueryStringValue(HKCU, 'Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E2C5}', 'pv', pv) and (pv <> '') and (pv <> '0.0.0.0') then Result := True;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  rc: Integer;
begin
  if CurStep = ssPostInstall then
  begin
    if not WebView2Installed() then
    begin
      ExtractTemporaryFile('MicrosoftEdgeWebView2RuntimeInstallerX64.exe');
      Exec(ExpandConstant('{tmp}\MicrosoftEdgeWebView2RuntimeInstallerX64.exe'), '/silent /install', '', SW_HIDE, ewWaitUntilTerminated, rc);
    end;
  end;
end;
