[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$RecoveryRepo = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$RecoveryPython = Join-Path $RecoveryRepo 'backend\.venv\Scripts\python.exe'
$RecoveryEvidence = Join-Path $RecoveryRepo '.omo\evidence\admin-recovery-build'
$RecoveryOutput = Join-Path $RecoveryRepo 'output\admin-recovery'
if (-not (Test-Path -LiteralPath $RecoveryPython)) { throw 'The developer build environment is missing.' }
New-Item -ItemType Directory -Path $RecoveryEvidence,$RecoveryOutput -Force | Out-Null
& $RecoveryPython -m PyInstaller --noconfirm --clean --onefile --console --name Reset-IZ-Admin --paths (Join-Path $RecoveryRepo 'backend') --paths $PSScriptRoot --hidden-import passlib.handlers.pbkdf2 --distpath $RecoveryOutput --workpath (Join-Path $RecoveryEvidence 'build') --specpath $RecoveryEvidence (Join-Path $PSScriptRoot 'Reset-IZ-Admin.py')
if ($LASTEXITCODE -ne 0) { throw 'Recovery executable build failed.' }
$env:PYTHONPATH = Join-Path $RecoveryRepo 'backend'
& $RecoveryPython -m pytest $PSScriptRoot -q --tb=short
if ($LASTEXITCODE -ne 0) { throw 'Recovery validation failed. Do not distribute this executable.' }
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'READ-ME-FIRST.txt') -Destination $RecoveryOutput -Force
Compress-Archive -LiteralPath (Join-Path $RecoveryOutput 'Reset-IZ-Admin.exe'),(Join-Path $RecoveryOutput 'READ-ME-FIRST.txt') -DestinationPath (Join-Path $RecoveryRepo 'output\IZ-Admin-Recovery-beta.3.zip') -Force
Write-Host 'Validated recovery ZIP is ready in the output folder.'
