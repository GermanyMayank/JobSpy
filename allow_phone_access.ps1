$ErrorActionPreference = 'Stop'
$phoneStatePath = Join-Path $PSScriptRoot 'output\phone-server.json'
if (!(Test-Path -LiteralPath $phoneStatePath)) { throw 'Start Phone Access first, then run this helper.' }
$phoneState = Get-Content -LiteralPath $phoneStatePath -Raw | ConvertFrom-Json
$phoneAddress = [System.Net.IPAddress]::Parse($phoneState.host)
if ($phoneAddress.AddressFamily -ne [System.Net.Sockets.AddressFamily]::InterNetwork -or [int]$phoneState.port -ne 8765) { throw 'Unexpected phone server address or port.' }
$phoneInterface = Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -eq $phoneState.host } | Select-Object -First 1
if (!$phoneInterface) { throw 'The saved address is no longer assigned to this PC. Restart Phone Access.' }
$phonePython = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '.venv\Scripts\python.exe')).Path
$phoneRuntime = (& $phonePython -c 'import sys; print(sys._base_executable)').Trim()
if (!(Test-Path -LiteralPath $phoneRuntime)) { throw 'Cannot identify the running Python executable.' }
$phoneRule = 'JobSpy phone access - local subnet only'
Get-NetFirewallRule -DisplayName $phoneRule -ErrorAction SilentlyContinue | Remove-NetFirewallRule
New-NetFirewallRule -DisplayName $phoneRule -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8765 -LocalAddress $phoneState.host -RemoteAddress LocalSubnet -InterfaceAlias $phoneInterface.InterfaceAlias -Program $phoneRuntime -Profile Any | Out-Null
Write-Host 'JobSpy phone access enabled only on the local subnet, current interface and port 8765.'
