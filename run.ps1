param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$PassThruArgs
)

$projectRoot = $PSScriptRoot
$mainScript = Join-Path $projectRoot 'KikuMoe.py'

if (-not (Test-Path -LiteralPath $mainScript -PathType Leaf)) {
    Write-Error "Main script non trovato: $mainScript"
    exit 1
}

$venvPython = Join-Path $projectRoot '.venv\Scripts\python.exe'

if (Test-Path -LiteralPath $venvPython -PathType Leaf) {
    Write-Host "Avvio di KikuMoe tramite virtual environment (.venv)..." -ForegroundColor Cyan
    & "$venvPython" "$mainScript" @PassThruArgs
    exit $LASTEXITCODE
}

$poetryCmd = Get-Command poetry -ErrorAction SilentlyContinue
if ($null -ne $poetryCmd) {
    Write-Host "Avvio di KikuMoe tramite Poetry..." -ForegroundColor Cyan
    poetry run python "$mainScript" @PassThruArgs
    exit $LASTEXITCODE
}

$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if ($null -ne $pythonCmd) {
    Write-Warning "Nessun ambiente .venv trovato e Poetry non presente nel PATH. Avvio con Python di sistema (i backend audio potrebbero mancare)."
    python "$mainScript" @PassThruArgs
    exit $LASTEXITCODE
}

Write-Error "Impossibile trovare un interprete Python valido ne' l'ambiente .venv in $projectRoot."
exit 1
