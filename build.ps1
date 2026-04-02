$ErrorActionPreference = "Stop"

$projectRoot = $PSScriptRoot

Write-Host "Installing dependencies via Poetry..." -ForegroundColor Cyan
Set-Location $projectRoot
poetry install --with dev

$specPath = Join-Path $projectRoot 'kikumoe.spec'

Write-Host "Running: poetry run python -m PyInstaller --noconfirm --clean $specPath" -ForegroundColor Green
poetry run python -m PyInstaller --noconfirm --clean $specPath

Write-Host "Done. Output:" -ForegroundColor Cyan
Write-Host "  dist\KikuMoe-1.9.0.exe"
