$ErrorActionPreference = 'Stop'
$phoneStatePath = Join-Path $PSScriptRoot 'output\phone-server.json'
if (!(Test-Path -LiteralPath $phoneStatePath)) { Write-Host 'Phone access is not running.'; exit }
$phoneState = Get-Content -LiteralPath $phoneStatePath -Raw | ConvertFrom-Json
$phoneProcess = Get-CimInstance Win32_Process -Filter "ProcessId = $([int]$phoneState.pid)"
$phoneExpected = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '.venv\Scripts\python.exe')).Path
$phoneExpected = (& $phoneExpected -c 'import sys; print(sys._base_executable)').Trim()
if ($phoneProcess -and $phoneProcess.ExecutablePath -eq $phoneExpected -and $phoneProcess.CommandLine -match 'phone_server\.py') {
    & taskkill.exe /PID ([string][int]$phoneState.pid) /T /F
} else { Write-Host 'The saved phone server is no longer running.' }
