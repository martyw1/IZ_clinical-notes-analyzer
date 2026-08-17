[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$RepositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$PythonExe = Join-Path $RepositoryRoot 'backend\.venv\Scripts\python.exe'
$StopLauncher = Join-Path $RepositoryRoot 'scripts\Stop-IZ-Clinical-Notes-Analyzer.cmd'
$TempRoot = Join-Path ([IO.Path]::GetTempPath()) "iz-cna-stop-$([Guid]::NewGuid().ToString('N'))"
$ListenerScript = Join-Path $TempRoot 'synthetic_listener.py'
$AppProcess = $null
$UnrelatedProcess = $null
$PreviousLocalAppData = $env:LOCALAPPDATA

function Assert-True {
    param([bool]$Condition, [string]$Label)
    if (-not $Condition) { throw "Assertion failed: $Label" }
    Write-Host "[pass] $Label"
}

function Get-FreeLocalPort {
    $listener = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, 0)
    try {
        $listener.Start()
        return [int]$listener.LocalEndpoint.Port
    }
    finally {
        $listener.Stop()
    }
}

function Wait-ForPortState {
    param([int]$Port, [bool]$Listening)

    $deadline = [DateTime]::UtcNow.AddSeconds(15)
    do {
        $found = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue).Count -gt 0
        if ($found -eq $Listening) { return $true }
        Start-Sleep -Milliseconds 250
    } while ([DateTime]::UtcNow -lt $deadline)
    return $false
}

function Start-SyntheticListener {
    param([int]$Port, [switch]$AppCommandShape)

    $arguments = @($ListenerScript, '127.0.0.1', [string]$Port)
    if ($AppCommandShape) {
        $arguments += @(
            '-m', 'uvicorn', 'app.desktop_main:app',
            '--host', '127.0.0.1', '--port', [string]$Port, '--no-access-log'
        )
    }
    return Start-Process -FilePath $PythonExe -ArgumentList $arguments `
        -WorkingDirectory (Join-Path $RepositoryRoot 'backend') -WindowStyle Hidden -PassThru
}

try {
    Assert-True -Condition (Test-Path -LiteralPath $PythonExe) -Label 'backend_python_exists'
    Assert-True -Condition (Test-Path -LiteralPath $StopLauncher) -Label 'stop_cmd_exists'
    New-Item -ItemType Directory -Path $TempRoot -Force | Out-Null
    $env:LOCALAPPDATA = Join-Path $TempRoot 'LocalAppData'
    $appDataRoot = Join-Path $env:LOCALAPPDATA 'IZ Clinical Notes Analyzer'
    New-Item -ItemType Directory -Path $appDataRoot -Force | Out-Null
    @'
import socket
import sys
import time

host = sys.argv[1]
port = int(sys.argv[2])
with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind((host, port))
    listener.listen()
    time.sleep(300)
'@ | Set-Content -LiteralPath $ListenerScript -Encoding UTF8

    $appPort = Get-FreeLocalPort
    Set-Content -LiteralPath (Join-Path $appDataRoot '.env') -Value "BACKEND_PORT=$appPort" -Encoding UTF8
    $AppProcess = Start-SyntheticListener -Port $appPort -AppCommandShape
    Assert-True -Condition (Wait-ForPortState -Port $appPort -Listening $true) -Label 'legacy_app_command_shape_listens'

    & $StopLauncher -NoRestartPrompt -NoPause
    Assert-True -Condition ($LASTEXITCODE -eq 0) -Label 'stop_cmd_returns_success'
    Assert-True -Condition (Wait-ForPortState -Port $appPort -Listening $false) -Label 'stop_cmd_releases_app_port'
    $AppProcess.Refresh()
    Assert-True -Condition $AppProcess.HasExited -Label 'stop_cmd_terminates_app_process'

    Start-Sleep -Seconds 2
    Assert-True -Condition (Wait-ForPortState -Port $appPort -Listening $false) -Label 'app_port_stays_free_after_cleanup'

    & $StopLauncher -NoRestartPrompt -NoPause
    Assert-True -Condition ($LASTEXITCODE -eq 0) -Label 'second_stop_is_idempotent'

    $unrelatedPort = Get-FreeLocalPort
    $UnrelatedProcess = Start-SyntheticListener -Port $unrelatedPort
    Assert-True -Condition (Wait-ForPortState -Port $unrelatedPort -Listening $true) -Label 'unrelated_python_listener_starts'
    & $StopLauncher -NoRestartPrompt -NoPause
    Assert-True -Condition ($LASTEXITCODE -eq 0) -Label 'stop_cmd_ignores_unrelated_listener'
    $UnrelatedProcess.Refresh()
    Assert-True -Condition (-not $UnrelatedProcess.HasExited) -Label 'unrelated_python_process_survives'
    Assert-True -Condition (Wait-ForPortState -Port $unrelatedPort -Listening $true) -Label 'unrelated_port_remains_listening'
}
finally {
    foreach ($process in @($AppProcess, $UnrelatedProcess)) {
        if ($process) {
            $process.Refresh()
            if (-not $process.HasExited) { Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue }
        }
    }
    $env:LOCALAPPDATA = $PreviousLocalAppData
    if (Test-Path -LiteralPath $TempRoot) { Remove-Item -LiteralPath $TempRoot -Recurse -Force }
}
