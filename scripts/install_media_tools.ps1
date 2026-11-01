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
$archiveUrl = "https://www.gyan.dev/ffmpeg/builds/packages/ffmpeg-$version-essentials_build.zip"
$expectedArchiveHash = "60f467265b1e312373dbcd92200c2618a74850f98d3d078e94296bb3fa2047ba"
$expectedFfmpegHash = "3256173F3F8BFFD7DF12227C68ADF68025EDB1832273A9530688A7BB1ED8EDEC"
$expectedFfprobeHash = "F0D36ECBBDD3BCFAC3EFA078C96C7271C2E68B3810595552AC3B7F17E9A65C52"

$tempRoot = Join-Path $projectRoot ".tmp\media-tools"
$archive = Join-Path $tempRoot "ffmpeg-$version.zip"
$extractRoot = Join-Path $tempRoot "ffmpeg-extracted"
New-Item -ItemType Directory -Force -Path $tempRoot, $binRoot | Out-Null

$resolvedProject = (Resolve-Path -LiteralPath $projectRoot).Path
$resolvedTemp = [System.IO.Path]::GetFullPath($tempRoot)
if (-not $resolvedTemp.StartsWith($resolvedProject + [System.IO.Path]::DirectorySeparatorChar)) {
    throw "Refusing to clean a temporary directory outside the project."
}

Write-Host "Downloading FFmpeg $version..."
Invoke-WebRequest -Uri $archiveUrl -OutFile $archive
$actualArchiveHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $archive).Hash.ToLowerInvariant()
if ($actualArchiveHash -ne $expectedArchiveHash) {
    throw "FFmpeg archive checksum mismatch."
}

if (Test-Path -LiteralPath $extractRoot) {
    Remove-Item -LiteralPath $extractRoot -Recurse -Force
}
Expand-Archive -LiteralPath $archive -DestinationPath $extractRoot -Force
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

