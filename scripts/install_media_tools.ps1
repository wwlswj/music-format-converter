$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$toolRoot = Join-Path $projectRoot "tools\ffmpeg"
$binRoot = Join-Path $toolRoot "bin"
$ffmpeg = Join-Path $binRoot "ffmpeg.exe"
$ffprobe = Join-Path $binRoot "ffprobe.exe"

if ((Test-Path -LiteralPath $ffmpeg) -and (Test-Path -LiteralPath $ffprobe)) {
    Write-Host "FFmpeg tools are already installed."
    exit 0
}

$version = "9.0.2"
$archiveUrl = "https://github.com/GyanD/codexffmpeg/releases/download/$version/ffmpeg-$version-essentials_build.7z"
$expectedArchiveHash = "4705843ccaaf54257c16ad90f3e952ece33c17df964ecf7bfdbb0f49c7171077"
$expectedFfmpegHash = "3256173F3F8BFFD7DF12227C68ADF68025EDB1832273A9530688A7BB1ED8EDEC"
$expectedFfprobeHash = "F0D36ECBBDD3BCFAC3EFA078C96C7271C2E68B3810595552AC3B7F17E9A65C52"

$tempRoot = Join-Path $projectRoot ".tmp\media-tools"
$archive = Join-Path $tempRoot "ffmpeg-$version.7z"
$extractRoot = Join-Path $tempRoot "ffmpeg-extracted"
New-Item -ItemType Directory -Force -Path $tempRoot, $binRoot | Out-Null

$resolvedProject = (Resolve-Path -LiteralPath $projectRoot).Path
$resolvedTemp = [System.IO.Path]::GetFullPath($tempRoot)
if (-not $resolvedTemp.StartsWith($resolvedProject + [System.IO.Path]::DirectorySeparatorChar)) {
    throw "Refusing to clean a temporary directory outside the project."
}

$archiveReady = $false
if (Test-Path -LiteralPath $archive) {
    $existingHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $archive).Hash.ToLowerInvariant()
    $archiveReady = $existingHash -eq $expectedArchiveHash
    if (-not $archiveReady) {
        Remove-Item -LiteralPath $archive -Force
    }
}
if (-not $archiveReady) {
    Write-Host "Downloading FFmpeg $version..."
    & curl.exe --fail --location --retry 3 --retry-delay 2 --silent --show-error `
        --output $archive $archiveUrl
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to download FFmpeg archive."
    }
}
$actualArchiveHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $archive).Hash.ToLowerInvariant()
if ($actualArchiveHash -ne $expectedArchiveHash) {
    throw "FFmpeg archive checksum mismatch."
}

if (Test-Path -LiteralPath $extractRoot) {
    Remove-Item -LiteralPath $extractRoot -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $extractRoot | Out-Null
Push-Location $extractRoot
try {
    & tar.exe -xf "..\ffmpeg-$version.7z"
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to extract the FFmpeg archive."
    }
}
finally {
    Pop-Location
}
$sourceFfmpeg = Get-ChildItem -LiteralPath $extractRoot -Recurse -Filter "ffmpeg.exe" |
    Where-Object { $_.DirectoryName -like "*\bin" } |
    Select-Object -First 1
$sourceFfprobe = Get-ChildItem -LiteralPath $extractRoot -Recurse -Filter "ffprobe.exe" |
    Where-Object { $_.DirectoryName -like "*\bin" } |
    Select-Object -First 1
if (-not $sourceFfmpeg -or -not $sourceFfprobe) {
    throw "The downloaded FFmpeg archive does not contain both required executables."
}

Copy-Item -LiteralPath $sourceFfmpeg.FullName -Destination $ffmpeg -Force
Copy-Item -LiteralPath $sourceFfprobe.FullName -Destination $ffprobe -Force
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $ffmpeg).Hash -ne $expectedFfmpegHash) {
    throw "ffmpeg.exe checksum mismatch."
}
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $ffprobe).Hash -ne $expectedFfprobeHash) {
    throw "ffprobe.exe checksum mismatch."
}

Write-Host "FFmpeg $version installed and verified."

