$ErrorActionPreference = "Stop"

$projectRoot = $PSScriptRoot
$windowsPackaging = Join-Path $projectRoot 'packaging\windows'

if (-not (Test-Path -LiteralPath $windowsPackaging -PathType Container)) {
    throw "Windows build prerequisites are missing: $windowsPackaging"
}

$requiredWindowsFiles = @(
    'KikuMoe.ico',
    'KikuMoe.manifest',
    'version_info.txt',
    'libmpv-2.dll'
) | ForEach-Object { Join-Path $windowsPackaging $_ }
$missingWindowsFiles = @(
    $requiredWindowsFiles | Where-Object { -not (Test-Path -LiteralPath $_ -PathType Leaf) }
)
if ($missingWindowsFiles.Count -gt 0) {
    $missingList = $missingWindowsFiles -join "`n  - "
    throw "Windows build prerequisites are missing:`n  - $missingList`nAdd the required assets to packaging/windows and retry."
}

Write-Host "Installing dependencies via Poetry..." -ForegroundColor Cyan
Set-Location $projectRoot
poetry install --with dev

$specPath = Join-Path $projectRoot 'kikumoe.spec'

Write-Host "Running: poetry run python -m PyInstaller --noconfirm --clean $specPath" -ForegroundColor Green
poetry run python -m PyInstaller --noconfirm --clean $specPath

Write-Host "Done. Output:" -ForegroundColor Cyan
Write-Host "  dist\KikuMoe-1.10.0.exe"
