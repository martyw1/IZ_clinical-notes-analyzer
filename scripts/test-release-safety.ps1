[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$python = Join-Path $repositoryRoot 'backend\.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { $python = 'python' }
& $python -m pytest (Join-Path $repositoryRoot 'backend\tests\test_release_safety_cross_platform.py') -q
if ($LASTEXITCODE -ne 0) { throw "release_safety_tests_failed:$LASTEXITCODE" }
Write-Output 'result=PASS'
