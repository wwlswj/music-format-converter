#define MyAppName "韶律音乐格式转换器"
#define MyAppPublisher "Wanli Wang"
#define MyAppExeName "ShaoLvMusicConverter.exe"
#define MyAppId "{{C55C3C6D-8E98-49E7-AEFA-4AF7D4BA4FB8}"

[Setup]
AppId={#MyAppId}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\ShaoLv
DefaultGroupName=ShaoLv
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir={#OutputDir}
OutputBaseFilename=ShaoLv-Music-Converter-Setup-{#MyAppVersion}
SetupIconFile={#RepoRoot}\assets\icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
LicenseFile={#RepoRoot}\LICENSE

[Languages]
Name: "chinesesimplified"; MessagesFile: "{#RepoRoot}\packaging\windows\ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "快捷方式："
Name: "skillcodex"; Description: "安装 Codex Skill"; GroupDescription: "Agent Skill："; Flags: unchecked
Name: "skilldeepseek"; Description: "安装 DeepSeek Harness Skill"; GroupDescription: "Agent Skill："; Flags: unchecked
Name: "skillclaude"; Description: "安装 Claude Code Skill"; GroupDescription: "Agent Skill："; Flags: unchecked

[Files]
Source: "{#AppSource}\*"; DestDir: "{app}"; Excludes: ".music-converter-data\*,.music-converter-data,*.lnk"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\ShaoLv"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\app.ico"
Name: "{autodesktop}\ShaoLv"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\app.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\music-converter.exe"; Parameters: "skill install --target codex --scope user"; Flags: runhidden waituntilterminated; Tasks: skillcodex; StatusMsg: "正在安装 Codex Skill..."
Filename: "{app}\music-converter.exe"; Parameters: "skill install --target deepseek --scope user"; Flags: runhidden waituntilterminated; Tasks: skilldeepseek; StatusMsg: "正在安装 DeepSeek Harness Skill..."
Filename: "{app}\music-converter.exe"; Parameters: "skill install --target claude --scope user"; Flags: runhidden waituntilterminated; Tasks: skillclaude; StatusMsg: "正在安装 Claude Code Skill..."
Filename: "{app}\{#MyAppExeName}"; Description: "启动韶律"; Flags: nowait postinstall skipifsilent

