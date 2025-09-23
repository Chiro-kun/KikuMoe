$ErrorActionPreference = "Stop"
Write-Host "Setting up PyInstaller..." -ForegroundColor Cyan
python -m pip install --upgrade pyinstaller pyinstaller-hooks-contrib

$specPath = Join-Path $PSScriptRoot 'kikumoe.spec'

Write-Host "Running: pyinstaller --noconfirm --clean $specPath" -ForegroundColor Green
pyinstaller --noconfirm --clean $specPath

Write-Host "Done. Output:" -ForegroundColor Cyan
Write-Host "  - OneFile: dist\\KikuMoe-1.8.exe"