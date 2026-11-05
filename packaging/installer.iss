; up-video-strm Windows 安装包脚本（Inno Setup 6）
;
; 由 packaging\build.ps1 调用：
;   正式版：ISCC /DMyAppVersion=x.y.z installer.iss
;   测试版：ISCC /DMyAppVersion=x.y.z /DMyTestBuild=1 installer.iss   （经 packaging\build-test.ps1）
; 也可在 Inno Setup Compiler 中直接打开后编译（默认按正式版处理）。
;
; 安装形态：按当前用户安装到 %LOCALAPPDATA%\Programs\<应用名>（不需要管理员权限）。
; 运行期数据落在 %LOCALAPPDATA%\<应用名>（数据库/日志/STRM 输出），卸载不删除。
; 测试版（up-video-strm-test）与正式版使用不同 AppId / 安装目录 / 数据目录 / 自启动项，
; 可同时安装、同时运行，互不影响。

#ifndef MyAppVersion
  #define MyAppVersion "1.0.0"
#endif

#ifdef MyTestBuild
  ; 测试版：独立安装身份，与正式版并存
  #define MyAppName "up-video-strm-test"
  #define MyAppExeName "up-video-strm-test.exe"
  #define MyAppId "{{6F0C2A9E-2D47-4B8A-9C31-5E7B1D4A8F26}"
  #define MyAppDirName "up-video-strm-test"
  #define MyDataDirName "up-video-strm-test"
#else
  ; 正式版
  #define MyAppName "up-video-strm"
  #define MyAppExeName "up-video-strm.exe"
  #define MyAppId "{{B3C1D8E4-5A72-4C9F-8E61-7D2A4F0B9C15}}"
  #define MyAppDirName "up-video-strm"
  #define MyDataDirName "up-video-strm"
#endif

#define MyAppPublisher "up-video-strm"

[Setup]
AppId={#MyAppId}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\{#MyAppDirName}
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
OutputBaseFilename={#MyAppName}-{#MyAppVersion}-win-x64-setup
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
Source: "..\dist\{#MyAppDirName}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Comment: "启动 {#MyAppName}"
Name: "{group}\卸载 {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; \
    ValueName: "{#MyAppName}"; ValueData: """{app}\{#MyAppExeName}"""; \
    Tasks: autostart; Flags: uninsdeletevalue

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "立即启动 {#MyAppName}"; Flags: nowait postinstall skipifsilent

; 注意：数据目录 %LOCALAPPDATA%\{#MyDataDirName}（数据库/日志/STRM/字幕）刻意不写入 [UninstallDelete]，
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
    Log('{#MyAppName} 数据目录：' + ExpandConstant('{localappdata}\{#MyDataDirName}'));
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
    正式版同时清理旧版本（video-strm）写入的值名；测试版只清理自己的值名。 }
  if CurUninstallStep = usUninstall then
  begin
    RegDeleteValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Run', '{#MyAppName}');
#ifdef MyTestBuild
    { 测试版不碰正式版的自启动项 }
#else
    RegDeleteValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Run', 'video-strm');
#endif
  end;
end;
