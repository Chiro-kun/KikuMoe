$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$pythonExe = if (Test-Path $venvPython) { $venvPython } else { 'python' }

Write-Host "Using Python: $pythonExe" -ForegroundColor Cyan
Write-Host "Installing build/runtime requirements..." -ForegroundColor Cyan
& $pythonExe -m pip install --upgrade pyinstaller pyinstaller-hooks-contrib
& $pythonExe -m pip install -r (Join-Path $PSScriptRoot 'requirements.txt')

# Fast sanity check to avoid generating a broken exe from a wrong interpreter.
& $pythonExe -c "import PyQt5, websocket; print('build-env-ok')"

$specPath = Join-Path $projectRoot 'packaging\windows\kikumoe.spec'

Write-Host "Running: $pythonExe -m PyInstaller --noconfirm --clean $specPath" -ForegroundColor Green
& $pythonExe -m PyInstaller --noconfirm --clean $specPath

Write-Host "Done. Output:" -ForegroundColor Cyan
Write-Host "  - OneFile: dist\\KikuMoe-1.9.0.exe"
