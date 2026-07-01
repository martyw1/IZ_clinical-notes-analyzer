[CmdletBinding()]
param(
    [switch]$SkipTests,
    [switch]$SkipFrontendBuild
)

$ErrorActionPreference = 'Stop'
$RootDir = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$Version = (Get-Content -LiteralPath (Join-Path $RootDir 'VERSION') -Raw).Trim()
$ReleaseRoot = Join-Path $RootDir 'dist\windows-release'
$PackageName = "IZ-Clinical-Notes-Analyzer-v$Version"
$PackageDir = Join-Path $ReleaseRoot $PackageName
$AppDir = Join-Path $PackageDir 'app'
$VenvDir = Join-Path $RootDir 'backend\.venv'
$VenvPython = Join-Path $VenvDir 'Scripts\python.exe'
$LatestPathsFile = Join-Path $ReleaseRoot 'latest-release-paths.txt'

function Write-Step($Message) {
    Write-Host "[setup] $Message"
}

function Write-Build($Message) {
    Write-Host "[build] $Message"
}

function Write-Ok($Message) {
    Write-Host "[ok] $Message" -ForegroundColor Green
}

function Write-Warn($Message) {
    Write-Host "[warn] $Message" -ForegroundColor Yellow
}

function Write-Fail($Message) {
    Write-Host "[fail] $Message" -ForegroundColor Red
}

function Get-NormalizedPath {
    param([string]$Path)
    $trimChars = [char[]]@([System.IO.Path]::DirectorySeparatorChar, [System.IO.Path]::AltDirectorySeparatorChar)
    return [System.IO.Path]::GetFullPath($Path).TrimEnd($trimChars)
}

function Assert-PathInside {
    param(
        [string]$Path,
        [string]$Parent,
        [string]$Label
    )
    $normalizedPath = Get-NormalizedPath -Path $Path
    $normalizedParent = Get-NormalizedPath -Path $Parent
    $comparison = [System.StringComparison]::OrdinalIgnoreCase
    $separator = [System.IO.Path]::DirectorySeparatorChar
    if (-not $normalizedPath.StartsWith("$normalizedParent$separator", $comparison)) {
        throw "$Label must be inside $normalizedParent; resolved to $normalizedPath"
    }
}

function Get-RelativePathInside {
    param(
        [string]$Path,
        [string]$Parent
    )
    $normalizedPath = Get-NormalizedPath -Path $Path
    $normalizedParent = Get-NormalizedPath -Path $Parent
    $separator = [System.IO.Path]::DirectorySeparatorChar
    $comparison = [System.StringComparison]::OrdinalIgnoreCase
    if (-not $normalizedPath.StartsWith("$normalizedParent$separator", $comparison)) {
        throw "Path $normalizedPath is not inside $normalizedParent"
    }
    return $normalizedPath.Substring($normalizedParent.Length + 1)
}

function Remove-GeneratedDirectory {
    param(
        [string]$Path,
        [string]$Parent,
        [string]$Label
    )
    Assert-PathInside -Path $Path -Parent $Parent -Label $Label
    if (-not (Test-Path -LiteralPath $Path)) { return }

    $emptyDir = Join-Path ([System.IO.Path]::GetTempPath()) "iz-cna-empty-$([System.Guid]::NewGuid().ToString('N'))"
    New-Item -ItemType Directory -Path $emptyDir -Force | Out-Null
    try {
        robocopy $emptyDir $Path /MIR /NFL /NDL /NJH /NJS /NP | Out-Null
        if ($LASTEXITCODE -gt 7) { throw "cleanup mirror failed with robocopy exit code $LASTEXITCODE" }
    } finally {
        Remove-Item -LiteralPath $emptyDir -Recurse -Force -ErrorAction SilentlyContinue
    }

    Remove-Item -LiteralPath $Path -Recurse -Force
}

