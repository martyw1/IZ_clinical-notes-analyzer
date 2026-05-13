[CmdletBinding()]
param([int]$Port = 8000)

$ErrorActionPreference = 'Stop'
$RootDir = Resolve-Path (Join-Path $PSScriptRoot '..')
$VenvPython = Join-Path $RootDir 'backend\.venv\Scripts\python.exe'
$SystemPython = Get-Command python -ErrorAction SilentlyContinue
$Python = if (Test-Path $VenvPython) { $VenvPython } elseif ($SystemPython) { $SystemPython.Source } else { throw 'Python 3.11+ was not found.' }

Set-Location $RootDir
$env:PYTHONPATH = Join-Path $RootDir 'backend'
if (!(Test-Path $VenvPython)) {
    & $Python -m venv (Join-Path $RootDir 'backend\.venv')
    $Python = $VenvPython
}
& $Python -m pip install -r (Join-Path $RootDir 'backend\requirements.txt')
Start-Process "http://localhost:$Port"
& $Python -m uvicorn app.desktop_main:app --app-dir (Join-Path $RootDir 'backend') --host 127.0.0.1 --port $Port
