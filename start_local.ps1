# Restart RCAAgent-Env on a new port (project root).
# Usage:  .\start_local.ps1              # default port 5500
#         .\start_local.ps1 -Port 9001   # custom port
# Stop first: closes anything LISTENING on that port, then starts run_dev.py

param(
    [int]$Port = 5500
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$lines = netstat -ano | Select-String -Pattern ":$Port\s+.*LISTENING"
foreach ($line in $lines) {
    if ($line -match "\s+(\d+)\s*$") {
        $procId = [int]$Matches[1]
        Write-Host "Stopping PID $procId on port $Port"
        taskkill /PID $procId /F 2>$null
    }
}

Write-Host "Starting on http://127.0.0.1:$Port/docs"
py -3.11 run_dev.py --host 127.0.0.1 --port $Port
