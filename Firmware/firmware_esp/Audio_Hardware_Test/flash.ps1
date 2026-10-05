# One-click flash script for Audio Hardware Test
param(
    [string]$Port = "COM8",
    [switch]$NoMonitor
)

Write-Host ">>> Activating ESP-IDF Environment..." -ForegroundColor Cyan
& 'C:\Espressif\tools\Microsoft.v6.0.2.PowerShell_profile.ps1'

if ($NoMonitor) {
    Write-Host ">>> Flashing Audio Hardware Test on $Port..." -ForegroundColor Green
    idf.py -p $Port flash
} else {
    Write-Host ">>> Flashing and Monitoring Audio Hardware Test on $Port..." -ForegroundColor Green
    idf.py -p $Port flash monitor
}
