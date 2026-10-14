param([switch]$Clean)
$ErrorActionPreference = 'Stop'
if (-not (Get-Command idf.py -ErrorAction SilentlyContinue)) {
    throw 'Activate the ESP-IDF 6.0.2 environment before running this script.'
}
if ($Clean) {
    idf.py -C $PSScriptRoot fullclean
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
idf.py -C $PSScriptRoot build
exit $LASTEXITCODE
