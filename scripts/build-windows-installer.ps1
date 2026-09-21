[CmdletBinding()]
param(
    [switch]$SkipTests,
    [switch]$SkipFrontendBuild,
    [switch]$ValidationOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-IzReleaseDirectoryName {
    param([Parameter(Mandatory = $true)][string]$PackageName)
    $sha = [Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [Text.UTF8Encoding]::new($false).GetBytes($PackageName)
        $hash = [BitConverter]::ToString($sha.ComputeHash($bytes)).Replace('-', '').ToLowerInvariant()
    } finally {
        $sha.Dispose()
    }
    return "IZ-CNA-$($hash.Substring(0, 16))"
}

$RootDir = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$Version = (Get-Content -LiteralPath (Join-Path $RootDir 'VERSION') -Raw).Trim()
$VersionMetadata = [IO.File]::ReadAllText(
    (Join-Path $RootDir 'VERSION.json'),
    [Text.UTF8Encoding]::new($false, $true)
) | ConvertFrom-Json -ErrorAction Stop
$Build = [string]$VersionMetadata.build
$ReleaseChannel = [string]$VersionMetadata.release_channel
$InstallerRevision = 1
$ProductId = 'r3.iz-clinical-notes-analyzer.desktop'
$ReleaseRoot = Join-Path $RootDir 'dist\windows-release'
$PackageName = "IZ-Clinical-Notes-Analyzer-v$Version-build-$Build-installer-r$InstallerRevision"
$FinalPackageDir = Join-Path $ReleaseRoot (Get-IzReleaseDirectoryName -PackageName $PackageName)
$FinalZipPath = Join-Path $ReleaseRoot "$PackageName.zip"
$FinalReceiptPath = Join-Path $ReleaseRoot "$PackageName.build-receipt.json"
$FinalGateEvidencePath = Join-Path $ReleaseRoot "$PackageName.build-gates.json"
$LatestPathsFile = Join-Path $ReleaseRoot 'latest-release-paths.txt'
$VenvDir = Join-Path $RootDir 'backend\.venv'
$VenvPython = Join-Path $VenvDir 'Scripts\python.exe'
. (Join-Path $RootDir 'scripts\release-safety.ps1')
Import-Module (Join-Path $RootDir 'scripts\installer\build-windows-package.psm1') -Force

function Write-Step($Message) { Write-Host "[setup] $Message" }
function Write-Build($Message) { Write-Host "[build] $Message" }
function Write-Ok($Message) { Write-Host "[ok] $Message" -ForegroundColor Green }
function Write-Warn($Message) { Write-Host "[warn] $Message" -ForegroundColor Yellow }
function Write-Fail($Message) { Write-Host "[fail] $Message" -ForegroundColor Red }

function Get-NormalizedPath {
    param([string]$Path)
    $trimChars = [char[]]@([System.IO.Path]::DirectorySeparatorChar, [System.IO.Path]::AltDirectorySeparatorChar)
    return [System.IO.Path]::GetFullPath($Path).TrimEnd($trimChars)
}

function Assert-PathInside {
    param([string]$Path, [string]$Parent, [string]$Label)
    $normalizedPath = Get-NormalizedPath -Path $Path
    $normalizedParent = Get-NormalizedPath -Path $Parent
    $separator = [System.IO.Path]::DirectorySeparatorChar
    if (-not $normalizedPath.StartsWith("$normalizedParent$separator", [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "$Label must be inside $normalizedParent; resolved to $normalizedPath"
    }
}

function Get-RelativePathInside {
    param([string]$Path, [string]$Parent)
    $normalizedPath = Get-NormalizedPath -Path $Path
    $normalizedParent = Get-NormalizedPath -Path $Parent
    $separator = [System.IO.Path]::DirectorySeparatorChar
    if (-not $normalizedPath.StartsWith("$normalizedParent$separator", [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Path $normalizedPath is not inside $normalizedParent"
    }
    return $normalizedPath.Substring($normalizedParent.Length + 1)
}

function Remove-GeneratedDirectory {
    param([string]$Path, [string]$Parent, [string]$Label)
    Assert-PathInside -Path $Path -Parent $Parent -Label $Label
    if (-not (Test-Path -LiteralPath $Path)) { return }
    if ((Get-Item -LiteralPath $Path).Attributes -band [System.IO.FileAttributes]::ReparsePoint) {
        throw "$Label cannot be a reparse point."
    }
    $emptyDir = Join-Path ([System.IO.Path]::GetTempPath()) "iz-cna-empty-$([Guid]::NewGuid().ToString('N'))"
    New-Item -ItemType Directory -Path $emptyDir | Out-Null
    try {
        robocopy $emptyDir $Path /MIR /NFL /NDL /NJH /NJS /NP | Out-Null
        if ($LASTEXITCODE -gt 7) { throw "cleanup mirror failed with robocopy exit code $LASTEXITCODE" }
    } finally {
        Remove-Item -LiteralPath $emptyDir -Recurse -Force -ErrorAction SilentlyContinue
    }
    Remove-Item -LiteralPath $Path -Recurse -Force
    $global:LASTEXITCODE = 0
}

function Copy-RepoContent {
    param([string]$Destination)
    $excludeDirs = @(
        (Join-Path $RootDir '.git'), (Join-Path $RootDir '.codegraph'), (Join-Path $RootDir '.omo'),
        (Join-Path $RootDir '.codex'), (Join-Path $RootDir '.github'), (Join-Path $RootDir '.venv'),
        (Join-Path $RootDir 'backend\.venv'), (Join-Path $RootDir 'backend\tests'),
        (Join-Path $RootDir 'frontend\node_modules'), (Join-Path $RootDir 'frontend\src'),
        (Join-Path $RootDir 'frontend\e2e'), (Join-Path $RootDir 'node_modules'),
        (Join-Path $RootDir 'pip'), (Join-Path $RootDir 'dist'), (Join-Path $RootDir 'output'),
        (Join-Path $RootDir 'black-hole-lab'), (Join-Path $RootDir 'scripts\admin_recovery'),
        (Join-Path $RootDir 'scripts\installer'), (Join-Path $RootDir 'scripts\tests'),
        (Join-Path $RootDir 'uploads'), (Join-Path $RootDir 'exports'), (Join-Path $RootDir 'logs'),
        (Join-Path $RootDir 'api-connectivity-reports'), (Join-Path $RootDir 'alleva-api-test-logs'),
        (Join-Path $RootDir '.pytest_cache'), (Join-Path $RootDir '.mypy_cache'),
        (Join-Path $RootDir '.ruff_cache'), (Join-Path $RootDir 'htmlcov'),
        (Join-Path $RootDir 'coverage'), (Join-Path $RootDir 'frontend\coverage'),
        (Join-Path $RootDir 'frontend\test-results'), (Join-Path $RootDir 'frontend\playwright-report'),
        (Join-Path $RootDir 'frontend\.agents'), (Join-Path $RootDir 'depricated'),
        (Join-Path $RootDir 'deprecated'), (Join-Path $RootDir 'depriceated'),
        (Join-Path $RootDir 'walkthroughs (2026-03-04)'),
        (Join-Path $RootDir 'video-extract (2026-06-05)'),
        (Join-Path $RootDir 'example-treatment-plans'),
        '__pycache__', '.codegraph', '.omo', '.codex', '.github', '.agents', 'node_modules',
        'pip', '.pytest_cache', '.tmp', '.cache', 'test-results', 'playwright-report',
        '.mypy_cache', '.ruff_cache', 'htmlcov', 'coverage', 'logs', 'uploads', 'exports',
        'reports', 'venv', 'api-connectivity-reports', 'alleva-api-test-logs'
    )
    $excludeFiles = @(
        '.git', '.env', '.env.*', '*.local.*', '*.local-*', '.alleva.local.ps1',
        'App Credentials Info.md', 'Test-AllevaApi.ps1', '*credential*', '*secret*', '*token*',
        '*.sqlite', '*.sqlite3', '*.db', '*.izcnabackup', '*.log', '*.tmp', '*.bak', '*.pyc',
        '.debug-journal.md', 'smoke-test-*.md', 'test-*.md', 'test-*.ps1', 'test-*.mjs', 'test_*.py',
        '*.test.*', '*.spec.*', '*controller*', 'Build-IZ-Windows-Installer.cmd',
        'Complete-Uninstall-IZ-Clinical-Notes-Analyzer.cmd', 'complete-uninstall-local-data.ps1'
    )
    robocopy $RootDir $Destination /MIR /XJ /XD $excludeDirs /XF $excludeFiles /NFL /NDL /NJH /NJS /NP | Out-Null
    if ($LASTEXITCODE -gt 7) { throw "robocopy failed with exit code $LASTEXITCODE" }
    $global:LASTEXITCODE = 0
}

function Copy-SafeDataTree {
    param([string]$Source, [string]$Destination)
    New-Item -ItemType Directory -Path $Destination -Force | Out-Null
    foreach ($item in Get-ChildItem -LiteralPath $Source -Recurse -Force) {
        if ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) {
            throw "Safe data source contains a reparse point: $($item.FullName)"
        }
    }
    foreach ($file in Get-ChildItem -LiteralPath $Source -Recurse -File) {
        $relativePath = Get-RelativePathInside -Path $file.FullName -Parent $Source
        if (Get-ForbiddenReleaseCategory -RelativePath $relativePath -Distribution) { continue }
        $destinationPath = Join-Path $Destination $relativePath
        New-Item -ItemType Directory -Path (Split-Path $destinationPath -Parent) -Force | Out-Null
        Copy-Item -LiteralPath $file.FullName -Destination $destinationPath
    }
}

function Copy-ApplicationMaintenanceHelpers {
    param([string]$TargetAppDirectory)
    $sourceRoot = Join-Path $RootDir 'scripts\installer'
    $targetRoot = Join-Path $TargetAppDirectory 'scripts\installer'
    $helperNames = @(
        'backup-verification.psm1', 'maintenance-common.psm1', 'maintenance-contracts.psm1',
        'maintenance-paths.psm1', 'maintenance-version.psm1', 'maintenance-lock.psm1',
        'maintenance-journal.psm1', 'maintenance-runtime.psm1'
    )
    foreach ($name in $helperNames) {
        if (-not (Test-Path -LiteralPath (Join-Path $sourceRoot $name) -PathType Leaf)) {
            throw "Required application maintenance helper is missing: $name"
        }
    }
    New-Item -ItemType Directory -Path $targetRoot -Force | Out-Null
    foreach ($name in $helperNames) {
        Copy-Item -LiteralPath (Join-Path $sourceRoot $name) -Destination (Join-Path $targetRoot $name)
    }
}

function Find-Python {
    $candidates = @(
        (Get-Command python.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -ErrorAction SilentlyContinue),
        (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python311\python.exe')
    ) | Where-Object { $_ -and (Test-Path -LiteralPath $_) }
    foreach ($candidate in $candidates) {
        try {
            $versionText = & $candidate -c "import sys; print('{}.{}.{}'.format(sys.version_info.major, sys.version_info.minor, sys.version_info.micro))" 2>$null
            if ($LASTEXITCODE -eq 0 -and [version]$versionText -ge [version]'3.11.0') { return $candidate }
        } catch { continue }
    }
    return $null
}

function Find-Npm {
    $commands = @(@(
        (Get-Command npm.cmd -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -ErrorAction SilentlyContinue),
        (Get-Command npm.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -ErrorAction SilentlyContinue)
    ) | Where-Object { $_ -and (Test-Path -LiteralPath $_) })
    if ($commands.Count -gt 0) { return $commands | Select-Object -First 1 }
    $wingetPackageRoot = Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Packages'
    if (Test-Path -LiteralPath $wingetPackageRoot) {
        return Get-ChildItem -Path $wingetPackageRoot -Recurse -Filter npm.cmd -ErrorAction SilentlyContinue |
            Select-Object -First 1 -ExpandProperty FullName
    }
    return $null
}

function Invoke-LoggedCommand {
    param([scriptblock]$Command, [string]$FailureMessage, [string]$LogPath, [switch]$Append)
    $logParent = Split-Path $LogPath -Parent
    if (-not (Test-Path -LiteralPath $logParent)) { New-Item -ItemType Directory -Path $logParent -Force | Out-Null }
    if (-not $Append) { [System.IO.File]::WriteAllText($LogPath, '', [System.Text.UTF8Encoding]::new($false)) }
    $previousErrorActionPreference = $ErrorActionPreference
    try {
        # Windows PowerShell 5.1 wraps native stderr as NativeCommandError. The
        # native exit code remains the build gate; a scriptblock throw still terminates.
        $ErrorActionPreference = 'Continue'
        & $Command *>&1 | Tee-Object -FilePath $LogPath -Append | ForEach-Object { Write-Host $_ }
        $exitCode = [int]$LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
    if ($exitCode -ne 0) { throw "$FailureMessage Exit code: $exitCode." }
    return [pscustomobject][ordered]@{
        exit_code = 0
        log_length = [long](Get-Item -LiteralPath $LogPath).Length
        log_sha256 = Get-IzFileSha256 -Path $LogPath
    }
}

function Ensure-BackendBuildEnvironment {
    param([string]$LogPath)
    $runtimeRequirements = Join-Path $RootDir 'backend\requirements-windows-local.txt'
    if (-not (Test-Path -LiteralPath $runtimeRequirements)) { $runtimeRequirements = Join-Path $RootDir 'backend\requirements.txt' }
    $buildRequirements = Join-Path $RootDir 'backend\requirements-build.txt'
    if (-not (Test-Path -LiteralPath $runtimeRequirements) -or -not (Test-Path -LiteralPath $buildRequirements)) {
        throw 'Backend runtime or build requirements file is missing.'
    }
    [System.IO.File]::WriteAllText($LogPath, '', [System.Text.UTF8Encoding]::new($false))
    if (-not (Test-Path -LiteralPath $VenvPython)) {
        $python = Find-Python
        if (-not $python) { throw 'Python 3.11 or newer was not found.' }
        Write-Step 'Creating backend environment...'
        $null = Invoke-LoggedCommand -Command { & $python -m venv $VenvDir } -FailureMessage 'Could not create backend\.venv.' -LogPath $LogPath -Append
    }
    Write-Step 'Installing backend runtime packages...'
    $null = Invoke-LoggedCommand -Command { & $VenvPython -m pip install -r $runtimeRequirements } -FailureMessage 'Backend runtime dependency installation failed.' -LogPath $LogPath -Append
    Write-Step 'Installing backend build/test packages...'
    $null = Invoke-LoggedCommand -Command { & $VenvPython -m pip install -r $buildRequirements } -FailureMessage 'Backend build/test dependency installation failed.' -LogPath $LogPath -Append
    $null = Invoke-LoggedCommand -Command { & $VenvPython -m pytest --version } -FailureMessage 'pytest is unavailable.' -LogPath $LogPath -Append
    Write-Ok 'Backend build environment is ready.'
}

function Invoke-InBuildQaEnvironment {
    param([string]$QaRoot, [scriptblock]$Action)
    $saved = @{}
    foreach ($name in @('LOCALAPPDATA', 'APPDATA', 'USERPROFILE', 'IZ_CNA_LOCAL_APP_DATA_DIR', 'IZ_CNA_ENV_FILE', 'PSModuleAnalysisCachePath')) {
        $item = Get-Item -LiteralPath "Env:$name" -ErrorAction SilentlyContinue
        $saved[$name] = if ($null -eq $item) { $null } else { [string]$item.Value }
    }
    $localAppData = Join-Path $QaRoot 'LocalAppData'
    $appData = Join-Path $QaRoot 'AppData'
    $userProfile = Join-Path $QaRoot 'UserProfile'
    $appLocalData = Join-Path $localAppData 'IZ Clinical Notes Analyzer'
    $moduleCache = Join-Path $QaRoot 'PowerShell\ModuleAnalysisCache'
    New-Item -ItemType Directory -Path $localAppData, $appData, $userProfile, $appLocalData, (Split-Path $moduleCache -Parent) -Force | Out-Null
    try {
        $env:LOCALAPPDATA = $localAppData
        $env:APPDATA = $appData
        $env:USERPROFILE = $userProfile
        $env:IZ_CNA_LOCAL_APP_DATA_DIR = $appLocalData
        $env:IZ_CNA_ENV_FILE = Join-Path $appLocalData '.env'
        $env:PSModuleAnalysisCachePath = $moduleCache
        & $Action
    } finally {
        foreach ($name in $saved.Keys) {
            if ($null -eq $saved[$name]) { Remove-Item -LiteralPath "Env:$name" -ErrorAction SilentlyContinue }
            else { Set-Item -LiteralPath "Env:$name" -Value $saved[$name] }
        }
    }
}

function Invoke-BackendTests {
    param([string]$LogPath, [string]$QaRoot)
    if ($SkipTests) {
        [System.IO.File]::WriteAllText($LogPath, 'validation-only: backend tests skipped', [System.Text.UTF8Encoding]::new($false))
        return [pscustomobject]@{ exit_code = 0; status = 'skipped'; log_length = (Get-Item $LogPath).Length; log_sha256 = Get-IzFileSha256 $LogPath }
    }
    Write-Step 'Running backend tests...'
    $observation = Invoke-InBuildQaEnvironment -QaRoot $QaRoot -Action {
        Remove-Item Env:\IZ_CNA_ENV_FILE -ErrorAction SilentlyContinue
        $previousPythonPath = $env:PYTHONPATH
        try {
            $env:PYTHONPATH = Join-Path $RootDir 'backend'
            Invoke-LoggedCommand -Command { & $VenvPython -m pytest (Join-Path $RootDir 'backend\tests') -q } -FailureMessage 'Backend tests failed.' -LogPath $LogPath
        } finally {
            if ($null -eq $previousPythonPath) { Remove-Item Env:\PYTHONPATH -ErrorAction SilentlyContinue }
            else { $env:PYTHONPATH = $previousPythonPath }
        }
    }
    $observation | Add-Member -NotePropertyName status -NotePropertyValue 'passed'
    Write-Ok 'Backend tests passed.'
    return $observation
}

function Assert-FrontendDist {
    $distDir = Join-Path $RootDir 'frontend\dist'
    $indexFile = Join-Path $distDir 'index.html'
    $assetsDir = Join-Path $distDir 'assets'
    if (-not (Test-Path -LiteralPath $indexFile -PathType Leaf)) { throw 'frontend\dist\index.html is missing.' }
    $assets = @(Get-ChildItem -LiteralPath $assetsDir -Recurse -File -ErrorAction SilentlyContinue)
    if (@($assets | Where-Object Extension -eq '.js').Count -eq 0 -or @($assets | Where-Object Extension -eq '.css').Count -eq 0) {
        throw 'frontend\dist does not contain JavaScript and CSS assets.'
    }
    if ((Get-Content -LiteralPath $indexFile -Raw) -notmatch '/assets/.+\.js') { throw 'frontend\dist\index.html does not reference a JavaScript asset.' }
}

function Invoke-FrontendBuild {
    param([string]$TestLogPath, [string]$BuildLogPath)
    if ($SkipFrontendBuild) {
        Assert-FrontendDist
        [System.IO.File]::WriteAllText($BuildLogPath, 'validation-only: existing frontend build inspected', [System.Text.UTF8Encoding]::new($false))
        [System.IO.File]::WriteAllText($TestLogPath, 'validation-only: frontend tests skipped with frontend build', [System.Text.UTF8Encoding]::new($false))
        return [pscustomobject]@{
            tests = [pscustomobject]@{ exit_code = 0; status = 'skipped'; log_length = (Get-Item $TestLogPath).Length; log_sha256 = Get-IzFileSha256 $TestLogPath }
            build = [pscustomobject]@{ exit_code = 0; status = 'skipped_existing'; log_length = (Get-Item $BuildLogPath).Length; log_sha256 = Get-IzFileSha256 $BuildLogPath }
        }
    }
    $npm = Find-Npm
    if (-not $npm) { throw 'Node.js/npm was not found.' }
    $previousPath = $env:PATH
    $env:PATH = "$(Split-Path $npm -Parent);$env:PATH"
    Push-Location (Join-Path $RootDir 'frontend')
    try {
        [System.IO.File]::WriteAllText($BuildLogPath, '', [System.Text.UTF8Encoding]::new($false))
        if (Test-Path -LiteralPath (Join-Path $RootDir 'frontend\package-lock.json')) {
            $null = Invoke-LoggedCommand -Command { & $npm ci } -FailureMessage 'npm ci failed.' -LogPath $BuildLogPath -Append
        } else {
            $null = Invoke-LoggedCommand -Command { & $npm install } -FailureMessage 'npm install failed.' -LogPath $BuildLogPath -Append
        }
        if ($SkipTests) {
            [System.IO.File]::WriteAllText($TestLogPath, 'validation-only: frontend tests skipped', [System.Text.UTF8Encoding]::new($false))
            $testObservation = [pscustomobject]@{ exit_code = 0; status = 'skipped'; log_length = (Get-Item $TestLogPath).Length; log_sha256 = Get-IzFileSha256 $TestLogPath }
        } else {
            $testObservation = Invoke-LoggedCommand -Command { & $npm run test -- --run } -FailureMessage 'Frontend tests failed.' -LogPath $TestLogPath
            $testObservation | Add-Member -NotePropertyName status -NotePropertyValue 'passed'
        }
        $buildObservation = Invoke-LoggedCommand -Command { & $npm run build } -FailureMessage 'Frontend build failed.' -LogPath $BuildLogPath -Append
        $buildObservation | Add-Member -NotePropertyName status -NotePropertyValue 'passed'
    } finally {
        Pop-Location
        $env:PATH = $previousPath
    }
    Assert-FrontendDist
    Write-Ok 'Frontend tests/build complete.'
    return [pscustomobject]@{ tests = $testObservation; build = $buildObservation }
}

function Build-DesktopRuntime {
    param([string]$TargetPackageDir, [string]$LogPath)
    $runtimeDir = Join-Path $TargetPackageDir 'app\runtime'
    $runtimeBuildRoot = Join-Path ([System.IO.Path]::GetTempPath()) "iz-cna-runtime-$([Guid]::NewGuid().ToString('N'))"
    $runtimeFrontendDir = Join-Path $runtimeBuildRoot 'data\frontend-dist'
    $runtimeConfigDir = Join-Path $runtimeBuildRoot 'data\config'
    $runtimeVersionFile = Join-Path $runtimeBuildRoot 'data\VERSION.json'
    $entryPoint = Join-Path $RootDir 'backend\app\desktop_runtime.py'
    if (-not (Test-Path -LiteralPath $entryPoint -PathType Leaf)) { throw "Desktop runtime entry point is missing: $entryPoint" }
    $versionFile = Join-Path $RootDir 'VERSION.json'
    if (-not (Test-Path -LiteralPath $versionFile -PathType Leaf)) { throw "Version metadata is missing: $versionFile" }
    $passlibHookDirectory = Join-Path $RootDir 'scripts\installer\pyinstaller-hooks'
    if (-not (Test-Path -LiteralPath (Join-Path $passlibHookDirectory 'hook-passlib.py') -PathType Leaf)) {
        throw 'The filtered PyInstaller passlib hook is missing.'
    }
    New-Item -ItemType Directory -Path $runtimeDir, $runtimeBuildRoot -Force | Out-Null
    try {
        Copy-SafeDataTree -Source (Join-Path $RootDir 'frontend\dist') -Destination $runtimeFrontendDir
        Copy-SafeDataTree -Source (Join-Path $RootDir 'config') -Destination $runtimeConfigDir
        Copy-Item -LiteralPath $versionFile -Destination $runtimeVersionFile -Force
        Write-Build 'Bundling the self-contained Windows desktop runtime...'
        $null = Invoke-LoggedCommand -Command {
            & $VenvPython -m PyInstaller --noconfirm --clean --onefile --noconsole --name IZClinicalNotesAnalyzer `
                --paths (Join-Path $RootDir 'backend') `
                --add-data "$runtimeFrontendDir;app\static" `
                --add-data "$runtimeConfigDir;config" `
                --add-data "$runtimeVersionFile;." `
                --collect-submodules app `
                --hidden-import app.desktop_main `
                --additional-hooks-dir $passlibHookDirectory `
                --exclude-module passlib.tests `
                --exclude-module pytest `
                --exclude-module _pytest `
                --distpath $runtimeDir `
                --workpath (Join-Path $runtimeBuildRoot 'work') `
                --specpath (Join-Path $runtimeBuildRoot 'spec') `
                $entryPoint
        } -FailureMessage 'Bundled Windows runtime build failed.' -LogPath $LogPath
    } finally {
        if (Test-Path -LiteralPath $runtimeBuildRoot) { Remove-Item -LiteralPath $runtimeBuildRoot -Recurse -Force }
    }
    $runtimeExe = Join-Path $runtimeDir 'IZClinicalNotesAnalyzer.exe'
    if (-not (Test-Path -LiteralPath $runtimeExe -PathType Leaf)) { throw 'Bundled Windows runtime was not produced.' }
    Write-Ok 'Self-contained Windows desktop runtime is present.'
    return $runtimeExe
}

function Write-InstallerFiles {
    param([string]$TargetPackageDir, [object]$LegacyProgramInventory)
    return Write-IzPackageInstallerFiles `
        -RepositoryRoot $RootDir `
        -PackageRoot $TargetPackageDir `
        -LegacyProgramInventory $LegacyProgramInventory
}

function Assert-RelativePathAllowed {
    param([string]$RelativePath, [string]$Source)
    Assert-SafeRelativePath -RelativePath $RelativePath -Source $Source -Distribution
}

function Assert-NoForbiddenReleaseItems {
    param([string]$TargetPackageDir)
    foreach ($item in Get-ChildItem -LiteralPath $TargetPackageDir -Recurse -Force -ErrorAction Stop) {
        if ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) {
            throw 'Release package contains a reparse point.'
        }
        Assert-RelativePathAllowed -RelativePath (Get-RelativePathInside -Path $item.FullName -Parent $TargetPackageDir) -Source 'Release package'
    }
    Write-Ok 'Release package forbidden-file scan passed.'
}

function Assert-ReleaseRequiredItems {
    param([string]$TargetPackageDir)
    $requiredItems = @(
        'app\backend', 'app\frontend', 'app\frontend\dist', 'app\frontend\dist\index.html',
        'app\VERSION', 'app\VERSION.json', 'app\runtime\IZClinicalNotesAnalyzer.exe',
        'app\config\rules', 'app\config\checklists\treatment-plan-v1.json',
        'app\docs\patient-treatment-plan-handling.md', 'app\docs\beta-client-test-run-guide.md', 'app\scripts',
        'Install-IZ-Clinical-Notes-Analyzer.cmd', 'Launch-IZ-Clinical-Notes-Analyzer.cmd',
        'Stop-IZ-Clinical-Notes-Analyzer.cmd', 'Collect-IZ-Clinical-Notes-Analyzer-Diagnostics.cmd',
        'Backup-IZ-Clinical-Notes-Analyzer.cmd', 'Restore-IZ-Clinical-Notes-Analyzer.cmd',
        'Uninstall-IZ-Clinical-Notes-Analyzer.cmd', 'Complete-Uninstall-IZ-Clinical-Notes-Analyzer.cmd',
        'release-manifest.json'
    )
    $requiredItems += @(Get-IzInstallerRuntimeRelativePaths | ForEach-Object { "installer\$_" })
    foreach ($item in $requiredItems) {
        if (-not (Test-Path -LiteralPath (Join-Path $TargetPackageDir $item))) { throw "Release package is missing required item: $item" }
    }
    Write-Ok 'Release package required-file validation passed.'
}

function Assert-ZipHasNoForbiddenItems {
    param([string]$ZipPath)
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip = [System.IO.Compression.ZipFile]::OpenRead($ZipPath)
    try {
        foreach ($entry in $zip.Entries) { Assert-RelativePathAllowed -RelativePath $entry.FullName -Source 'Release zip' }
    } finally { $zip.Dispose() }
    Write-Ok 'Release zip forbidden-file scan passed.'
}

function Get-StreamSha256 {
    param([System.IO.Stream]$Stream)
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($sha.ComputeHash($Stream))).Replace('-', '').ToLowerInvariant() }
    finally { $sha.Dispose() }
}

function Assert-ZipMatchesManifest {
    param([string]$ZipPath, [string]$PackageDir)
    $manifest = Assert-IzReleaseManifest -PackageRoot $PackageDir
    $expected = @{}
    foreach ($file in $manifest.files) { $expected[[string]$file.path] = $file }
    $manifestPath = Join-Path $PackageDir 'release-manifest.json'
    $expected['release-manifest.json'] = [pscustomobject]@{ path = 'release-manifest.json'; length = (Get-Item $manifestPath).Length; sha256 = Get-IzFileSha256 $manifestPath }
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip = [System.IO.Compression.ZipFile]::OpenRead($ZipPath)
    try {
        $entries = @($zip.Entries | Where-Object { $_.Name })
        if ($entries.Count -ne $expected.Count) { throw 'ZIP_FILE_COUNT_MISMATCH' }
        $seen = [System.Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
        foreach ($entry in $entries) {
            $name = $entry.FullName.Replace('\', '/')
            if (-not $seen.Add($name) -or -not $expected.ContainsKey($name)) { throw 'ZIP_MEMBER_MISMATCH' }
            $record = $expected[$name]
            if ([long]$entry.Length -ne [long]$record.length) { throw 'ZIP_MEMBER_LENGTH_MISMATCH' }
            $stream = $entry.Open()
            try { $entryHash = Get-StreamSha256 -Stream $stream } finally { $stream.Dispose() }
            if ($entryHash -cne [string]$record.sha256) { throw 'ZIP_MEMBER_HASH_MISMATCH' }
        }
    } finally { $zip.Dispose() }
    Write-Ok 'Release zip matches the internal manifest byte-for-byte.'
}

function Inspect-FrozenBundle {
    param([string]$RuntimePath, [string]$LogPath)
    $observation = Invoke-LoggedCommand -Command {
        & $VenvPython -m PyInstaller.utils.cliutils.archive_viewer -r -b $RuntimePath
    } -FailureMessage 'Frozen bundle inspection failed.' -LogPath $LogPath
    $listing = Get-Content -LiteralPath $LogPath -Raw
    foreach ($required in @('app.desktop_runtime', 'app.desktop_main', 'passlib', 'configparser', 'VERSION.json', 'treatment-plan-v1.json', 'app\static\index.html')) {
        if (-not $listing.Contains($required)) { throw "FROZEN_BUNDLE_REQUIRED_MEMBER_MISSING:$required" }
    }
    if ($listing -match '(?im)(^|[\s''"/\\])(?:app\.)?tests?(?:[./\\''"\s]|$)' -or
        $listing -match '(?im)(^|[\s''"/\\])pytest(?:[./\\''"\s]|$)' -or
        $listing -match '(?i)installer[\\/]templates|complete-uninstall-local-data') {
        throw 'FROZEN_BUNDLE_FORBIDDEN_MEMBER'
    }
    return [pscustomobject][ordered]@{
        exit_code = 0
        status = 'passed'
        executable_length = [long](Get-Item -LiteralPath $RuntimePath).Length
        executable_sha256 = Get-IzFileSha256 $RuntimePath
        listing_length = [long]$observation.log_length
        listing_sha256 = [string]$observation.log_sha256
    }
}

function Assert-PreservedArchives {
    $expected = @(
        [pscustomobject]@{ name = 'IZ-Clinical-Notes-Analyzer-v2.0.0-beta.3.zip'; length = 43716351L; sha256 = '9c5fd47203242e1a21df612f719f1c14fa4240c86ba869f924ec4690834fc89c'; version = '2.0.0-beta.3'; build = '2026.09.03.1' },
        [pscustomobject]@{ name = 'IZ-Clinical-Notes-Analyzer-v2.0.0-beta.4.zip'; length = 43873389L; sha256 = '67b83eea402566658dea6d64ac6cba37a192a7d1bd670cf560541324c0092b14'; version = '2.0.0-beta.4'; build = '2026.09.10.2' }
    )
    $verified = [Collections.Generic.List[object]]::new()
    foreach ($item in $expected) {
        $path = Join-Path $ReleaseRoot $item.name
        if (-not (Test-Path -LiteralPath $path -PathType Leaf) -or
            (Get-Item -LiteralPath $path).Length -ne $item.length -or
            (Get-IzFileSha256 $path) -cne $item.sha256) { throw "PRESERVED_ARCHIVE_CHANGED:$($item.name)" }
        $verified.Add([pscustomobject][ordered]@{
            name = $item.name
            length = [long]$item.length
            sha256 = $item.sha256
            version = $item.version
            build = $item.build
            path = (Resolve-Path -LiteralPath $path).Path
        })
    }
    Write-Ok 'Original beta.3 and beta.4 ZIP bytes remain unchanged.'
    return @($verified.ToArray())
}

function Assert-LegacyInstalledRelativePath {
    param([string]$Path)
    if ([string]::IsNullOrWhiteSpace($Path) -or $Path.Length -gt 1024 -or
        $Path.StartsWith('/') -or $Path.StartsWith('\\') -or $Path.Contains('//') -or
        $Path.IndexOf([char]0) -ge 0 -or $Path -match '^[A-Za-z]:' -or
        @($Path.Split('/') | Where-Object { $_ -in @('', '.', '..') }).Count -ne 0) {
        throw 'LEGACY_INVENTORY_PATH_INVALID'
    }
}

function Get-LegacyGeneratedCommandRecords {
    param([string]$InstallerSource)
    $definitions = @(
        [pscustomobject]@{ variable = 'Uninstaller'; path = 'Uninstall-IZ-Clinical-Notes-Analyzer.cmd' },
        [pscustomobject]@{ variable = 'CompleteUninstaller'; path = 'Complete-Uninstall-IZ-Clinical-Notes-Analyzer.cmd' }
    )
    $records = [Collections.Generic.List[object]]::new()
    foreach ($definition in $definitions) {
        $pattern = '(?ms)^@"\r?\n(?<body>(?:(?!\r?\n"@).)*)\r?\n"@\s*\|\s*Set-Content\s+-Path\s+\$' +
            [regex]::Escape($definition.variable) + '\s+-Encoding\s+ASCII\s*$'
        $matches = [regex]::Matches($InstallerSource, $pattern)
        if ($matches.Count -ne 1) { throw 'LEGACY_GENERATED_COMMAND_SOURCE_INVALID' }
        $body = $matches[0].Groups['body'].Value
        if ($body.Contains('$') -or $body.Contains('`')) { throw 'LEGACY_GENERATED_COMMAND_SOURCE_INVALID' }
        $content = $body.Replace("`r`n", "`n").Replace("`r", "`n").Replace("`n", "`r`n") + "`r`n"
        $bytes = [Text.ASCIIEncoding]::new().GetBytes($content)
        $sha = [Security.Cryptography.SHA256]::Create()
        try { $hash = ([BitConverter]::ToString($sha.ComputeHash($bytes))).Replace('-', '').ToLowerInvariant() }
        finally { $sha.Dispose(); [Array]::Clear($bytes, 0, $bytes.Length) }
        $records.Add([pscustomobject][ordered]@{ path = $definition.path; length = [long]$content.Length; sha256 = $hash })
    }
    return @($records.ToArray())
}

function New-LegacyProgramInventory {
    param([object[]]$Archives)
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $sources = [Collections.Generic.List[object]]::new()
    foreach ($source in $Archives) {
        $recordsByPath = [Collections.Generic.Dictionary[string,object]]::new([StringComparer]::OrdinalIgnoreCase)
        $archive = [IO.Compression.ZipFile]::OpenRead([string]$source.path)
        try {
            $fileCount = 0
            $expandedBytes = [long]0
            foreach ($entry in $archive.Entries) {
                if (-not $entry.Name) { continue }
                $fileCount++
                if ($fileCount -gt 10000 -or [long]$entry.Length -gt 536870912L -or
                    $expandedBytes -gt (2147483648L - [long]$entry.Length)) { throw 'LEGACY_ARCHIVE_BOUNDS_EXCEEDED' }
                $expandedBytes += [long]$entry.Length
                $archivePath = $entry.FullName.Replace('\\', '/')
                $installedPath = if ($archivePath.StartsWith('app/', [StringComparison]::Ordinal)) {
                    $archivePath.Substring(4)
                } elseif ($archivePath.StartsWith('installer/', [StringComparison]::Ordinal)) {
                    $archivePath
                } elseif ($archivePath -ceq 'release-manifest.json') {
                    $archivePath
                } else { $null }
                if (-not $installedPath) { continue }
                Assert-LegacyInstalledRelativePath $installedPath
                if ($recordsByPath.ContainsKey($installedPath)) { throw 'LEGACY_INVENTORY_PATH_COLLISION' }
                $stream = $entry.Open()
                try { $hash = Get-StreamSha256 -Stream $stream } finally { $stream.Dispose() }
                $recordsByPath.Add($installedPath, [pscustomobject][ordered]@{
                    path = $installedPath
                    length = [long]$entry.Length
                    sha256 = $hash
                })
            }
            $installEntries = @($archive.Entries | Where-Object {
                $_.FullName.Replace('\\', '/') -ceq 'installer/install-windows-release.ps1'
            })
            if ($installEntries.Count -ne 1) { throw 'LEGACY_INSTALLER_SOURCE_INVALID' }
            $stream = $installEntries[0].Open()
            $reader = [IO.StreamReader]::new($stream, [Text.UTF8Encoding]::new($false, $true), $true)
            try { $installerSource = $reader.ReadToEnd() } finally { $reader.Dispose(); $stream.Dispose() }
            foreach ($record in @(Get-LegacyGeneratedCommandRecords -InstallerSource $installerSource)) {
                $recordsByPath[[string]$record.path] = $record
            }
        } finally { $archive.Dispose() }
        $paths = [string[]]@($recordsByPath.Keys)
        [Array]::Sort($paths, [StringComparer]::Ordinal)
        $sources.Add([pscustomobject][ordered]@{
            archive_name = [string]$source.name
            archive_length = [long]$source.length
            archive_sha256 = [string]$source.sha256
            version = [string]$source.version
            build = [string]$source.build
            files = @($paths | ForEach-Object { $recordsByPath[$_] })
        })
    }
    return [pscustomobject][ordered]@{
        schema = 'iz-cna-legacy-program-inventory-v1'
        product_id = $ProductId
        sources = @($sources.ToArray())
    }
}

function Assert-ReleaseMetadata {
    if ($VersionMetadata.version -cne $Version -or $Version -cne '1.0.0' -or
        $Build -cne '2026.09.21.2' -or $ReleaseChannel -cne 'stable-local-desktop') {
        throw 'Release version metadata is inconsistent.'
    }
}

function Assert-CleanSourceRevision {
    param([string]$ExpectedHead)
    $head = (& git -C $RootDir rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0 -or $head -cne $ExpectedHead) { throw 'stale_repository_state' }
    $dirty = @(& git -C $RootDir status --porcelain=v1 --untracked-files=all)
    if ($LASTEXITCODE -ne 0 -or $dirty.Count -ne 0) { throw 'dirty_worktree' }
}

function New-OwnedRoot {
    param([string]$Parent, [string]$Name, [string]$Owner)
    if (-not (Test-Path -LiteralPath $Parent)) { New-Item -ItemType Directory -Path $Parent | Out-Null }
    if ((Get-Item -LiteralPath $Parent).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'OWNED_PARENT_REPARSE_POINT' }
    $root = Join-Path $Parent $Name
    if (Test-Path -LiteralPath $root) { throw 'ARTIFACT_COLLISION' }
    New-Item -ItemType Directory -Path $root | Out-Null
    [IO.File]::WriteAllText((Join-Path $root 'owner.json'), "{`"owner`":`"$Owner`"}", [Text.UTF8Encoding]::new($false))
    return $root
}

function Remove-OwnedRoot {
    param([string]$Path, [string]$Parent, [string]$Owner)
    if (-not (Test-Path -LiteralPath $Path -PathType Container)) { return }
    $fullPath = (Resolve-Path -LiteralPath $Path).Path
    $fullParent = (Resolve-Path -LiteralPath $Parent).Path
    $marker = Join-Path $fullPath 'owner.json'
    $expectedMarker = "{`"owner`":`"$Owner`"}"
    if ((Split-Path $fullPath -Parent) -cne $fullParent -or
        -not (Test-Path -LiteralPath $marker -PathType Leaf) -or
        [IO.File]::ReadAllText($marker) -cne $expectedMarker -or
        ((Get-Item -LiteralPath $fullPath).Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw 'OWNED_ROOT_CLEANUP_REFUSED'
    }
    Remove-GeneratedDirectory -Path $fullPath -Parent $fullParent -Label 'Owned build root'
}

function Write-JsonNoBom {
    param($Value, [string]$Path, [int]$Depth = 10)
    [IO.File]::WriteAllText($Path, ($Value | ConvertTo-Json -Depth $Depth), [Text.UTF8Encoding]::new($false))
}

function New-Gate {
    param([string]$Name, [string]$Command, [string]$Evidence)
    return [ordered]@{ name = $Name; status = 'passed'; command = $Command; exit_code = 0; evidence = $Evidence }
}

$qaParent = Join-Path ([Environment]::GetFolderPath('UserProfile')) 'IZ-CNA-QA'
$invocationId = [Guid]::NewGuid().ToString('N').Substring(0, 12)
$buildQaRoot = $null
$stageOwnerRoot = $null
$published = $false

try {
    Set-Location $RootDir
    Assert-ReleaseMetadata
    if (($SkipTests -or $SkipFrontendBuild) -and -not $ValidationOnly) {
        throw 'Client-ready builds reject -SkipTests and -SkipFrontendBuild. Use -ValidationOnly for a non-release diagnostic run.'
    }
    New-Item -ItemType Directory -Path $ReleaseRoot -Force | Out-Null
    $legacyArchives = @(Assert-PreservedArchives)
    $legacyProgramInventory = New-LegacyProgramInventory -Archives $legacyArchives
    $sourceRevision = (& git -C $RootDir rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0 -or $sourceRevision -notmatch '^[0-9a-f]{40}$') { throw 'malformed_repository_head' }
    if (-not $ValidationOnly) {
        Assert-IzArtifactPathsAvailable -Paths @($FinalPackageDir, $FinalZipPath, $FinalReceiptPath, $FinalGateEvidencePath)
        Assert-CleanSourceRevision -ExpectedHead $sourceRevision
    }

    $buildQaRoot = New-OwnedRoot -Parent $qaParent -Name "build-$invocationId" -Owner 'iz-cna-windows-build-v1'
    $logRoot = Join-Path $buildQaRoot 'logs'
    New-Item -ItemType Directory -Path $logRoot | Out-Null
    $preflightLog = Join-Path $logRoot 'preflight.log'
    $backendEnvironmentLog = Join-Path $logRoot 'backend-environment.log'
    $backendTestsLog = Join-Path $logRoot 'backend-tests.log'
    $frontendTestsLog = Join-Path $logRoot 'frontend-tests.log'
    $frontendBuildLog = Join-Path $logRoot 'frontend-build.log'
    $runtimeBuildLog = Join-Path $logRoot 'runtime-build.log'
    $frozenInspectionLog = Join-Path $logRoot 'frozen-bundle-inspection.log'

    Write-Build "IZ Clinical Notes Analyzer $Version build $Build installer revision $InstallerRevision"
    Write-Step 'Running Windows preflight in an isolated QA profile...'
    Invoke-InBuildQaEnvironment -QaRoot (Join-Path $buildQaRoot 'preflight-profile') -Action {
        $null = Invoke-LoggedCommand -Command {
            & (Join-Path $RootDir 'scripts\preflight-windows.ps1') -AssumeYes -SkipFrontendCheck -ReportPath (Join-Path $buildQaRoot 'preflight-report.json')
        } -FailureMessage 'Windows preflight failed.' -LogPath $preflightLog
    }

    Ensure-BackendBuildEnvironment -LogPath $backendEnvironmentLog
    $backendObservation = Invoke-BackendTests -LogPath $backendTestsLog -QaRoot (Join-Path $buildQaRoot 'backend-test-profile')
    $frontendObservation = Invoke-FrontendBuild -TestLogPath $frontendTestsLog -BuildLogPath $frontendBuildLog
    if ($ValidationOnly) {
        $repositorySafetyObservation = [ordered]@{ status = 'not_release_ready'; source_revision = $sourceRevision }
    } else {
        Assert-NoForbiddenRepositoryIndexItems -RepositoryRoot $RootDir -ExpectedHead $sourceRevision
        Assert-CleanSourceRevision -ExpectedHead $sourceRevision
        $repositorySafetyObservation = [ordered]@{ status = 'passed'; source_revision = $sourceRevision }
    }

    if ($ValidationOnly) {
        $stageOwnerRoot = $buildQaRoot
        $PackageDir = Join-Path $stageOwnerRoot "$PackageName.NOT-RELEASE-READY"
        $ZipPath = Join-Path $stageOwnerRoot "$PackageName.NOT-RELEASE-READY.zip"
    } else {
        $stageOwnerRoot = New-OwnedRoot -Parent $ReleaseRoot -Name ".stage-$invocationId" -Owner 'iz-cna-release-stage-v1'
        $PackageDir = Join-Path $stageOwnerRoot 'package'
        $ZipPath = Join-Path $stageOwnerRoot 'candidate.zip'
    }
    $AppDir = Join-Path $PackageDir 'app'
    New-Item -ItemType Directory -Path $AppDir -Force | Out-Null
    Copy-RepoContent -Destination $AppDir
    Copy-ApplicationMaintenanceHelpers -TargetAppDirectory $AppDir
    $runtimePath = Build-DesktopRuntime -TargetPackageDir $PackageDir -LogPath $runtimeBuildLog
    $null = Write-InstallerFiles -TargetPackageDir $PackageDir -LegacyProgramInventory $legacyProgramInventory
    $manifest = Write-IzReleaseManifest -PackageRoot $PackageDir -Version $Version -Build $Build -InstallerRevision $InstallerRevision -ReleaseChannel $ReleaseChannel
    Assert-ReleaseRequiredItems -TargetPackageDir $PackageDir
    Assert-NoForbiddenReleaseItems -TargetPackageDir $PackageDir
    $null = Assert-IzReleaseManifest -PackageRoot $PackageDir
    $frozenObservation = Inspect-FrozenBundle -RuntimePath $runtimePath -LogPath $frozenInspectionLog

    Add-Type -AssemblyName System.IO.Compression.FileSystem
    [System.AppContext]::SetSwitch('Switch.System.IO.Compression.ZipFile.UseBackslash', $false)
    [System.IO.Compression.ZipFile]::CreateFromDirectory(
        ('\\?\' + ($PackageDir -replace '^\\\\', 'UNC\')),
        ('\\?\' + ($ZipPath -replace '^\\\\', 'UNC\'))
    )
    Assert-ZipHasNoForbiddenItems -ZipPath $ZipPath
    Assert-ZipMatchesManifest -ZipPath $ZipPath -PackageDir $PackageDir

    $gateEvidenceName = "$PackageName.build-gates.json"
    $gateObservations = [ordered]@{
        schema = 'iz-cna-build-gate-evidence-v1'
        product_id = $ProductId
        version = $Version
        build = $Build
        installer_revision = $InstallerRevision
        source_revision = $sourceRevision
        release_ready = -not $ValidationOnly
        preflight = [ordered]@{ log_length = (Get-Item $preflightLog).Length; log_sha256 = Get-IzFileSha256 $preflightLog }
        backend_tests = $backendObservation
        frontend_tests = $frontendObservation.tests
        frontend_build = $frontendObservation.build
        repository_safety = $repositorySafetyObservation
        directory_safety = [ordered]@{ status = 'passed'; file_count = @($manifest.files).Count; payload_identity = $manifest.payload_identity }
        zip_safety = [ordered]@{ status = 'passed'; length = (Get-Item $ZipPath).Length; sha256 = Get-IzFileSha256 $ZipPath }
        frozen_bundle_inspection = $frozenObservation
        preserved_archives = [ordered]@{
            beta3_sha256 = '9c5fd47203242e1a21df612f719f1c14fa4240c86ba869f924ec4690834fc89c'
            beta4_sha256 = '67b83eea402566658dea6d64ac6cba37a192a7d1bd670cf560541324c0092b14'
        }
    }

    if ($ValidationOnly) {
        $validationSummaryPath = Join-Path $buildQaRoot 'validation-summary.NOT-RELEASE-READY.json'
        Write-JsonNoBom -Value $gateObservations -Path $validationSummaryPath
        Write-Warn 'Validation-only artifact is not release-ready and has no build receipt.'
        Write-Host "VALIDATION_DIRECTORY=$PackageDir"
        Write-Host "VALIDATION_ZIP=$ZipPath"
        Write-Host "VALIDATION_SUMMARY=$validationSummaryPath"
        $published = $true
        exit 0
    }

    if ($backendObservation.status -cne 'passed' -or $frontendObservation.tests.status -cne 'passed' -or $frontendObservation.build.status -cne 'passed') {
        throw 'Client-ready build gate was skipped.'
    }
    Assert-CleanSourceRevision -ExpectedHead $sourceRevision
    Assert-PreservedArchives
    Assert-IzArtifactPathsAvailable -Paths @($FinalPackageDir, $FinalZipPath, $FinalReceiptPath, $FinalGateEvidencePath)
    $stagedGateEvidencePath = Join-Path $stageOwnerRoot 'build-gates.json'
    Write-JsonNoBom -Value $gateObservations -Path $stagedGateEvidencePath
    Move-Item -LiteralPath $PackageDir -Destination $FinalPackageDir
    Move-Item -LiteralPath $ZipPath -Destination $FinalZipPath
    Move-Item -LiteralPath $stagedGateEvidencePath -Destination $FinalGateEvidencePath
    $gates = @(
        New-Gate -Name 'backend_tests' -Command 'backend/.venv/Scripts/python.exe -m pytest backend/tests -q' -Evidence $gateEvidenceName
        New-Gate -Name 'frontend_tests' -Command 'npm run test -- --run' -Evidence $gateEvidenceName
        New-Gate -Name 'frontend_build' -Command 'npm run build' -Evidence $gateEvidenceName
        New-Gate -Name 'repository_safety' -Command 'git status and release-safety repository scan' -Evidence $gateEvidenceName
        New-Gate -Name 'directory_safety' -Command 'release manifest and directory safety validation' -Evidence $gateEvidenceName
        New-Gate -Name 'zip_safety' -Command 'ZIP inventory/hash and release safety validation' -Evidence $gateEvidenceName
        New-Gate -Name 'frozen_bundle_inspection' -Command 'PyInstaller archive recursive member inspection' -Evidence $gateEvidenceName
    )
    $null = Write-IzBuildReceipt `
        -ReceiptPath $FinalReceiptPath -ProductId $ProductId -Version $Version -Build $Build `
        -InstallerRevision $InstallerRevision -SourceRevision $sourceRevision `
        -PackageDirectory $FinalPackageDir -ZipPath $FinalZipPath `
        -ManifestPath (Join-Path $FinalPackageDir 'release-manifest.json') `
        -PayloadIdentity $manifest.payload_identity -Gates $gates
    @"
Release folder: $FinalPackageDir
Release zip: $FinalZipPath
Build receipt: $FinalReceiptPath
"@ | Set-Content -LiteralPath $LatestPathsFile -Encoding ASCII
    Write-Host "BUILD_RECEIPT_PATH=$FinalReceiptPath"
    if ($env:GITHUB_OUTPUT) {
        [IO.File]::AppendAllText($env:GITHUB_OUTPUT, "build_receipt_path=$FinalReceiptPath`n", [Text.UTF8Encoding]::new($false))
    }
    Write-Ok "Release package ready: $FinalPackageDir"
    Write-Ok "Release zip ready: $FinalZipPath"
    $published = $true
    exit 0
} catch {
    Write-Host ''
    Write-Fail 'Windows release build failed.'
    Write-Host $_.Exception.Message
    exit 1
} finally {
    if (-not $ValidationOnly -and $stageOwnerRoot -and (Test-Path -LiteralPath $stageOwnerRoot)) {
        Remove-OwnedRoot -Path $stageOwnerRoot -Parent $ReleaseRoot -Owner 'iz-cna-release-stage-v1'
    }
    if (-not $ValidationOnly -and $buildQaRoot -and (Test-Path -LiteralPath $buildQaRoot)) {
        Remove-OwnedRoot -Path $buildQaRoot -Parent $qaParent -Owner 'iz-cna-windows-build-v1'
    }
}