function Copy-RepoContent {
    param([string]$Destination)
    $excludeDirs = @(
        (Join-Path $RootDir '.git'),
        (Join-Path $RootDir '.codegraph'),
        (Join-Path $RootDir '.omo'),
        (Join-Path $RootDir '.codex'),
        (Join-Path $RootDir '.github'),
        (Join-Path $RootDir '.venv'),
        (Join-Path $RootDir 'backend\.venv'),
        (Join-Path $RootDir 'frontend\node_modules'),
        (Join-Path $RootDir 'node_modules'),
        (Join-Path $RootDir 'dist'),
        (Join-Path $RootDir 'uploads'),
        (Join-Path $RootDir 'exports'),
        (Join-Path $RootDir 'logs'),
        (Join-Path $RootDir 'api-connectivity-reports'),
        (Join-Path $RootDir 'alleva-api-test-logs'),
        (Join-Path $RootDir '.pytest_cache'),
        (Join-Path $RootDir '.mypy_cache'),
        (Join-Path $RootDir '.ruff_cache'),
        (Join-Path $RootDir 'htmlcov'),
        (Join-Path $RootDir 'coverage'),
        (Join-Path $RootDir 'frontend\coverage'),
        (Join-Path $RootDir 'depricated'),
        (Join-Path $RootDir 'deprecated'),
        (Join-Path $RootDir 'depriceated'),
        (Join-Path $RootDir 'walkthroughs (2026-03-04)'),
        (Join-Path $RootDir 'video-extract (2026-06-05)'),
        (Join-Path $RootDir 'example-treatment-plans'),
        '__pycache__',
        '.codegraph',
        '.omo',
        '.codex',
        '.github',
        'node_modules',
        '.pytest_cache',
        '.mypy_cache',
        '.ruff_cache',
        'htmlcov',
        'logs',
        'uploads',
        'exports',
        'api-connectivity-reports',
        'alleva-api-test-logs'
    )
    $excludeFiles = @(
        '.env',
        '.env.*',
        '.alleva.local.ps1',
        'App Credentials Info.md',
        'Test-AllevaApi.ps1',
        '*credential*',
        '*secret*',
        '*token*',
        '*.sqlite',
        '*.sqlite3',
        '*.db',
        '*.log',
        '*.tmp',
        '*.bak',
        '*.pyc'
    )
    robocopy $RootDir $Destination /MIR /XD $excludeDirs /XF $excludeFiles /NFL /NDL /NJH /NJS /NP | Out-Null
    if ($LASTEXITCODE -gt 7) { throw "robocopy failed with exit code $LASTEXITCODE" }
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
    $commands = @(
        (Get-Command npm.cmd -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -ErrorAction SilentlyContinue),
        (Get-Command npm.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -ErrorAction SilentlyContinue)
    ) | Where-Object { $_ -and (Test-Path -LiteralPath $_) }
    if ($commands.Count -gt 0) { return $commands | Select-Object -First 1 }

    $wingetPackageRoot = Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Packages'
    if (Test-Path -LiteralPath $wingetPackageRoot) {
        $wingetNpm = Get-ChildItem -Path $wingetPackageRoot -Recurse -Filter npm.cmd -ErrorAction SilentlyContinue |
            Select-Object -First 1 -ExpandProperty FullName
        if ($wingetNpm -and (Test-Path -LiteralPath $wingetNpm)) { return $wingetNpm }
    }
    return $null
}

function Invoke-CheckedCommand {
    param(
        [scriptblock]$Command,
        [string]$FailureMessage
    )
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$FailureMessage Exit code: $LASTEXITCODE."
    }
}

function Ensure-BackendBuildEnvironment {
    $runtimeRequirements = Join-Path $RootDir 'backend\requirements-windows-local.txt'
    if (-not (Test-Path -LiteralPath $runtimeRequirements)) {
        $runtimeRequirements = Join-Path $RootDir 'backend\requirements.txt'
    }
    $buildRequirements = Join-Path $RootDir 'backend\requirements-build.txt'
    if (-not (Test-Path -LiteralPath $runtimeRequirements)) {
        throw "Backend runtime requirements file was not found. Expected backend\requirements-windows-local.txt or backend\requirements.txt."
    }
    if (-not (Test-Path -LiteralPath $buildRequirements)) {
        throw "Backend build/test requirements file was not found at backend\requirements-build.txt."
    }

    if (-not (Test-Path -LiteralPath $VenvPython)) {
        $python = Find-Python
        if (-not $python) {
            throw "Python 3.11 or newer was not found. Install Python 3.12 from https://www.python.org/downloads/windows/ and check 'Add python.exe to PATH', then double-click Build-IZ-Windows-Installer.cmd again."
        }
        Write-Step 'Creating backend environment...'
        Invoke-CheckedCommand -Command { & $python -m venv $VenvDir } -FailureMessage 'Could not create backend\.venv.'
    }

    Write-Step 'Installing backend runtime packages...'
    Invoke-CheckedCommand -Command { & $VenvPython -m pip install -r $runtimeRequirements } -FailureMessage 'Backend runtime dependency installation failed.'

    Write-Step 'Installing backend test packages...'
    Invoke-CheckedCommand -Command { & $VenvPython -m pip install -r $buildRequirements } -FailureMessage 'Backend test dependency installation failed.'

    Write-Step 'Verifying pytest is available...'
    Invoke-CheckedCommand -Command { & $VenvPython -m pytest --version } -FailureMessage 'pytest is still unavailable after installing backend test packages.'
    Write-Ok 'Backend test runner is available.'
}

function Invoke-BackendTests {
    if ($SkipTests) {
        Write-Warn 'Backend tests skipped because -SkipTests was provided.'
        return
    }
    Write-Step 'Running backend tests...'
    $env:PYTHONPATH = Join-Path $RootDir 'backend'
    Invoke-CheckedCommand -Command { & $VenvPython -m pytest (Join-Path $RootDir 'backend\tests') -q } -FailureMessage 'Backend tests failed.'
    Write-Ok 'Backend tests passed.'
}

function Assert-FrontendDist {
    $distDir = Join-Path $RootDir 'frontend\dist'
    $indexFile = Join-Path $distDir 'index.html'
    $assetsDir = Join-Path $distDir 'assets'
    if (-not (Test-Path -LiteralPath $indexFile)) {
        throw "The browser app build is missing frontend\dist\index.html. Install Node.js LTS and rerun the build."
    }
    if (-not (Test-Path -LiteralPath $assetsDir)) {
        throw "The browser app build is missing frontend\dist\assets. Run the normal build without -SkipFrontendBuild."
    }
    $assetFiles = @(Get-ChildItem -LiteralPath $assetsDir -Recurse -File -ErrorAction SilentlyContinue)
    $jsAssets = @($assetFiles | Where-Object { $_.Extension -eq '.js' -and $_.Length -gt 0 })
    $cssAssets = @($assetFiles | Where-Object { $_.Extension -eq '.css' -and $_.Length -gt 0 })
    if ($jsAssets.Count -eq 0) {
        throw "The browser app build does not contain a JavaScript asset under frontend\dist\assets."
    }
    if ($cssAssets.Count -eq 0) {
        throw "The browser app build does not contain a CSS asset under frontend\dist\assets."
    }
    $indexText = Get-Content -LiteralPath $indexFile -Raw
    if ($indexText -notmatch '/assets/.+\.js') {
        throw "frontend\dist\index.html does not reference a built JavaScript asset."
    }
}

