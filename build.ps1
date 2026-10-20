$ErrorActionPreference = "Stop"

$projectRoot = $PSScriptRoot
$windowsPackaging = Join-Path $projectRoot 'packaging\windows'

if (-not (Test-Path -LiteralPath $windowsPackaging -PathType Container)) {
    throw "Windows build prerequisites are missing: $windowsPackaging"
}

# Download automatico di libmpv-2.dll se assente
$libmpvFile = Join-Path $windowsPackaging 'libmpv-2.dll'
if (-not (Test-Path -LiteralPath $libmpvFile -PathType Leaf)) {
    Write-Host "libmpv-2.dll non trovata in $windowsPackaging." -ForegroundColor Yellow
    Write-Host "Download automatico del pacchetto mpv-dev in corso..." -ForegroundColor Cyan
    $mpvUrl = "https://github.com/shinchiro/mpv-winbuild-cmake/releases/download/20261020/mpv-dev-x86_64-20261020-git-6a262d11f6.7z"
    $tempArchive = Join-Path ([System.IO.Path]::GetTempPath()) "mpv-dev-$([System.Guid]::NewGuid().ToString('N')).7z"
    try {
        Invoke-WebRequest -Uri $mpvUrl -OutFile $tempArchive
        if (Get-Command 7z -ErrorAction SilentlyContinue) {
            & 7z e $tempArchive "-o$windowsPackaging" libmpv-2.dll -r -y | Out-Null
        } elseif (Get-Command tar -ErrorAction SilentlyContinue) {
            & tar -xf $tempArchive -C $windowsPackaging --wildcards "*libmpv-2.dll" | Out-Null
        } else {
            Write-Warning "Né '7z' né 'tar' sono disponibili nel PATH per estrarre l'archivio .7z."
        }
        if (Test-Path -LiteralPath $libmpvFile -PathType Leaf) {
            Write-Host "libmpv-2.dll scaricata ed estratta con successo!" -ForegroundColor Green
        }
    } catch {
        Write-Warning "Download automatico fallito: $_"
    } finally {
        if (Test-Path -LiteralPath $tempArchive) { Remove-Item $tempArchive -Force -ErrorAction SilentlyContinue }
    }
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

$appVersion = "1.10.0"
$versionYml = Join-Path $projectRoot "version.yml"
if (Test-Path $versionYml) {
    $vMatch = Select-String -Path $versionYml -Pattern 'version:\s*(.+)'
    if ($vMatch) { $appVersion = $vMatch.Matches[0].Groups[1].Value.Trim() }
}

Write-Host "Done. Output:" -ForegroundColor Cyan
Write-Host "  dist\KikuMoe-$appVersion.exe"
