[CmdletBinding()]
param(
    [switch]$Restart,
    [switch]$NoRestartPrompt,
    [switch]$NoPause,
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
$ExitCode = 0
$RestartLaunched = $false

$RootDir = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$ScriptsDir = Join-Path $RootDir 'scripts'
$BackendDir = Join-Path $RootDir 'backend'
$FrontendDir = Join-Path $RootDir 'frontend'
$StartCmd = Join-Path $ScriptsDir 'Start-IZ-Clinical-Notes-Analyzer.cmd'
$AppDataRoot = Join-Path $env:LOCALAPPDATA 'IZ Clinical Notes Analyzer'

function Write-Info($Message) { Write-Host "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] [INFO] $Message" }
function Write-Pass($Message) { Write-Host "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] [PASS] $Message" -ForegroundColor Green }
function Write-Warn($Message) { Write-Host "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] [WARN] $Message" -ForegroundColor Yellow }
function Write-Fail($Message) { Write-Host "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] [FAIL] $Message" -ForegroundColor Red }

function ConvertTo-NormalizedText {
    param([AllowNull()][string]$Value)
    if ($null -eq $Value) { return '' }
    return $Value.ToLowerInvariant().Replace('/', '\')
}

function ConvertTo-NormalizedCommandText {
    param([AllowNull()][string]$Value)
    $text = ConvertTo-NormalizedText $Value
    $normalizedRoot = ConvertTo-NormalizedText $RootDir
    $text = $text.Replace("$normalizedRoot\.\", "$normalizedRoot\")
    $text = $text.Replace("$normalizedRoot\scripts\..\scripts", "$normalizedRoot\scripts")
    $text = $text.Replace("$normalizedRoot\backend\..\backend", "$normalizedRoot\backend")
    $text = $text.Replace("$normalizedRoot\frontend\..\frontend", "$normalizedRoot\frontend")
    return $text
}

function Test-CommandLineContainsPath {
    param([string]$CommandLine, [string]$Path)
    $needle = ConvertTo-NormalizedText $Path
    return $CommandLine.Contains($needle)
}

function Get-ConfiguredBackendPorts {
    $ports = New-Object System.Collections.Generic.List[int]
    $ports.Add(8000)
    $ports.Add(8020)

    $envFiles = @(
        (Join-Path $AppDataRoot '.env'),
        (Join-Path $RootDir '.env'),
        (Join-Path $RootDir 'backend\.env')
    ) | Select-Object -Unique

    foreach ($envFile in $envFiles) {
        if (!(Test-Path $envFile)) { continue }
        $line = Get-Content -Path $envFile -ErrorAction SilentlyContinue |
            Where-Object { $_ -match '^\s*BACKEND_PORT\s*=' } |
            Select-Object -First 1
        if (!$line) { continue }

        $text = ($line -replace '^\s*BACKEND_PORT\s*=', '').Trim().Trim('"').Trim("'")
        $port = 0
        if ([int]::TryParse($text, [ref]$port) -and $port -gt 0 -and $port -le 65535) {
            if (!$ports.Contains($port)) { $ports.Add($port) }
        }
    }

    return $ports.ToArray() | Sort-Object -Unique
}

function Get-LocalPortOwnerReasons {
    param([int[]]$Ports)

    $owners = @{}
    try {
        $connections = Get-NetTCPConnection -State Listen -ErrorAction Stop |
            Where-Object {
                ($Ports -contains [int]$_.LocalPort) -and
                ($_.LocalAddress -in @('127.0.0.1', '::1', '0.0.0.0', '::'))
            }

        foreach ($connection in $connections) {
            $pidText = [string]$connection.OwningProcess
            $reason = "listening on local port $($connection.LocalPort)"
            if ($owners.ContainsKey($pidText)) {
                if ($owners[$pidText] -notcontains $reason) { $owners[$pidText] += $reason }
            }
            else {
                $owners[$pidText] = @($reason)
            }
        }
    }
    catch {
        Write-Warn "Could not inspect listening localhost ports: $($_.Exception.Message)"
    }

    return $owners
}

function Test-IsLauncherCmd {
    param([string]$Name, [string]$CommandLine)
    return (
        $Name -eq 'cmd.exe' -and
        (Test-CommandLineContainsPath -CommandLine $CommandLine -Path $StartCmd)
    )
}

function Test-IsStartupPowerShell {
    param([string]$Name, [string]$CommandLine)
    if ($Name -notin @('powershell.exe', 'pwsh.exe')) { return $false }
    if ($CommandLine -notmatch '(^|\s)-file(\s|$)') { return $false }
    $startWrapper = Join-Path $ScriptsDir 'start-windows-local.ps1'
    $startupScript = Join-Path $ScriptsDir 'startup-windows-local.ps1'
    return (
        (Test-CommandLineContainsPath -CommandLine $CommandLine -Path $startWrapper) -or
        (Test-CommandLineContainsPath -CommandLine $CommandLine -Path $startupScript)
    )
}

function Test-IsAppUvicorn {
    param([string]$Name, [string]$CommandLine, [string]$ExecutablePath)

    $hasRepoBackend = Test-CommandLineContainsPath -CommandLine $CommandLine -Path $BackendDir
    $hasUvicorn = $CommandLine.Contains('-m uvicorn')
    $hasAppTarget = (
        $CommandLine.Contains('app.desktop_main:app') -or
        $CommandLine.Contains('app.main:app')
    )
    $hasAppDir = $CommandLine.Contains('--app-dir')
    $isPythonLike = ($Name -in @('python.exe', 'pythonw.exe')) -or $ExecutablePath.Contains('\python')

    return ($isPythonLike -and $hasUvicorn -and $hasAppTarget -and $hasAppDir -and $hasRepoBackend)
}

function Test-IsFrontendVite {
    param([string]$Name, [string]$CommandLine)

    if ($Name -ne 'node.exe') { return $false }
    $hasRepoFrontend = Test-CommandLineContainsPath -CommandLine $CommandLine -Path $FrontendDir
    $hasVite = (
        $CommandLine.Contains('\vite\bin\vite.js') -or
        $CommandLine.Contains(' vite ') -or
        $CommandLine.Contains('\vite.js')
    )

    return ($hasRepoFrontend -and $hasVite)
}

function Get-AppProcessTargets {
    param([int[]]$Ports)

    $portOwners = Get-LocalPortOwnerReasons -Ports $Ports
    $targets = @()
    $currentProcessId = [int]$PID

    $processes = Get-CimInstance Win32_Process -ErrorAction Stop
    foreach ($process in $processes) {
        if ([int]$process.ProcessId -eq $currentProcessId) { continue }

        $name = ConvertTo-NormalizedText $process.Name
        $commandLine = ConvertTo-NormalizedCommandText $process.CommandLine
        $executablePath = ConvertTo-NormalizedText $process.ExecutablePath
        if ([string]::IsNullOrWhiteSpace($commandLine)) { continue }

        $reasons = @()
        $priority = 50

        if (Test-IsLauncherCmd -Name $name -CommandLine $commandLine) {
            $reasons += 'launcher cmd running Start-IZ-Clinical-Notes-Analyzer.cmd'
            $priority = [Math]::Min($priority, 10)
        }

        if (Test-IsStartupPowerShell -Name $name -CommandLine $commandLine) {
            $reasons += 'startup PowerShell running start-windows-local.ps1 or startup-windows-local.ps1'
            $priority = [Math]::Min($priority, 10)
        }

        if (Test-IsAppUvicorn -Name $name -CommandLine $commandLine -ExecutablePath $executablePath) {
            if ($commandLine.Contains('app.main:app')) {
                $reasons += 'repo backend smoke-test Uvicorn server app.main:app'
            }
            else {
                $reasons += 'repo backend desktop Uvicorn server app.desktop_main:app'
            }
            $priority = [Math]::Min($priority, 20)
        }

        if (Test-IsFrontendVite -Name $name -CommandLine $commandLine) {
            $reasons += 'repo frontend Vite development or preview server'
            $priority = [Math]::Min($priority, 30)
        }

        $pidText = [string]$process.ProcessId
        if ($reasons.Count -gt 0 -and $portOwners.ContainsKey($pidText)) {
            $reasons += $portOwners[$pidText]
        }

        if ($reasons.Count -gt 0) {
            $targets += [pscustomobject]@{
                ProcessId = [int]$process.ProcessId
                Name = $process.Name
                Priority = $priority
                Reasons = ($reasons | Select-Object -Unique) -join '; '
            }
        }
    }

    return $targets | Sort-Object Priority, ProcessId
}

function Show-ProcessScope {
    param([int[]]$Ports)

    Write-Host 'App-specific processes this cleanup targets:'
    Write-Host '  - cmd.exe running scripts\Start-IZ-Clinical-Notes-Analyzer.cmd'
    Write-Host '  - powershell.exe or pwsh.exe running scripts\start-windows-local.ps1'
    Write-Host '  - powershell.exe or pwsh.exe running scripts\startup-windows-local.ps1'
    Write-Host '  - python.exe or pythonw.exe running Uvicorn for app.desktop_main:app from this repo backend'
    Write-Host '  - python.exe or pythonw.exe running Uvicorn for app.main:app from this repo backend smoke tests'
    Write-Host '  - node.exe running this repo frontend Vite dev or preview server, if present'
    Write-Host ''
    Write-Host 'Guardrails: this does not close browser windows, clear patient data, delete uploads,'
    Write-Host 'or kill unrelated Python, Node, PowerShell, or cmd processes by name alone.'
    Write-Host "Local ports checked only as supporting status: $($Ports -join ', ')"
    Write-Host ''
}

function Stop-AppTargets {
    param([object[]]$Targets)

    if ($Targets.Count -eq 0) {
        Write-Pass 'No running app-specific processes were found.'
        return
    }

    Write-Info "Found $($Targets.Count) app-specific process(es) to stop."
    foreach ($target in $Targets) {
        Write-Host "  PID $($target.ProcessId) $($target.Name): $($target.Reasons)"
    }
    Write-Host ''

    foreach ($target in $Targets) {
        if ($DryRun) {
            Write-Info "Dry run: would stop PID $($target.ProcessId) $($target.Name)."
            continue
        }

        Write-Info "Stopping PID $($target.ProcessId) $($target.Name): $($target.Reasons)"
        try {
            Stop-Process -Id $target.ProcessId -Force -ErrorAction Stop
        }
        catch [Microsoft.PowerShell.Commands.ProcessCommandException] {
            Write-Warn "PID $($target.ProcessId) was already stopped."
        }
        catch {
            Write-Warn "Could not stop PID $($target.ProcessId): $($_.Exception.Message)"
        }
    }
}

function Read-RestartChoice {
    if ($Restart) {
        Write-Info 'Restart requested by command-line switch.'
        return $true
    }

    if ($NoRestartPrompt) {
        Write-Info 'Restart prompt skipped by command-line switch.'
        return $false
    }

    while ($true) {
        Write-Host ''
        Write-Host 'Do you want to restart the app?'
        $answer = Read-Host 'Enter Y or N'
        $clean = $answer.Trim().ToLowerInvariant()
        if ($clean -in @('y', 'yes')) { return $true }
        if ([string]::IsNullOrWhiteSpace($clean) -or $clean -in @('n', 'no')) { return $false }
        Write-Warn 'Please enter Y or N.'
    }
}

function Start-AppLauncher {
    if (!(Test-Path $StartCmd)) {
        throw "Restart launcher was not found at $StartCmd"
    }

    Write-Info "Starting the normal launcher: $StartCmd"
    $argumentList = "/d /c `"`"$StartCmd`"`""
    Start-Process -FilePath $env:ComSpec -ArgumentList $argumentList -WorkingDirectory $RootDir -WindowStyle Normal | Out-Null
    $script:RestartLaunched = $true
    Write-Pass 'Restart launched in a normal app console window.'
}

try {
    Set-Location $RootDir
    Write-Host 'IZ Clinical Notes Analyzer cleanup'
    Write-Host "Repo: $RootDir"
    Write-Host "Local app data: $AppDataRoot"
    Write-Host ''

    $ports = @(Get-ConfiguredBackendPorts)
    Show-ProcessScope -Ports $ports

    $targets = @(Get-AppProcessTargets -Ports $ports)
    Stop-AppTargets -Targets $targets

    if (-not $DryRun) {
        Start-Sleep -Milliseconds 800
        $remaining = @(Get-AppProcessTargets -Ports $ports)
        if ($remaining.Count -gt 0) {
            Write-Warn 'Some app-specific processes are still running after cleanup:'
            foreach ($process in $remaining) {
                Write-Host "  PID $($process.ProcessId) $($process.Name): $($process.Reasons)"
            }
            throw 'Cleanup did not stop every app-specific process.'
        }
        Write-Pass 'All detected app-specific processes are stopped.'
    }
    else {
        Write-Pass 'Dry run complete. No processes were stopped.'
    }

    if (-not $DryRun -and (Read-RestartChoice)) {
        Start-AppLauncher
    }
    elseif (-not $DryRun) {
        Write-Info 'Restart skipped. You can start later with scripts\Start-IZ-Clinical-Notes-Analyzer.cmd.'
    }
}
catch {
    $ExitCode = 1
    Write-Fail $_.Exception.Message
}
finally {
    if (-not $NoPause -and -not $RestartLaunched) {
        Write-Host ''
        Read-Host 'Press Enter to close this window' | Out-Null
    }
}

exit $ExitCode
