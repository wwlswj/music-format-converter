$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$pythonw = Join-Path $projectRoot ".venv\Scripts\pythonw.exe"
$launcher = Join-Path $projectRoot "launcher.py"

if (-not (Test-Path -LiteralPath $pythonw)) {
    throw "Missing virtual environment: $pythonw"
}
if (-not (Test-Path -LiteralPath $launcher)) {
    throw "Missing launcher: $launcher"
}

$shell = New-Object -ComObject WScript.Shell
foreach ($name in @("启动韶律.lnk")) {
    $shortcutPath = Join-Path $projectRoot $name
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = $pythonw
    $shortcut.Arguments = '"' + $launcher + '"'
    $shortcut.WorkingDirectory = $projectRoot
    $shortcut.IconLocation = "$pythonw,0"
    $shortcut.Description = "韶律音乐格式转换器"
    $shortcut.Save()
}

Write-Host "Created launch shortcuts in $projectRoot"

