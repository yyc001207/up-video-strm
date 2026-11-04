; up-video-strm Windows 安装包脚本（Inno Setup 6）
;
; 由 packaging\build.ps1 调用：ISCC /DMyAppVersion=x.y.z packaging\installer.iss
; 也可在 Inno Setup Compiler 中直接打开后编译。
;
; 安装形态：按当前用户安装到 %LOCALAPPDATA%\Programs\up-video-strm（不需要管理员权限）。
; 运行期数据统一落在 %LOCALAPPDATA%\up-video-strm（数据库/日志/STRM 输出），卸载不删除。

#ifndef MyAppVersion
  #define MyAppVersion "1.0.0"
#endif

#define MyAppName "up-video-strm"
#define MyAppPublisher "up-video-strm"
#define MyAppExeName "up-video-strm.exe"
#define MyAppId "{{B3C1D8E4-5A72-4C9F-8E61-7D2A4F0B9C15}"

[Setup]
AppId={#MyAppId}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\up-video-strm
VersionInfoVersion={#MyAppVersion}.0
VersionInfoProductVersion={#MyAppVersion}
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription={#MyAppName} Setup
VersionInfoProductName={#MyAppName}
VersionInfoCopyright=MIT License
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=up-video-strm-{#MyAppVersion}-win-x64-setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupIconFile=app.ico
ArchitecturesAllowed=x64compatible
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加任务:"; Flags: unchecked
Name: "autostart"; Description: "开机自动启动（登录后后台启动服务）"; GroupDescription: "附加任务:"; Flags: unchecked

[Files]
Source: "..\dist\up-video-strm\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Comment: "启动 up-video-strm"
Name: "{group}\卸载 {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; \
    ValueName: "up-video-strm"; ValueData: """{app}\{#MyAppExeName}"""; \
    Tasks: autostart; Flags: uninsdeletevalue

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "立即启动 {#MyAppName}"; Flags: nowait postinstall skipifsilent

; 注意：数据目录 %LOCALAPPDATA%\up-video-strm（数据库/日志/STRM/字幕）刻意不写入 [UninstallDelete]，
; 卸载时保留，重装后可直接沿用原有配置与已生成文件。

[Code]
{ Edge WebView2 运行时检测：应用窗口依赖它，缺失时给出明确指引而不是装完打不开。 }
function WebView2Installed(): Boolean;
begin
  Result :=
    RegKeyExists(HKLM, 'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}') or
    RegKeyExists(HKLM, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}') or
    RegKeyExists(HKCU, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}');
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    Log('up-video-strm 数据目录：' + ExpandConstant('{localappdata}\up-video-strm'));
    if not WebView2Installed() then
      MsgBox('未检测到 Microsoft Edge WebView2 运行时，程序窗口可能无法打开。' + #13#10 + #13#10 +
             '请先安装 WebView2 运行时后重新打开程序：' + #13#10 +
             'https://developer.microsoft.com/microsoft-edge/webview2/',
             mbInformation, MB_OK);
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  { 应用内「开机自启」写的是 HKCU Run，卸载时一并清掉，避免残留指向已删除的 exe。
    旧版本（video-strm）写入的值名同样清理，避免升级安装后遗留失效自启项。 }
  if CurUninstallStep = usUninstall then
  begin
    RegDeleteValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Run', 'up-video-strm');
    RegDeleteValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Run', 'video-strm');
  end;
end;
