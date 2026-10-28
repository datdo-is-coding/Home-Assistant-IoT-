# One-click flash script for ActionBox
param(
    [string]$Port = "COM9",
    [switch]$NoMonitor
)
$ErrorActionPreference = 'Stop'

Write-Host ">>> Activating ESP-IDF Environment..." -ForegroundColor Cyan
. 'C:\Espressif\tools\Microsoft.v6.0.2.PowerShell_profile.ps1'

if ($NoMonitor) {
    Write-Host ">>> Flashing ActionBox on $Port..." -ForegroundColor Green
    idf.py -C $PSScriptRoot -p $Port flash
}
else {
    Write-Host ">>> Flashing and Monitoring ActionBox on $Port..." -ForegroundColor Green
    idf.py -C $PSScriptRoot -p $Port flash monitor
}
exit $LASTEXITCODE