function Invoke-FrontendBuild {
    if ($SkipFrontendBuild) {
        Write-Step 'Checking existing browser app build...'
        Assert-FrontendDist
        Write-Ok 'Existing frontend build is valid.'
        return
    }

    $npm = Find-Npm
    if (-not $npm) {
        throw "Node.js/npm was not found. Install Node.js LTS for Windows, then double-click Build-IZ-Windows-Installer.cmd again. Suggested command for advanced users: winget install OpenJS.NodeJS.LTS --scope user --accept-package-agreements --accept-source-agreements"
    }

    $env:PATH = "$(Split-Path $npm -Parent);$env:PATH"
    Push-Location (Join-Path $RootDir 'frontend')
    try {
        if (Test-Path -LiteralPath (Join-Path $RootDir 'frontend\package-lock.json')) {
            Write-Step 'Installing frontend dependencies with npm ci...'
            Invoke-CheckedCommand -Command { & $npm ci } -FailureMessage 'npm ci failed while installing frontend dependencies.'
        } else {
            Write-Step 'Installing frontend dependencies with npm install...'
            Invoke-CheckedCommand -Command { & $npm install } -FailureMessage 'npm install failed while installing frontend dependencies.'
        }

        if ($SkipTests) {
            Write-Warn 'Frontend tests skipped because -SkipTests was provided.'
        } else {
            Write-Step 'Running frontend tests...'
            Invoke-CheckedCommand -Command { & $npm run test -- --run } -FailureMessage 'Frontend tests failed.'
            Write-Ok 'Frontend tests passed.'
        }

        Write-Step 'Building browser app...'
        Invoke-CheckedCommand -Command { & $npm run build } -FailureMessage 'Frontend build failed.'
    } finally {
        Pop-Location
    }
    Assert-FrontendDist
    Write-Ok 'Frontend build complete.'
}

