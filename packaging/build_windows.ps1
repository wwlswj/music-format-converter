param(
    [string]$Version = "0.2.0"
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
$python = if (Test-Path -LiteralPath $venvPython) {
    $venvPython
} else {
    (Get-Command python -ErrorAction Stop).Source
}
$buildRoot = Join-Path $projectRoot "build\windows"
$distRoot = Join-Path $projectRoot "dist\windows"
$artifactRoot = Join-Path $projectRoot "artifacts"
$guiDist = Join-Path $distRoot "gui"
$cliDist = Join-Path $distRoot "cli"
$guiApp = Join-Path $guiDist "ShaoLvMusicConverter"
$appSource = Join-Path $buildRoot "app"

if (-not (Test-Path -LiteralPath $python)) {
    throw "Missing virtual environment: $python"
}

$resolvedProject = (Resolve-Path -LiteralPath $projectRoot).Path
foreach ($target in @($buildRoot, $distRoot)) {
    $fullTarget = [System.IO.Path]::GetFullPath($target)
    if (-not $fullTarget.StartsWith($resolvedProject + [System.IO.Path]::DirectorySeparatorChar)) {
        throw "Refusing to clean path outside project: $fullTarget"
    }
    if (Test-Path -LiteralPath $fullTarget) {
        Remove-Item -LiteralPath $fullTarget -Recurse -Force
    }
}
New-Item -ItemType Directory -Force -Path $buildRoot, $guiDist, $cliDist, $artifactRoot | Out-Null

& $python (Join-Path $projectRoot "packaging\make_icon.py")
& (Join-Path $projectRoot "scripts\install_media_tools.ps1")

$common = @(
    "--noconfirm",
    "--clean",
    "--paths", (Join-Path $projectRoot "src"),
    "--add-data", "$((Join-Path $projectRoot 'assets'));assets",
    "--add-data", "$((Join-Path $projectRoot 'skills'));skills",
    "--add-data", "$((Join-Path $projectRoot 'licenses'));licenses",
    "--add-data", "$((Join-Path $projectRoot 'README.md'));.",
    "--add-data", "$((Join-Path $projectRoot 'LICENSE'));.",
    "--add-data", "$((Join-Path $projectRoot 'THIRD_PARTY_NOTICES.md'));.",
    "--hidden-import", "mutagen.monkeysaudio",
    "--workpath", $buildRoot,
    "--specpath", $buildRoot
)

& $python -m PyInstaller @common --windowed --onedir --name "ShaoLvMusicConverter" `
    --icon (Join-Path $projectRoot "assets\icon.ico") `
    --distpath $guiDist (Join-Path $projectRoot "packaging\entry_gui.py")

& $python -m PyInstaller @common --console --onedir --name "music-converter" `
    --contents-directory "music-converter-internal" `
    --icon (Join-Path $projectRoot "assets\icon.ico") `
    --distpath $cliDist (Join-Path $projectRoot "packaging\entry_cli.py")

New-Item -ItemType Directory -Force -Path $appSource | Out-Null
Copy-Item -Path (Join-Path $guiApp "*") -Destination $appSource -Recurse -Force
Copy-Item -Path (Join-Path $cliDist "music-converter\*") -Destination $appSource -Recurse -Force
Copy-Item -LiteralPath (Join-Path $projectRoot "tools") -Destination (Join-Path $appSource "tools") -Recurse -Force
Copy-Item -LiteralPath (Join-Path $projectRoot "assets\icon.ico") -Destination (Join-Path $appSource "app.ico") -Force
Copy-Item -LiteralPath (Join-Path $projectRoot "README.md") -Destination $appSource -Force
Copy-Item -LiteralPath (Join-Path $projectRoot "LICENSE") -Destination $appSource -Force
Copy-Item -LiteralPath (Join-Path $projectRoot "THIRD_PARTY_NOTICES.md") -Destination $appSource -Force
Copy-Item -LiteralPath (Join-Path $projectRoot "licenses") -Destination (Join-Path $appSource "licenses") -Recurse -Force
Copy-Item -LiteralPath (Join-Path $projectRoot "packaging\skill-installers") -Destination (Join-Path $appSource "skill-installers") -Recurse -Force

$isccCandidates = @(
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
    "$env:USERPROFILE\AppData\Local\Programs\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
)
$commandIscc = Get-Command ISCC.exe -ErrorAction SilentlyContinue
if ($commandIscc) {
    $isccCandidates = @($commandIscc.Source) + $isccCandidates
}
$iscc = $isccCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $iscc) {
    throw "Inno Setup 6 was not found."
}

& $iscc "/DMyAppVersion=$Version" "/DAppSource=$appSource" "/DRepoRoot=$projectRoot" `
    "/DOutputDir=$artifactRoot" (Join-Path $projectRoot "packaging\windows\installer.iss")

Get-ChildItem -LiteralPath $artifactRoot -Filter "ShaoLv-Music-Converter-Setup-*.exe" |
    Select-Object FullName,Length

