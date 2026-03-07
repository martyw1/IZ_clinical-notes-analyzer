[CmdletBinding()]
param(
    [switch]$SkipWingetInstall
)

$ErrorActionPreference = 'Stop'

$RootDir = Split-Path -Path $PSScriptRoot -Parent
$LogDir = Join-Path $RootDir 'logs'
if (!(Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir | Out-Null
}
$Timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$LogFile = Join-Path $LogDir "startup-windows-$Timestamp.log"
Start-Transcript -Path $LogFile -Append | Out-Null

function Write-Info($Message) { Write-Host "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] [INFO] $Message" }
function Write-Warn($Message) { Write-Host "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] [WARN] $Message" -ForegroundColor Yellow }
function Write-Pass($Message) { Write-Host "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] [PASS] $Message" -ForegroundColor Green }

function Get-EnvValue {
    param(
        [string]$EnvFile,
        [string]$Key
    )

    if (!(Test-Path $EnvFile)) {
        return $null
    }

    $line = Get-Content $EnvFile | Where-Object { $_ -match "^$Key=" } | Select-Object -Last 1
    if (!$line) {
        return $null
    }
    return $line.Substring($Key.Length + 1)
}

function Set-EnvValue {
    param(
        [string]$EnvFile,
        [string]$Key,
        [string]$Value
    )

    $lines = if (Test-Path $EnvFile) { Get-Content $EnvFile } else { @() }
    $updated = $false
    $newLines = foreach ($line in $lines) {
        if ($line -match "^$Key=") {
            $updated = $true
            "$Key=$Value"
        }
        else {
            $line
        }
    }

    if (!$updated) {
        $newLines += "$Key=$Value"
    }

    Set-Content -Path $EnvFile -Value $newLines
}

function Build-DatabaseUrl {
    param(
        [string]$User,
        [string]$Password,
        [string]$Host,
        [string]$Port,
        [string]$Database
    )

    $encodedUser = [System.Uri]::EscapeDataString($User)
    $encodedPassword = [System.Uri]::EscapeDataString($Password)
    $encodedDatabase = [System.Uri]::EscapeDataString($Database)
    return "postgresql+psycopg://$encodedUser:$encodedPassword@$Host`:$Port/$encodedDatabase"
}

function Initialize-DedicatedDbEnv {
    param([string]$EnvFile)

    $postgresPort = if ($env:POSTGRES_PORT) { $env:POSTGRES_PORT } elseif (Get-EnvValue $EnvFile 'POSTGRES_PORT') { Get-EnvValue $EnvFile 'POSTGRES_PORT' } else { '5432' }
    $databaseHost = if (Get-EnvValue $EnvFile 'DATABASE_HOST') { Get-EnvValue $EnvFile 'DATABASE_HOST' } else { '127.0.0.1' }
    $databaseName = if (Get-EnvValue $EnvFile 'DATABASE_NAME') { Get-EnvValue $EnvFile 'DATABASE_NAME' } elseif (Get-EnvValue $EnvFile 'POSTGRES_DB') { Get-EnvValue $EnvFile 'POSTGRES_DB' } else { 'iz_clinical_notes_analyzer' }
    $databaseUser = if (Get-EnvValue $EnvFile 'DATABASE_USER') { Get-EnvValue $EnvFile 'DATABASE_USER' } elseif (Get-EnvValue $EnvFile 'POSTGRES_USER') { Get-EnvValue $EnvFile 'POSTGRES_USER' } else { 'iz_clinical_notes_app' }
    $databasePassword = if (Get-EnvValue $EnvFile 'DATABASE_PASSWORD') { Get-EnvValue $EnvFile 'DATABASE_PASSWORD' } elseif (Get-EnvValue $EnvFile 'POSTGRES_PASSWORD') { Get-EnvValue $EnvFile 'POSTGRES_PASSWORD' } else { 'change-me-app' }
    $postgresVolumeName = if (Get-EnvValue $EnvFile 'POSTGRES_VOLUME_NAME') { Get-EnvValue $EnvFile 'POSTGRES_VOLUME_NAME' } else { 'iz_clinical_notes_analyzer_postgres_data' }
    $databaseUrl = Build-DatabaseUrl -User $databaseUser -Password $databasePassword -Host $databaseHost -Port $postgresPort -Database $databaseName

    Set-EnvValue $EnvFile 'POSTGRES_PORT' $postgresPort
    Set-EnvValue $EnvFile 'POSTGRES_VOLUME_NAME' $postgresVolumeName
    Set-EnvValue $EnvFile 'DATABASE_HOST' $databaseHost
    Set-EnvValue $EnvFile 'DATABASE_PORT' $postgresPort
    Set-EnvValue $EnvFile 'DATABASE_NAME' $databaseName
    Set-EnvValue $EnvFile 'DATABASE_USER' $databaseUser
    Set-EnvValue $EnvFile 'DATABASE_PASSWORD' $databasePassword
    Set-EnvValue $EnvFile 'POSTGRES_SERVICE_HOST' 'postgres'
    Set-EnvValue $EnvFile 'DATABASE_URL' $databaseUrl
    Set-EnvValue $EnvFile 'POSTGRES_DB' $databaseName
    Set-EnvValue $EnvFile 'POSTGRES_USER' $databaseUser
    Set-EnvValue $EnvFile 'POSTGRES_PASSWORD' $databasePassword

    return @{
        PostgresPort = $postgresPort
        DatabaseName = $databaseName
        DatabaseUser = $databaseUser
        DatabasePassword = $databasePassword
    }
}

function Wait-ForDedicatedPostgres {
    param(
        [string]$DatabaseUser,
        [string]$DatabasePassword
    )

    for ($attempt = 1; $attempt -le 40; $attempt++) {
        try {
            docker compose exec -T -e "PGPASSWORD=$DatabasePassword" postgres psql -U $DatabaseUser -d postgres -v ON_ERROR_STOP=1 -c "SELECT 1" | Out-Null
            Write-Pass "Dedicated PostgreSQL is reachable (attempt $attempt/40)."
            return
        }
        catch {
            Start-Sleep -Seconds 2
        }
    }

    throw 'Dedicated PostgreSQL did not become ready in time.'
}

function Ensure-DedicatedDatabase {
    param(
        [string]$DatabaseName,
        [string]$DatabaseUser,
        [string]$DatabasePassword
    )

    $bootstrapSql = @"
SELECT format('CREATE DATABASE %I OWNER %I', :'app_db_name', :'app_db_user')
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = :'app_db_name') \gexec
SELECT format('ALTER DATABASE %I OWNER TO %I', :'app_db_name', :'app_db_user') \gexec
"@

    $bootstrapSql | docker compose exec -T -e "PGPASSWORD=$DatabasePassword" postgres psql -U $DatabaseUser -d postgres -v ON_ERROR_STOP=1 -v "app_db_name=$DatabaseName" -v "app_db_user=$DatabaseUser" | Out-Null

    $schemaSql = @"
SELECT format('ALTER SCHEMA public OWNER TO %I', :'app_db_user') \gexec
SELECT format('GRANT ALL ON SCHEMA public TO %I', :'app_db_user') \gexec
SELECT format('ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO %I', :'app_db_user') \gexec
SELECT format('ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO %I', :'app_db_user') \gexec
"@

    $schemaSql | docker compose exec -T -e "PGPASSWORD=$DatabasePassword" postgres psql -U $DatabaseUser -d $DatabaseName -v ON_ERROR_STOP=1 -v "app_db_user=$DatabaseUser" | Out-Null
}

