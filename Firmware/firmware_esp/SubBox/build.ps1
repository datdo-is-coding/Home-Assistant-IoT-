# One-click build script for SubBox using native ESP-IDF
param(
    [switch]$Clean
)
$ErrorActionPreference = 'Stop'

Write-Host ">>> Activating ESP-IDF Environment..." -ForegroundColor Cyan
. 'C:\Espressif\tools\Microsoft.v6.0.2.PowerShell_profile.ps1'

if ($Clean) {
    Write-Host ">>> Cleaning build directory..." -ForegroundColor Yellow
    idf.py -C $PSScriptRoot fullclean
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

Write-Host ">>> Building SubBox..." -ForegroundColor Green
idf.py -C $PSScriptRoot build
exit $LASTEXITCODE
