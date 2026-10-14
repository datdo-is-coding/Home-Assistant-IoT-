param(
    [Parameter(Mandatory = $true)][string]$Port,
    [switch]$NoMonitor
)
$ErrorActionPreference = 'Stop'
if (-not (Get-Command idf.py -ErrorAction SilentlyContinue)) {
    throw 'Activate the ESP-IDF 6.0.2 environment before running this script.'
}
if ($NoMonitor) {
    idf.py -C $PSScriptRoot -p $Port flash
} else {
    idf.py -C $PSScriptRoot -p $Port flash monitor
}
exit $LASTEXITCODE
