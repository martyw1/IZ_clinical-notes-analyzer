[CmdletBinding()]
param([int]$Port = 8000)

$ErrorActionPreference = 'Stop'
$RootDir = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$VenvDir = Join-Path $RootDir 'backend\.venv'
$VenvPython = Join-Path $VenvDir 'Scripts\python.exe'

function Write-Step($Message) { Write-Host "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $Message" }

function Assert-PythonVersion {
    param([string]$PythonExe)
    $versionText = & $PythonExe -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')"
    if ($LASTEXITCODE -ne 0) { throw "Could not run Python at $PythonExe." }
    $version = [version]$versionText.Trim()
    if ($version -lt [version]'3.11.0') { throw "Python 3.11+ is required. Found Python $version at $PythonExe." }
    return $version
}

function New-BackendVirtualEnvironment {
    New-Item -ItemType Directory -Path (Split-Path $VenvDir -Parent) -Force | Out-Null

    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCommand) {
        Write-Step "Creating backend virtual environment with $($pythonCommand.Source)."
        & $pythonCommand.Source -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)"
        if ($LASTEXITCODE -eq 0) {
            & $pythonCommand.Source -m venv $VenvDir
            if ($LASTEXITCODE -eq 0) { return }
        }
    }

    $pyCommand = Get-Command py -ErrorAction SilentlyContinue
    if ($pyCommand) {
        Write-Step "Creating backend virtual environment with Python Launcher at $($pyCommand.Source)."
        & $pyCommand.Source -3.11 -m venv $VenvDir
        if ($LASTEXITCODE -eq 0) { return }
        & $pyCommand.Source -3 -m venv $VenvDir
        if ($LASTEXITCODE -eq 0) { return }
    }

    throw 'Python 3.11+ was not found or could not create backend\.venv. Install Python 3.11+ and reopen PowerShell.'
}

Set-Location $RootDir
$env:PYTHONPATH = Join-Path $RootDir 'backend'

if (!(Test-Path $VenvPython)) {
    New-BackendVirtualEnvironment
}
if (!(Test-Path $VenvPython)) { throw 'backend\.venv\Scripts\python.exe was not created.' }
$pythonVersion = Assert-PythonVersion -PythonExe $VenvPython
Write-Step "Using Python $pythonVersion at $VenvPython."

& $VenvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw 'pip upgrade failed.' }

& $VenvPython -m pip install -r (Join-Path $RootDir 'backend\requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Backend dependency installation failed.' }

Start-Process "http://localhost:$Port"
& $VenvPython -m uvicorn app.desktop_main:app --app-dir (Join-Path $RootDir 'backend') --host 127.0.0.1 --port $Port
if ($LASTEXITCODE -ne 0) { throw 'Desktop local FastAPI server exited with an error.' }
