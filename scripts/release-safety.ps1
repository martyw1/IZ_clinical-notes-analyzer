function Get-ForbiddenReleaseCategory {
    param(
        [Parameter(Mandatory)]
        [string]$RelativePath
    )

    $relative = ($RelativePath -replace '/', '\').Trim('\')
    if (-not $relative) { return $null }

    $lower = $relative.ToLowerInvariant()
    $parts = @($lower.Split([char[]]@('\', '/'), [System.StringSplitOptions]::RemoveEmptyEntries))
    $fileName = [System.IO.Path]::GetFileName($lower)

    if ([System.IO.Path]::IsPathRooted($RelativePath) -or $parts -contains '..') { return 'malformed_path' }

    foreach ($part in $parts) {
        if ($part -in @('.git', '.codegraph', '.codex', '.github', '.agents')) { return 'repository_metadata' }
        if ($part -eq '.omo') { return 'local_evidence' }
        if ($part -eq 'node_modules') { return 'dependencies' }
        if ($part -eq 'venv' -or $part -like '.venv*') { return 'environment' }
        if ($part -in @('.pytest_cache', '.mypy_cache', '.ruff_cache', '__pycache__', '.tmp', '.cache')) { return 'cache' }
        if ($part -in @('reports', 'test-results', 'playwright-report', 'htmlcov', 'coverage', 'api-connectivity-reports')) { return 'report' }
        if ($part -eq 'uploads') { return 'upload' }
        if ($part -in @('exports', 'example-treatment-plans')) { return 'clinical_export' }
        if ($part -in @('logs', 'alleva-api-test-logs')) { return 'log' }
    }

    if ($fileName -eq '.debug-journal.md') { return 'local_evidence' }
    if ($fileName -eq '.env.example') { return $null }
    if ($fileName -eq '.env' -or $fileName.StartsWith('.env.') -or $fileName -eq '.alleva.local.ps1' -or $fileName -like '*.local.*') {
        return 'local_config'
    }
    if ($fileName -eq 'app credentials info.md' -or $fileName -eq 'test-allevaapi.ps1' -or $fileName -like '*credential*' -or $fileName -like '*secret*' -or $fileName -like '*token*') {
        return 'secret'
    }
    if ($fileName -like '*.sqlite' -or $fileName -like '*.sqlite3' -or $fileName -like '*.db') {
        return 'database'
    }
    if ($fileName -like '*.log') { return 'log' }
    if ($fileName -like '*.tmp' -or $fileName -like '*.bak' -or $fileName -like '*.pyc') { return 'cache' }

    return $null
}

function Assert-SafeRelativePath {
    param(
        [Parameter(Mandatory)]
        [string]$RelativePath,
        [Parameter(Mandatory)]
        [string]$Source
    )

    $category = Get-ForbiddenReleaseCategory -RelativePath $RelativePath
    if ($category) {
        throw "$Source contains forbidden category '$category'."
    }
}

function Assert-NoForbiddenPaths {
    param(
        [AllowEmptyCollection()]
        [string[]]$RelativePaths = @(),
        [Parameter(Mandatory)]
        [string]$Source
    )

    $categoryCounts = @{}
    foreach ($relativePath in $RelativePaths) {
        $category = Get-ForbiddenReleaseCategory -RelativePath $relativePath
        if ($category) {
            $categoryCounts[$category] = 1 + [int]$categoryCounts[$category]
        }
    }
    if ($categoryCounts.Count -ne 0) {
        $summary = @($categoryCounts.Keys | Sort-Object | ForEach-Object { "$_=$($categoryCounts[$_])" }) -join ','
        throw "$Source contains forbidden categories:$summary"
    }
}

function Assert-GitMetadataResult {
    param(
        [Parameter(Mandatory)]
        [int]$ExitCode,
        [AllowEmptyCollection()]
        [string[]]$Output = @()
    )

    if ($ExitCode -ne 0) {
        throw 'git_metadata_command_failed'
    }
    return @($Output)
}

function Assert-NoForbiddenRepositoryIndexItems {
    param(
        [Parameter(Mandatory)]
        [string]$RepositoryRoot,
        [string]$ExpectedHead = '',
        [switch]$AllowDirty
    )

    $resolvedRoot = (Resolve-Path -LiteralPath $RepositoryRoot).Path
    $gitRoot = @(& git -C $resolvedRoot rev-parse --show-toplevel 2>$null)
    $gitRoot = @(Assert-GitMetadataResult -ExitCode $LASTEXITCODE -Output $gitRoot)
    if ($gitRoot.Count -ne 1) {
        throw 'Repository safety scan could not resolve Git metadata.'
    }
    if (-not [string]::Equals((Resolve-Path -LiteralPath $gitRoot[0]).Path, $resolvedRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw 'Repository safety scan root mismatch.'
    }

    $head = @(& git -C $resolvedRoot rev-parse HEAD 2>$null)
    $head = @(Assert-GitMetadataResult -ExitCode $LASTEXITCODE -Output $head)
    if ($head.Count -ne 1 -or $head[0] -notmatch '^[0-9a-f]{40}$') {
        throw 'malformed_repository_head'
    }
    if ($ExpectedHead) {
        if ($ExpectedHead -notmatch '^[0-9a-f]{40}$') { throw 'malformed_expected_head' }
        if ($ExpectedHead -ne $head[0]) { throw 'stale_repository_state' }
    }

    $dirtyEntries = @(& git -C $resolvedRoot status --porcelain=v1 --untracked-files=no 2>$null)
    $dirtyEntries = @(Assert-GitMetadataResult -ExitCode $LASTEXITCODE -Output $dirtyEntries)
    if (-not $AllowDirty -and $dirtyEntries.Count -ne 0) { throw 'dirty_worktree' }

    $staged = @(& git -C $resolvedRoot diff --cached --name-only --diff-filter=ACMR 2>$null)
    $staged = @(Assert-GitMetadataResult -ExitCode $LASTEXITCODE -Output $staged)
    $untracked = @(& git -C $resolvedRoot ls-files --others --exclude-standard 2>$null)
    $untracked = @(Assert-GitMetadataResult -ExitCode $LASTEXITCODE -Output $untracked)
    Assert-NoForbiddenPaths -RelativePaths @($staged + $untracked) -Source 'Repository index'
}

function Assert-NoForbiddenReleaseItems {
    param(
        [Parameter(Mandatory)]
        [string]$TargetPackageDir
    )

    $resolvedPackageDir = (Resolve-Path -LiteralPath $TargetPackageDir).Path
    $packagePrefix = $resolvedPackageDir.TrimEnd([char[]]@('\', '/')) + [System.IO.Path]::DirectorySeparatorChar
    $relativePaths = @(Get-ChildItem -LiteralPath $resolvedPackageDir -Recurse -Force -ErrorAction Stop | ForEach-Object {
        $fullName = [System.IO.Path]::GetFullPath($_.FullName)
        if (-not $fullName.StartsWith($packagePrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw 'Release package path escaped the scan root.'
        }
        $fullName.Substring($packagePrefix.Length)
    })
    Assert-NoForbiddenPaths -RelativePaths $relativePaths -Source 'Release package'
}

function Assert-ZipHasNoForbiddenItems {
    param(
        [Parameter(Mandatory)]
        [string]$ZipPath
    )

    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip = [System.IO.Compression.ZipFile]::OpenRead((Resolve-Path -LiteralPath $ZipPath).Path)
    try {
        $relativePaths = @($zip.Entries | ForEach-Object { $_.FullName })
        Assert-NoForbiddenPaths -RelativePaths $relativePaths -Source 'Release zip'
    } finally {
        $zip.Dispose()
    }
}