function Assert-RelativePathAllowed {
    param(
        [string]$RelativePath,
        [string]$Source
    )
    $relative = ($RelativePath -replace '/', '\').Trim('\')
    if (-not $relative) { return }
    $lower = $relative.ToLowerInvariant()
    $parts = @($lower.Split([char[]]@('\', '/'), [System.StringSplitOptions]::RemoveEmptyEntries))
    $fileName = [System.IO.Path]::GetFileName($lower)
    $forbiddenDirs = @(
        '.git',
        '.codegraph',
        '.omo',
        '.codex',
        '.github',
        '.venv',
        'node_modules',
        '.pytest_cache',
        '.mypy_cache',
        '.ruff_cache',
        'htmlcov',
        'coverage',
        'logs',
        'uploads',
        'exports',
        'api-connectivity-reports',
        'alleva-api-test-logs',
        'example-treatment-plans',
        '__pycache__'
    )
    foreach ($part in $parts) {
        if ($forbiddenDirs -contains $part) {
            throw "$Source contains forbidden folder '$part' at $relative."
        }
    }
    if ($lower -match '(^|\\)backend\\\.venv($|\\)') {
        throw "$Source contains backend\.venv at $relative."
    }
    if (
        $fileName -eq '.env' -or
        $fileName.StartsWith('.env.') -or
        $fileName -eq '.alleva.local.ps1' -or
        $fileName -eq 'app credentials info.md' -or
        $fileName -eq 'test-allevaapi.ps1' -or
        $fileName -like '*credential*' -or
        $fileName -like '*secret*' -or
        $fileName -like '*token*' -or
        $fileName -like '*.sqlite' -or
        $fileName -like '*.sqlite3' -or
        $fileName -like '*.db' -or
        $fileName -like '*.log' -or
        $fileName -like '*.tmp' -or
        $fileName -like '*.bak' -or
        $fileName -like '*.pyc'
    ) {
        throw "$Source contains forbidden file at $relative."
    }
}

function Assert-NoForbiddenReleaseItems {
    param([string]$TargetPackageDir)
    $items = Get-ChildItem -LiteralPath $TargetPackageDir -Recurse -Force -ErrorAction SilentlyContinue
    foreach ($item in $items) {
        $relative = Get-RelativePathInside -Path $item.FullName -Parent $TargetPackageDir
        Assert-RelativePathAllowed -RelativePath $relative -Source 'Release package'
    }
    Write-Ok 'Release package forbidden-file scan passed.'
}

function Assert-ReleaseRequiredItems {
    param([string]$TargetPackageDir)
    $requiredItems = @(
        'app\backend',
        'app\frontend',
        'app\frontend\dist',
        'app\frontend\dist\index.html',
        'app\docs\patient-treatment-plan-handling.md',
        'app\scripts',
        'Install-IZ-Clinical-Notes-Analyzer.cmd',
        'Launch-IZ-Clinical-Notes-Analyzer.cmd',
        'Stop-IZ-Clinical-Notes-Analyzer.cmd',
        'Collect-IZ-Clinical-Notes-Analyzer-Diagnostics.cmd',
        'Backup-IZ-Clinical-Notes-Analyzer.cmd',
        'Uninstall-IZ-Clinical-Notes-Analyzer.cmd',
        'Complete-Uninstall-IZ-Clinical-Notes-Analyzer.cmd',
        'release-manifest.json'
    )
    foreach ($item in $requiredItems) {
        $path = Join-Path $TargetPackageDir $item
        if (-not (Test-Path -LiteralPath $path)) {
            throw "Release package is missing required item: $item"
        }
    }
    Write-Ok 'Release package required-file validation passed.'
}

function Assert-ZipHasNoForbiddenItems {
    param([string]$ZipPath)
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip = [System.IO.Compression.ZipFile]::OpenRead($ZipPath)
    try {
        foreach ($entry in $zip.Entries) {
            Assert-RelativePathAllowed -RelativePath $entry.FullName -Source 'Release zip'
        }
    } finally {
        $zip.Dispose()
    }
    Write-Ok 'Release zip forbidden-file scan passed.'
}

function Write-InstallerFiles {
    param([string]$TargetPackageDir)
    $installCmd = Join-Path $TargetPackageDir 'Install-IZ-Clinical-Notes-Analyzer.cmd'
    $launchCmd = Join-Path $TargetPackageDir 'Launch-IZ-Clinical-Notes-Analyzer.cmd'
    $stopCmd = Join-Path $TargetPackageDir 'Stop-IZ-Clinical-Notes-Analyzer.cmd'
    $diagnosticsCmd = Join-Path $TargetPackageDir 'Collect-IZ-Clinical-Notes-Analyzer-Diagnostics.cmd'
    $backupCmd = Join-Path $TargetPackageDir 'Backup-IZ-Clinical-Notes-Analyzer.cmd'
    $uninstallCmd = Join-Path $TargetPackageDir 'Uninstall-IZ-Clinical-Notes-Analyzer.cmd'
    $completeUninstallCmd = Join-Path $TargetPackageDir 'Complete-Uninstall-IZ-Clinical-Notes-Analyzer.cmd'

@"
@echo off
setlocal
set "PACKAGE_DIR=%~dp0"
cd /d "%PACKAGE_DIR%"
title Install IZ Clinical Notes Analyzer
echo IZ Clinical Notes Analyzer installer
echo.
echo This installs the app for the current Windows user. Administrator access is not required.
echo Existing local data under %%LOCALAPPDATA%%\IZ Clinical Notes Analyzer will be preserved.
echo Current treatment-plan handling docs are included under app\docs.
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%PACKAGE_DIR%installer\install-windows-release.ps1" %*
set "EXIT_CODE=%ERRORLEVEL%"
echo.
if "%EXIT_CODE%"=="0" (
    echo [ok] Install completed.
    echo Launch from the Start Menu, Desktop shortcut, or Launch-IZ-Clinical-Notes-Analyzer.cmd.
) else (
    echo [fail] Install did not complete.
    echo Review the message above or send a screenshot of this window to R3 support.
)
echo.
pause
exit /b %EXIT_CODE%
"@ | Set-Content -Path $installCmd -Encoding ASCII

@"
@echo off
setlocal
set "PACKAGE_DIR=%~dp0"
set "NO_PAUSE="
for %%A in (%*) do (
    if /I "%%~A"=="-NoPause" set "NO_PAUSE=1"
    if /I "%%~A"=="/NoPause" set "NO_PAUSE=1"
)
cd /d "%PACKAGE_DIR%"
title IZ Clinical Notes Analyzer
echo Starting IZ Clinical Notes Analyzer...
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%PACKAGE_DIR%app\scripts\start-windows-local.ps1" -AssumeYes %*
set "EXIT_CODE=%ERRORLEVEL%"
if not "%EXIT_CODE%"=="0" (
    echo.
    echo [fail] The app did not start.
    echo Review the startup log under %%LOCALAPPDATA%%\IZ Clinical Notes Analyzer\logs.
    echo Send a screenshot of this window to R3 support if the message is unclear.
    echo.
    if not "%NO_PAUSE%"=="1" pause
)
exit /b %EXIT_CODE%
"@ | Set-Content -Path $launchCmd -Encoding ASCII

@"
@echo off
setlocal
set "PACKAGE_DIR=%~dp0"
set "NO_PAUSE="
for %%A in (%*) do (
    if /I "%%~A"=="-NoPause" set "NO_PAUSE=1"
    if /I "%%~A"=="/NoPause" set "NO_PAUSE=1"
)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%PACKAGE_DIR%app\scripts\stop-windows-local.ps1" %*
set "EXIT_CODE=%ERRORLEVEL%"
if not "%EXIT_CODE%"=="0" if not "%NO_PAUSE%"=="1" pause
exit /b %EXIT_CODE%
"@ | Set-Content -Path $stopCmd -Encoding ASCII

@"
@echo off
setlocal
set "PACKAGE_DIR=%~dp0"
set "NO_PAUSE="
for %%A in (%*) do (
    if /I "%%~A"=="-NoPause" set "NO_PAUSE=1"
    if /I "%%~A"=="/NoPause" set "NO_PAUSE=1"
)
title IZ Clinical Notes Analyzer Diagnostics
echo Collecting IZ Clinical Notes Analyzer diagnostics...
echo This does not include uploaded clinical documents, raw .env secrets, or SQLite databases.
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%PACKAGE_DIR%app\scripts\collect-diagnostics.ps1" %*
set "EXIT_CODE=%ERRORLEVEL%"
echo.
if "%EXIT_CODE%"=="0" (
    echo [ok] Diagnostics collection finished.
) else (
    echo [fail] Diagnostics collection did not complete.
)
echo.
if not "%NO_PAUSE%"=="1" pause
exit /b %EXIT_CODE%
"@ | Set-Content -Path $diagnosticsCmd -Encoding ASCII

@"
@echo off
setlocal
set "PACKAGE_DIR=%~dp0"
set "NO_PAUSE="
for %%A in (%*) do (
    if /I "%%~A"=="-NoPause" set "NO_PAUSE=1"
    if /I "%%~A"=="/NoPause" set "NO_PAUSE=1"
)
title Backup IZ Clinical Notes Analyzer
echo Backup IZ Clinical Notes Analyzer local data
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%PACKAGE_DIR%app\scripts\backup-local-data.ps1" %*
set "EXIT_CODE=%ERRORLEVEL%"
echo.
if "%EXIT_CODE%"=="0" (
    echo [ok] Backup command finished.
) else (
    echo [fail] Backup did not complete.
)
echo.
if not "%NO_PAUSE%"=="1" pause
exit /b %EXIT_CODE%
"@ | Set-Content -Path $backupCmd -Encoding ASCII

@"
@echo off
setlocal
set "PACKAGE_DIR=%~dp0"
set "NO_PAUSE="
for %%A in (%*) do (
    if /I "%%~A"=="-NoPause" set "NO_PAUSE=1"
    if /I "%%~A"=="/NoPause" set "NO_PAUSE=1"
)
title Uninstall IZ Clinical Notes Analyzer
echo Uninstall IZ Clinical Notes Analyzer app files
echo Local data under %%LOCALAPPDATA%%\IZ Clinical Notes Analyzer will be preserved.
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%PACKAGE_DIR%installer\uninstall-windows-release.ps1" %*
set "EXIT_CODE=%ERRORLEVEL%"
echo.
if "%EXIT_CODE%"=="0" (
    echo [ok] Uninstall completed. Local data was preserved.
) else (
    echo [fail] Uninstall did not complete.
)
echo.
if not "%NO_PAUSE%"=="1" pause
exit /b %EXIT_CODE%
"@ | Set-Content -Path $uninstallCmd -Encoding ASCII

@"
@echo off
setlocal
set "PACKAGE_DIR=%~dp0"
set "NO_PAUSE="
for %%A in (%*) do (
    if /I "%%~A"=="-NoPause" set "NO_PAUSE=1"
    if /I "%%~A"=="/NoPause" set "NO_PAUSE=1"
)
title Complete Uninstall IZ Clinical Notes Analyzer
echo Complete uninstall removes app files AND local IZ Clinical Notes Analyzer data.
echo Use this only when R3 intentionally wants this Windows user account cleaned.
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%PACKAGE_DIR%app\scripts\complete-uninstall-local-data.ps1" %*
set "EXIT_CODE=%ERRORLEVEL%"
echo.
if "%EXIT_CODE%"=="0" (
    echo [ok] Complete uninstall finished.
) else (
    echo [fail] Complete uninstall did not complete.
)
echo.
if not "%NO_PAUSE%"=="1" pause
exit /b %EXIT_CODE%
"@ | Set-Content -Path $completeUninstallCmd -Encoding ASCII

    $installerDir = Join-Path $TargetPackageDir 'installer'
    New-Item -ItemType Directory -Path $installerDir -Force | Out-Null

@'
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$PackageDir = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$SourceAppDir = Join-Path $PackageDir 'app'
$InstallRoot = Join-Path $env:LOCALAPPDATA 'Programs\IZ Clinical Notes Analyzer'
$StartMenuDir = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\IZ Clinical Notes Analyzer'
$DesktopDir = [Environment]::GetFolderPath('Desktop')
$Launcher = Join-Path $InstallRoot 'scripts\Start-IZ-Clinical-Notes-Analyzer.cmd'
$StopLauncher = Join-Path $InstallRoot 'scripts\Stop-IZ-Clinical-Notes-Analyzer.cmd'
$DiagnosticsLauncher = Join-Path $InstallRoot 'scripts\Collect-IZ-Clinical-Notes-Analyzer-Diagnostics.cmd'
$BackupLauncher = Join-Path $InstallRoot 'scripts\Backup-IZ-Clinical-Notes-Analyzer.cmd'
$InstalledInstallerDir = Join-Path $InstallRoot 'installer'
$StartShortcut = Join-Path $StartMenuDir 'IZ Clinical Notes Analyzer.lnk'
$StopShortcut = Join-Path $StartMenuDir 'Stop IZ Clinical Notes Analyzer.lnk'
$DiagnosticsShortcut = Join-Path $StartMenuDir 'IZ Clinical Notes Analyzer Diagnostics.lnk'
$BackupShortcut = Join-Path $StartMenuDir 'Backup IZ Clinical Notes Analyzer.lnk'
$UninstallShortcut = Join-Path $StartMenuDir 'Uninstall IZ Clinical Notes Analyzer.lnk'
$CompleteUninstallShortcut = Join-Path $StartMenuDir 'Complete Uninstall IZ Clinical Notes Analyzer.lnk'
$DesktopStartShortcut = Join-Path $DesktopDir 'IZ Clinical Notes Analyzer.lnk'
$DesktopDiagnosticsShortcut = Join-Path $DesktopDir 'IZ Clinical Notes Analyzer Diagnostics.lnk'
$DesktopBackupShortcut = Join-Path $DesktopDir 'IZ Clinical Notes Analyzer Backup.lnk'
$Uninstaller = Join-Path $InstallRoot 'Uninstall-IZ-Clinical-Notes-Analyzer.cmd'
$CompleteUninstaller = Join-Path $InstallRoot 'Complete-Uninstall-IZ-Clinical-Notes-Analyzer.cmd'
$LocalDataDir = Join-Path $env:LOCALAPPDATA 'IZ Clinical Notes Analyzer'

function Write-InstallStep($Message) { Write-Host "[setup] $Message" }
function Write-InstallOk($Message) { Write-Host "[ok] $Message" -ForegroundColor Green }

function New-Shortcut {
    param(
        [string]$ShortcutPath,
        [string]$TargetPath,
        [string]$WorkingDirectory,
        [string]$IconLocation = ''
    )
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($ShortcutPath)
    $shortcut.TargetPath = $TargetPath
    $shortcut.WorkingDirectory = $WorkingDirectory
    $shortcut.IconLocation = if ($IconLocation) { $IconLocation } else { "$env:SystemRoot\System32\shell32.dll,220" }
    $shortcut.Save()
}

function Assert-RequiredPackageItem {
    param([string]$RelativePath)
    $path = Join-Path $PackageDir $RelativePath
    if (-not (Test-Path -LiteralPath $path)) {
        throw "This release package is incomplete. Missing: $RelativePath. Download or unzip the release package again."
    }
}

Assert-RequiredPackageItem 'app\backend'
Assert-RequiredPackageItem 'app\frontend\dist\index.html'
Assert-RequiredPackageItem 'app\scripts\preflight-windows.ps1'

Write-InstallStep "Installing app files to $InstallRoot"
New-Item -ItemType Directory -Path $InstallRoot, $StartMenuDir -Force | Out-Null
robocopy $SourceAppDir $InstallRoot /MIR /NFL /NDL /NJH /NJS /NP | Out-Null
if ($LASTEXITCODE -gt 7) { throw "Install copy failed with robocopy exit code $LASTEXITCODE" }
Copy-Item -LiteralPath (Join-Path $PackageDir 'release-manifest.json') -Destination (Join-Path $InstallRoot 'release-manifest.json') -Force
robocopy (Join-Path $PackageDir 'installer') $InstalledInstallerDir /MIR /NFL /NDL /NJH /NJS /NP | Out-Null
if ($LASTEXITCODE -gt 7) { throw "Installer helper copy failed with robocopy exit code $LASTEXITCODE" }

@"
@echo off
setlocal
set "NO_PAUSE="
for %%A in (%*) do (
    if /I "%%~A"=="-NoPause" set "NO_PAUSE=1"
    if /I "%%~A"=="/NoPause" set "NO_PAUSE=1"
)
title Uninstall IZ Clinical Notes Analyzer
echo Uninstall IZ Clinical Notes Analyzer app files
echo Local data under %%LOCALAPPDATA%%\IZ Clinical Notes Analyzer will be preserved.
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0installer\uninstall-windows-release.ps1" -InstalledAppRoot "%~dp0." %*
set "EXIT_CODE=%ERRORLEVEL%"
echo.
if "%EXIT_CODE%"=="0" (
    echo [ok] Uninstall completed. Local data was preserved.
) else (
    echo [fail] Uninstall did not complete.
)
echo.
if not "%NO_PAUSE%"=="1" pause
exit /b %EXIT_CODE%
"@ | Set-Content -Path $Uninstaller -Encoding ASCII

@"
@echo off
setlocal
set "NO_PAUSE="
for %%A in (%*) do (
    if /I "%%~A"=="-NoPause" set "NO_PAUSE=1"
    if /I "%%~A"=="/NoPause" set "NO_PAUSE=1"
)
title Complete Uninstall IZ Clinical Notes Analyzer
echo Complete uninstall removes app files AND local IZ Clinical Notes Analyzer data.
echo Use this only when R3 intentionally wants this Windows user account cleaned.
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\complete-uninstall-local-data.ps1" -InstalledAppRoot "%~dp0." %*
set "EXIT_CODE=%ERRORLEVEL%"
echo.
if "%EXIT_CODE%"=="0" (
    echo [ok] Complete uninstall finished.
) else (
    echo [fail] Complete uninstall did not complete.
)
echo.
if not "%NO_PAUSE%"=="1" pause
exit /b %EXIT_CODE%
"@ | Set-Content -Path $CompleteUninstaller -Encoding ASCII

Write-InstallStep 'Creating Start Menu and Desktop shortcuts'
New-Shortcut -ShortcutPath $StartShortcut -TargetPath $Launcher -WorkingDirectory $InstallRoot
New-Shortcut -ShortcutPath $StopShortcut -TargetPath $StopLauncher -WorkingDirectory $InstallRoot -IconLocation "$env:SystemRoot\System32\shell32.dll,27"
New-Shortcut -ShortcutPath $DiagnosticsShortcut -TargetPath $DiagnosticsLauncher -WorkingDirectory $InstallRoot -IconLocation "$env:SystemRoot\System32\shell32.dll,23"
New-Shortcut -ShortcutPath $BackupShortcut -TargetPath $BackupLauncher -WorkingDirectory $InstallRoot -IconLocation "$env:SystemRoot\System32\shell32.dll,258"
New-Shortcut -ShortcutPath $UninstallShortcut -TargetPath $Uninstaller -WorkingDirectory $InstallRoot
New-Shortcut -ShortcutPath $CompleteUninstallShortcut -TargetPath $CompleteUninstaller -WorkingDirectory $InstallRoot -IconLocation "$env:SystemRoot\System32\shell32.dll,131"
New-Shortcut -ShortcutPath $DesktopStartShortcut -TargetPath $Launcher -WorkingDirectory $InstallRoot
New-Shortcut -ShortcutPath $DesktopDiagnosticsShortcut -TargetPath $DiagnosticsLauncher -WorkingDirectory $InstallRoot -IconLocation "$env:SystemRoot\System32\shell32.dll,23"
New-Shortcut -ShortcutPath $DesktopBackupShortcut -TargetPath $BackupLauncher -WorkingDirectory $InstallRoot -IconLocation "$env:SystemRoot\System32\shell32.dll,258"

Write-InstallOk "Installed IZ Clinical Notes Analyzer to $InstallRoot"
Write-Host "Local data folder: $LocalDataDir"
Write-Host "Start Menu shortcut: $StartShortcut"
Write-InstallStep 'Running first-time preflight after install'
& (Join-Path $InstallRoot 'scripts\preflight-windows.ps1') -AssumeYes
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-InstallOk 'Install complete. Use the Start Menu shortcut or Desktop shortcut to launch the app.'
'@ | Set-Content -Path (Join-Path $installerDir 'install-windows-release.ps1') -Encoding UTF8

@'
[CmdletBinding()]
param(
    [string]$InstalledAppRoot = '',
    [switch]$NoPause,
    [int]$DelaySeconds = 0
)

$ErrorActionPreference = 'Stop'
if ($DelaySeconds -gt 0) {
    Start-Sleep -Seconds $DelaySeconds
}
$InstallRoot = if ($InstalledAppRoot) { $InstalledAppRoot } else { Join-Path $env:LOCALAPPDATA 'Programs\IZ Clinical Notes Analyzer' }
$ExpectedInstallRoot = Join-Path $env:LOCALAPPDATA 'Programs\IZ Clinical Notes Analyzer'
$StartMenuDir = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\IZ Clinical Notes Analyzer'
$DesktopDir = [Environment]::GetFolderPath('Desktop')
$DesktopShortcuts = @(
    'IZ Clinical Notes Analyzer.lnk',
    'IZ Clinical Notes Analyzer Diagnostics.lnk',
    'IZ Clinical Notes Analyzer Backup.lnk'
) | ForEach-Object { Join-Path $DesktopDir $_ }

function Get-NormalizedPath {
    param([string]$Path)
    $trimChars = [char[]]@([System.IO.Path]::DirectorySeparatorChar, [System.IO.Path]::AltDirectorySeparatorChar)
    return [System.IO.Path]::GetFullPath($Path).TrimEnd($trimChars)
}

function Assert-ExpectedPath {
    param(
        [string]$Path,
        [string]$Expected,
        [string]$Label
    )
    $normalizedPath = Get-NormalizedPath -Path $Path
    $normalizedExpected = Get-NormalizedPath -Path $Expected
    if (-not $normalizedPath.Equals($normalizedExpected, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "$Label resolved to $normalizedPath, expected $normalizedExpected"
    }
}

Assert-ExpectedPath -Path $InstallRoot -Expected $ExpectedInstallRoot -Label 'Install folder'
Assert-ExpectedPath -Path $StartMenuDir -Expected (Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\IZ Clinical Notes Analyzer') -Label 'Start Menu folder'

$normalizedInstallRoot = Get-NormalizedPath -Path $InstallRoot
if ($PSCommandPath) {
    $normalizedScriptPath = Get-NormalizedPath -Path $PSCommandPath
    $separator = [System.IO.Path]::DirectorySeparatorChar
    if ($normalizedScriptPath.StartsWith("$normalizedInstallRoot$separator", [System.StringComparison]::OrdinalIgnoreCase)) {
        $helperPath = Join-Path ([System.IO.Path]::GetTempPath()) "iz-cna-uninstall-$([System.Guid]::NewGuid().ToString('N')).ps1"
        Copy-Item -LiteralPath $PSCommandPath -Destination $helperPath -Force
        $argList = "-NoProfile -ExecutionPolicy Bypass -File `"$helperPath`" -InstalledAppRoot `"$InstallRoot`" -NoPause -DelaySeconds 2"
        Start-Process -FilePath 'powershell.exe' -ArgumentList $argList -WindowStyle Hidden
        Write-Host 'Uninstall cleanup started. The app folder will be removed in a few seconds.'
        Write-Host "Local data under %LOCALAPPDATA%\IZ Clinical Notes Analyzer will be preserved."
        exit 0
    }
}

$stopScript = Join-Path $InstallRoot 'scripts\stop-windows-local.ps1'
if (Test-Path -LiteralPath $stopScript) {
    Write-Host 'Stopping any running local app process...'
    & $stopScript -NoRestartPrompt -NoPause
}
Set-Location ([System.IO.Path]::GetTempPath())

foreach ($shortcut in $DesktopShortcuts) {
    if (Test-Path -LiteralPath $shortcut) {
        Remove-Item -LiteralPath $shortcut -Force
    }
}

if (Test-Path $StartMenuDir) {
    Remove-Item -LiteralPath $StartMenuDir -Recurse -Force
}
if (Test-Path $InstallRoot) {
    Remove-Item -LiteralPath $InstallRoot -Recurse -Force
}
Write-Host "Removed IZ Clinical Notes Analyzer application files and shortcuts."
Write-Host "Local data under %LOCALAPPDATA%\IZ Clinical Notes Analyzer was preserved."
'@ | Set-Content -Path (Join-Path $installerDir 'uninstall-windows-release.ps1') -Encoding UTF8
}

try {
    Set-Location $RootDir
    Write-Build 'IZ Clinical Notes Analyzer Windows release build'
    Write-Build "Version: $Version"
    Write-Build "Repository: $RootDir"

    Write-Step 'Running Windows preflight...'
    & (Join-Path $RootDir 'scripts\preflight-windows.ps1') -AssumeYes -SkipFrontendCheck
    if ($LASTEXITCODE -ne 0) {
        throw "Windows preflight failed. Review %LOCALAPPDATA%\IZ Clinical Notes Analyzer\logs\preflight-windows-latest.json."
    }

    Ensure-BackendBuildEnvironment
    Invoke-BackendTests
    Invoke-FrontendBuild

    Write-Build "Creating release package at $PackageDir"
    New-Item -ItemType Directory -Path $ReleaseRoot -Force | Out-Null
    Remove-GeneratedDirectory -Path $PackageDir -Parent $ReleaseRoot -Label 'Release package directory'
    New-Item -ItemType Directory -Path $AppDir -Force | Out-Null
    Copy-RepoContent -Destination $AppDir
    Write-InstallerFiles -TargetPackageDir $PackageDir

    $manifest = [ordered]@{
        app_name = 'IZ Clinical Notes Analyzer'
        version = $Version
        created_at = (Get-Date).ToUniversalTime().ToString('o')
        package_name = $PackageName
        install_root = '%LOCALAPPDATA%\Programs\IZ Clinical Notes Analyzer'
        local_data_root = '%LOCALAPPDATA%\IZ Clinical Notes Analyzer'
        install_command = 'Install-IZ-Clinical-Notes-Analyzer.cmd'
        launch_command = 'Launch-IZ-Clinical-Notes-Analyzer.cmd'
        stop_command = 'Stop-IZ-Clinical-Notes-Analyzer.cmd'
        diagnostics_command = 'Collect-IZ-Clinical-Notes-Analyzer-Diagnostics.cmd'
        backup_command = 'Backup-IZ-Clinical-Notes-Analyzer.cmd'
        uninstall_command = 'Uninstall-IZ-Clinical-Notes-Analyzer.cmd'
        complete_uninstall_command = 'Complete-Uninstall-IZ-Clinical-Notes-Analyzer.cmd'
        treatment_plan_handling_reference = 'app\docs\patient-treatment-plan-handling.md'
        treatment_plan_compliance_engine = 'local deterministic timeliness and checklist evaluation'
        frontend_dist_validated = $true
        forbidden_file_scan = 'passed'
    }
    $manifest | ConvertTo-Json -Depth 4 | Set-Content -Path (Join-Path $PackageDir 'release-manifest.json') -Encoding UTF8

    Assert-ReleaseRequiredItems -TargetPackageDir $PackageDir
    Assert-NoForbiddenReleaseItems -TargetPackageDir $PackageDir

    $zipPath = Join-Path $ReleaseRoot "$PackageName.zip"
    Assert-PathInside -Path $zipPath -Parent $ReleaseRoot -Label 'Release zip path'
    if (Test-Path $zipPath) { Remove-Item -LiteralPath $zipPath -Force }
    Compress-Archive -Path (Join-Path $PackageDir '*') -DestinationPath $zipPath
    Assert-ZipHasNoForbiddenItems -ZipPath $zipPath

    @"
Release folder: $PackageDir
Release zip: $zipPath
"@ | Set-Content -Path $LatestPathsFile -Encoding ASCII

    Write-Ok "Release package ready: $PackageDir"
    Write-Ok "Release zip ready: $zipPath"
    exit 0
}
catch {
    Write-Host ''
    Write-Fail 'Windows release build failed.'
    Write-Host $_.Exception.Message
    Write-Host ''
    Write-Host 'What to do next:'
    Write-Host '  1. Read the message above.'
    Write-Host '  2. Fix the named missing dependency, failed test, or unsafe file.'
    Write-Host '  3. Double-click Build-IZ-Windows-Installer.cmd again.'
    exit 1
}
