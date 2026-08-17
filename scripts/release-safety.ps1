Set-StrictMode -Version Latest

$script:ReleaseSafetyPython = Join-Path $PSScriptRoot 'release_safety.py'
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $repositoryRoot 'backend\.venv\Scripts\python.exe'
$script:ReleaseSafetyPythonExecutable = if (Test-Path -LiteralPath $venvPython) { $venvPython } else { 'python' }

function Invoke-ReleaseSafetyPython {
    param([Parameter(Mandatory)][string[]]$Arguments)

    $output = @(& $script:ReleaseSafetyPythonExecutable $script:ReleaseSafetyPython @Arguments 2>&1)
    if ($LASTEXITCODE -ne 0) {
        $reason = 'forbidden_items_detected'
        try {
            $payload = ($output -join "`n") | ConvertFrom-Json
            if ($payload.reason) { $reason = [string]$payload.reason }
        } catch {
            $reason = 'release_safety_command_failed'
        }
        throw $reason
    }
    return @($output)
}

function Get-ForbiddenReleaseCategory {
    param([Parameter(Mandatory)][string]$RelativePath)

    $relative = ($RelativePath -replace '/', '\').Trim('\')
    if (-not $relative) { return $null }
    $lower = $relative.ToLowerInvariant()
    $parts = @($lower.Split([char[]]@('\', '/'), [System.StringSplitOptions]::RemoveEmptyEntries))
    $fileName = [System.IO.Path]::GetFileName($lower)
    if ([System.IO.Path]::IsPathRooted($RelativePath) -or $parts -contains '..') { return 'malformed_path' }
    $categories = @{
        '.git'='repository_metadata'; '.codegraph'='repository_metadata'; '.codex'='repository_metadata'; '.github'='repository_metadata'; '.agents'='repository_metadata'
        '.omo'='local_evidence'; 'node_modules'='dependencies'; 'venv'='environment'; '.pytest_cache'='cache'; '.mypy_cache'='cache'; '.ruff_cache'='cache'
        '__pycache__'='cache'; '.tmp'='cache'; '.cache'='cache'; 'reports'='report'; 'test-results'='report'; 'playwright-report'='report'; 'htmlcov'='report'
        'coverage'='report'; 'api-connectivity-reports'='report'; 'uploads'='upload'; 'exports'='clinical_export'; 'example-treatment-plans'='clinical_export'
        'logs'='log'; 'alleva-api-test-logs'='log'
    }
    foreach ($part in $parts) { if ($categories.ContainsKey($part)) { return $categories[$part] } }
    if ($fileName -eq '.env.example') { return $null }
    if ($fileName -eq '.debug-journal.md') { return 'local_evidence' }
    if ($fileName -eq '.env' -or $fileName.StartsWith('.env.') -or $fileName -eq '.alleva.local.ps1' -or $fileName -like '*.local.*' -or $fileName -like '*.local-*') { return 'local_config' }
    if ($fileName -eq 'app credentials info.md' -or $fileName -eq 'test-allevaapi.ps1' -or $fileName -like '*credential*' -or $fileName -like '*secret*' -or $fileName -like '*token*') { return 'secret' }
    if ($fileName -like '*.sqlite' -or $fileName -like '*.sqlite3' -or $fileName -like '*.db') { return 'database' }
    if ($fileName -like '*.izcnabackup') { return 'backup' }
    if ($fileName -like '*.log') { return 'log' }
    if ($fileName -like '*.tmp' -or $fileName -like '*.bak' -or $fileName -like '*.pyc') { return 'cache' }
    return $null
}

function Assert-SafeRelativePath {
    param([Parameter(Mandatory)][string]$RelativePath, [Parameter(Mandatory)][string]$Source)

    $category = Get-ForbiddenReleaseCategory -RelativePath $RelativePath
    if ($category) { throw "$Source contains forbidden category '$category'." }
}

function Assert-NoForbiddenPaths {
    param(
        [AllowEmptyCollection()][string[]]$RelativePaths = @(),
        [Parameter(Mandatory)][string]$Source
    )

    $categoryCounts = @{}
    foreach ($relativePath in $RelativePaths) {
        $category = Get-ForbiddenReleaseCategory -RelativePath $relativePath
        if ($category) { $categoryCounts[$category] = 1 + [int]$categoryCounts[$category] }
    }
    if ($categoryCounts.Count -ne 0) {
        $summary = @($categoryCounts.Keys | Sort-Object | ForEach-Object { "$_=$($categoryCounts[$_])" }) -join ','
        throw "$Source contains forbidden categories:$summary"
    }
}

function Assert-GitMetadataResult {
    param([Parameter(Mandatory)][int]$ExitCode, [AllowEmptyCollection()][string[]]$Output = @())

    if ($ExitCode -ne 0) { throw 'git_metadata_command_failed' }
    return @($Output)
}

function Assert-NoForbiddenRepositoryIndexItems {
    param([Parameter(Mandatory)][string]$RepositoryRoot, [string]$ExpectedHead = '', [switch]$AllowDirty)

    if (-not $ExpectedHead) { $ExpectedHead = (& git -C $RepositoryRoot rev-parse HEAD) }
    $arguments = @('verify-git-source', '--repository-root', $RepositoryRoot, '--expected-head', $ExpectedHead)
    if ($AllowDirty) { $arguments += '--allow-dirty' }
    $null = Invoke-ReleaseSafetyPython -Arguments $arguments
}

function Assert-NoForbiddenReleaseItems {
    param([Parameter(Mandatory)][string]$TargetPackageDir)

    $null = Invoke-ReleaseSafetyPython -Arguments @('scan-tree', '--path', $TargetPackageDir)
}

function Assert-ZipHasNoForbiddenItems {
    param([Parameter(Mandatory)][string]$ZipPath)

    $null = Invoke-ReleaseSafetyPython -Arguments @('scan-zip', '--path', $ZipPath)
}
