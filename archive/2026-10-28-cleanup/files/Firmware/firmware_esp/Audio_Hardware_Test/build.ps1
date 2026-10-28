# One-click build script for Audio Hardware Test
param(
    [switch]$Clean
)

Write-Host ">>> Activating ESP-IDF Environment..." -ForegroundColor Cyan
& 'C:\Espressif\tools\Microsoft.v6.0.2.PowerShell_profile.ps1'

if ($Clean) {
    Write-Host ">>> Cleaning build directory..." -ForegroundColor Yellow
    idf.py fullclean
}

Write-Host ">>> Building Audio Hardware Test..." -ForegroundColor Green
idf.py build