function Ensure-Command {
    param(
        [string]$Command,
        [string]$WingetId,
        [string]$DisplayName
    )

    if (Get-Command $Command -ErrorAction SilentlyContinue) {
        Write-Pass "Found $DisplayName"
        return
    }

    if ($SkipWingetInstall) {
        throw "$DisplayName is missing and -SkipWingetInstall was provided."
    }

    if (!(Get-Command winget -ErrorAction SilentlyContinue)) {
        throw "winget is required to install missing dependencies automatically."
    }

    Write-Info "Installing $DisplayName via winget ($WingetId)"
    winget install --id $WingetId --accept-source-agreements --accept-package-agreements --silent
}

try {
    Set-Location $RootDir
    Write-Info "Starting Windows bootstrap from $RootDir"
    $EnvFile = Join-Path $RootDir '.env'

    if (!(Test-Path $EnvFile)) {
        Copy-Item (Join-Path $RootDir '.env.example') $EnvFile
        Write-Info 'Created .env from .env.example'
    } else {
        Write-Pass '.env already exists'
    }

    $dbConfig = Initialize-DedicatedDbEnv -EnvFile $EnvFile
    Write-Info ("Dedicated DB config: {0}/{1} on localhost:{2}" -f $dbConfig.DatabaseName, $dbConfig.DatabaseUser, $dbConfig.PostgresPort)

    Ensure-Command -Command git -WingetId Git.Git -DisplayName 'Git'
    Ensure-Command -Command python -WingetId Python.Python.3.11 -DisplayName 'Python 3.11+'
    Ensure-Command -Command npm -WingetId OpenJS.NodeJS.LTS -DisplayName 'Node.js LTS (npm)'
    Ensure-Command -Command docker -WingetId Docker.DockerDesktop -DisplayName 'Docker Desktop'

    Write-Info 'Validating Docker engine availability'
    docker info | Out-Null
    docker compose version | Out-Null
    Write-Pass 'Docker engine and compose plugin are available'

    Write-Info 'Setting up backend Python environment'
    python -m venv backend/.venv
    & (Join-Path $RootDir 'backend/.venv/Scripts/python.exe') -m pip install --upgrade pip
    & (Join-Path $RootDir 'backend/.venv/Scripts/python.exe') -m pip install -r (Join-Path $RootDir 'backend/requirements.txt')

    Write-Info 'Setting up frontend Node environment'
    Set-Location (Join-Path $RootDir 'frontend')
    npm install
    Set-Location $RootDir

    Write-Info 'Starting dedicated PostgreSQL service'
    docker compose pull
    docker compose up -d postgres
    Wait-ForDedicatedPostgres -DatabaseUser $dbConfig.DatabaseUser -DatabasePassword $dbConfig.DatabasePassword
    Ensure-DedicatedDatabase -DatabaseName $dbConfig.DatabaseName -DatabaseUser $dbConfig.DatabaseUser -DatabasePassword $dbConfig.DatabasePassword

    Write-Info 'Starting full Docker Compose stack'
    docker compose up -d --build

    Write-Info 'Current service status'
    docker compose ps

    Write-Pass "Startup complete. Logs are in $LogFile"
}
catch {
    Write-Error "Startup failed: $($_.Exception.Message)"
    throw
}
finally {
    Stop-Transcript | Out-Null
}
