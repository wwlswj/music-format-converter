$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
$tempRoot = Join-Path $projectRoot ".tmp"
$baseTemp = Join-Path $tempRoot "pytest-run"

New-Item -ItemType Directory -Force -Path $tempRoot | Out-Null
$env:TEMP = $tempRoot
$env:TMP = $tempRoot
$env:QT_QPA_PLATFORM = "offscreen"

Push-Location $projectRoot
try {
    & $python -m pytest --basetemp $baseTemp
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
    & (Join-Path $projectRoot ".venv\Scripts\ruff.exe") check src tests app.py launcher.py scripts packaging
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}
finally {
    Pop-Location
}

