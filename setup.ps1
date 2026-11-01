$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = "python"
$venv = Join-Path $projectRoot ".venv"
$venvPython = Join-Path $venv "Scripts\python.exe"
$tempRoot = Join-Path $projectRoot ".tmp"

New-Item -ItemType Directory -Force -Path $tempRoot | Out-Null
$env:TEMP = $tempRoot
$env:TMP = $tempRoot

if (-not (Test-Path -LiteralPath $venvPython)) {
    Write-Host "创建 Python 虚拟环境…"
    & $python -m venv $venv
}

Write-Host "安装或修复 Python 依赖…"
& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -e "$projectRoot[dev]"
& $venvPython -m pip check

& (Join-Path $projectRoot "scripts\install_media_tools.ps1")

$required = @(
    "tools\ffmpeg\bin\ffmpeg.exe",
    "tools\ffmpeg\bin\ffprobe.exe",
    "tools\monkeys-audio\MAC.exe"
)
foreach ($relative in $required) {
    $absolute = Join-Path $projectRoot $relative
    if (-not (Test-Path -LiteralPath $absolute)) {
        throw "缺少项目内工具：$relative"
    }
}

& (Join-Path $projectRoot "scripts\create_shortcuts.ps1")

Write-Host "检查媒体工具和编码器…"
Push-Location $projectRoot
try {
    & $venvPython -m music_converter doctor
}
finally {
    Pop-Location
}

Write-Host "安装完成。运行 .\run.ps1 启动界面。"

