@echo off
:: Verifica se lo script è eseguito come amministratore
net session >nul 2>&1
if %errorLevel% == 0 (
    echo Amministratore confermato.
) else (
    echo Richiesti privilegi di amministratore. Riavvio come amministratore...
    powershell -Command "Start-Process -FilePath '%~f0' -ArgumentList 'elevated' -Verb RunAs"
    exit /b
)

:: Ottieni la directory corrente
set "currentDir=%~dp0"
set "currentDir=%currentDir:~0,-1%"

:: Installa FFmpeg tramite winget (spesso gestisce già la PATH in automatico)
echo Installazione di FFmpeg in corso...
winget install -e --id Gyan.FFmpeg --accept-source-agreements --accept-package-agreements
echo.
echo ==========================================================
echo INSTALLAZIONE COMPLETATA!
echo Se ffmpeg non viene ancora rilevato da KikuMoe,
echo e' necessario RIAVVIARE WINDOWS per far ricaricare la
echo nuova variabile di ambiente PATH al sistema.
echo ==========================================================
echo.
pause