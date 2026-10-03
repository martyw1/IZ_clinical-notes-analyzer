$ErrorActionPreference = 'Stop'
if (Get-NetTCPConnection -LocalPort 8767 -State Listen -ErrorAction SilentlyContinue) { throw 'Screenshot port is already in use; refusing to attach to an existing app' }
$repo = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$runId = 'training-' + [Guid]::NewGuid().ToString('N')
$runtime = Join-Path $env:LOCALAPPDATA "IZ-CNA-OfficeManager-Smoke/$runId"
New-Item -ItemType Directory -Path $runtime | Out-Null
@{ runId=$runId; dataDir=$runtime } | ConvertTo-Json | Set-Content (Join-Path $runtime 'owner.json') -Encoding ascii
$env:IZ_CNA_LOCAL_APP_DATA_DIR = $runtime
$env:IZ_CNA_ENV_FILE = ''
$env:IZ_OM_RUN_ID = $runId
$env:IZ_OM_EVIDENCE_DIR = $runtime
$env:IZ_CNA_BOOTSTRAP_ADMIN_USERNAME = 'training_admin'
$env:IZ_OM_PASSWORD = 'DemoOnly' + [Guid]::NewGuid().ToString('N') + '7'
$env:IZ_CNA_BOOTSTRAP_ADMIN_PASSWORD = $env:IZ_OM_PASSWORD
$env:IZ_CNA_SECRET_KEY = [Guid]::NewGuid().ToString('N') + [Guid]::NewGuid().ToString('N')
$env:IZ_CNA_DATA_ENCRYPTION_KEY = [Guid]::NewGuid().ToString('N') + [Guid]::NewGuid().ToString('N')
$env:IZ_CNA_LOCAL_SQLITE_DB_PATH = 'clinical-notes-analyzer-v2.sqlite3'
$env:ENVIRONMENT = 'development'
$env:PYTHONPATH = Join-Path $repo 'backend'
$python = Join-Path $repo 'backend/.venv/Scripts/python.exe'
& $python (Join-Path $repo 'frontend/e2e/office-manager/support/seed.py')
if ($LASTEXITCODE -ne 0) { throw 'Isolated training seed failed' }
$server = Start-Process -FilePath $python -ArgumentList @('-m','uvicorn','app.desktop_main:app','--host','127.0.0.1','--port','8767') -WorkingDirectory $repo -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $runtime 'server-output.txt') -RedirectStandardError (Join-Path $runtime 'server-error.txt')
try {
    $ready = $false
    for ($attempt=0; $attempt -lt 30; $attempt++) {
        try { $response=Invoke-WebRequest http://127.0.0.1:8767/api/health -TimeoutSec 2; $ready=$response.StatusCode -eq 200 } catch { $ready=$false }
        if ($ready) { break }
        Start-Sleep -Seconds 1
    }
    if (!$ready) { throw 'Isolated screenshot app did not start' }
    & node (Join-Path $PSScriptRoot 'capture-training-screens.mjs')
    if ($LASTEXITCODE -ne 0) { throw 'Screenshot capture failed' }
} finally {
    if (!$server.HasExited) { Stop-Process -Id $server.Id }
}
