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
$NodeDir = Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Packages\OpenJS.NodeJS.LTS_Microsoft.Winget.Source_8wekyb3d8bbwe\node-v24.16.0-win-x64'
$Npm = Join-Path $NodeDir 'npm.cmd'

function Write-Step($Message) {
    Write-Host "[build] $Message"
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
        (Join-Path $RootDir '.venv'),
        (Join-Path $RootDir 'backend\.venv'),
        (Join-Path $RootDir 'frontend\node_modules'),
        (Join-Path $RootDir 'node_modules'),
        (Join-Path $RootDir 'dist'),
        (Join-Path $RootDir 'uploads'),
        (Join-Path $RootDir 'logs'),
        (Join-Path $RootDir '.pytest_cache'),
        (Join-Path $RootDir 'htmlcov'),
        (Join-Path $RootDir 'walkthroughs (2026-03-04)'),
        (Join-Path $RootDir 'video-extract (2026-06-05)')
    )
    $excludeFiles = @('.env', '*.sqlite', '*.sqlite3', '*.db', '*.log', '*.tmp')
    robocopy $RootDir $Destination /MIR /XD $excludeDirs /XF $excludeFiles /NFL /NDL /NJH /NJS /NP | Out-Null
    if ($LASTEXITCODE -gt 7) { throw "robocopy failed with exit code $LASTEXITCODE" }
}

function Write-InstallerFiles {
    param([string]$TargetPackageDir)
    $installCmd = Join-Path $TargetPackageDir 'Install-IZ-Clinical-Notes-Analyzer.cmd'
    $launchCmd = Join-Path $TargetPackageDir 'Launch-IZ-Clinical-Notes-Analyzer.cmd'
    $uninstallCmd = Join-Path $TargetPackageDir 'Uninstall-IZ-Clinical-Notes-Analyzer.cmd'

@"
@echo off
setlocal
set PACKAGE_DIR=%~dp0
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%PACKAGE_DIR%installer\install-windows-release.ps1"
if not "%ERRORLEVEL%"=="0" pause
exit /b %ERRORLEVEL%
"@ | Set-Content -Path $installCmd -Encoding ASCII

@"
@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0app\scripts\start-windows-local.ps1" -AssumeYes
if not "%ERRORLEVEL%"=="0" pause
exit /b %ERRORLEVEL%
"@ | Set-Content -Path $launchCmd -Encoding ASCII

@"
@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0installer\uninstall-windows-release.ps1"
if not "%ERRORLEVEL%"=="0" pause
exit /b %ERRORLEVEL%
"@ | Set-Content -Path $uninstallCmd -Encoding ASCII

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
$Launcher = Join-Path $InstallRoot 'scripts\Start-IZ-Clinical-Notes-Analyzer.cmd'
$InstalledInstallerDir = Join-Path $InstallRoot 'installer'
$StartShortcut = Join-Path $StartMenuDir 'IZ Clinical Notes Analyzer.lnk'
$UninstallShortcut = Join-Path $StartMenuDir 'Uninstall IZ Clinical Notes Analyzer.lnk'
$Uninstaller = Join-Path $InstallRoot 'Uninstall-IZ-Clinical-Notes-Analyzer.cmd'

function New-Shortcut {
    param(
        [string]$ShortcutPath,
        [string]$TargetPath,
        [string]$WorkingDirectory
    )
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($ShortcutPath)
    $shortcut.TargetPath = $TargetPath
    $shortcut.WorkingDirectory = $WorkingDirectory
    $shortcut.IconLocation = "$env:SystemRoot\System32\shell32.dll,220"
    $shortcut.Save()
}

New-Item -ItemType Directory -Path $InstallRoot, $StartMenuDir -Force | Out-Null
robocopy $SourceAppDir $InstallRoot /MIR /NFL /NDL /NJH /NJS /NP | Out-Null
if ($LASTEXITCODE -gt 7) { throw "Install copy failed with robocopy exit code $LASTEXITCODE" }
robocopy (Join-Path $PackageDir 'installer') $InstalledInstallerDir /MIR /NFL /NDL /NJH /NJS /NP | Out-Null
if ($LASTEXITCODE -gt 7) { throw "Installer helper copy failed with robocopy exit code $LASTEXITCODE" }

@"
@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0installer\uninstall-windows-release.ps1" -InstalledAppRoot "%~dp0"
if not "%ERRORLEVEL%"=="0" pause
exit /b %ERRORLEVEL%
"@ | Set-Content -Path $Uninstaller -Encoding ASCII

New-Shortcut -ShortcutPath $StartShortcut -TargetPath $Launcher -WorkingDirectory $InstallRoot
New-Shortcut -ShortcutPath $UninstallShortcut -TargetPath $Uninstaller -WorkingDirectory $InstallRoot

Write-Host "Installed IZ Clinical Notes Analyzer to $InstallRoot"
Write-Host "Start Menu shortcut: $StartShortcut"
Write-Host "Launching preflight..."
& (Join-Path $InstallRoot 'scripts\preflight-windows.ps1') -AssumeYes
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "Install complete. Use the Start Menu shortcut to launch the app."
'@ | Set-Content -Path (Join-Path $installerDir 'install-windows-release.ps1') -Encoding UTF8

@'
[CmdletBinding()]
param(
    [string]$InstalledAppRoot = ''
)

$ErrorActionPreference = 'Stop'
$InstallRoot = if ($InstalledAppRoot) { $InstalledAppRoot } else { Join-Path $env:LOCALAPPDATA 'Programs\IZ Clinical Notes Analyzer' }
$StartMenuDir = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\IZ Clinical Notes Analyzer'

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

Set-Location $RootDir
Write-Step "Running Windows preflight"
& (Join-Path $RootDir 'scripts\preflight-windows.ps1') -AssumeYes -SkipFrontendBuild:$SkipFrontendBuild
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

if (-not $SkipTests) {
    Write-Step "Running backend tests"
    $env:PYTHONPATH = Join-Path $RootDir 'backend'
    & (Join-Path $RootDir 'backend\.venv\Scripts\python.exe') -m pytest (Join-Path $RootDir 'backend\tests') -q
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

if (-not $SkipFrontendBuild) {
    if (-not (Test-Path $Npm)) {
        $Npm = (Get-Command npm.cmd -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -ErrorAction SilentlyContinue)
    }
    if (-not $Npm) { throw 'npm.cmd was not found. Install Node.js LTS or run preflight with frontend build already present.' }
    $env:PATH = "$(Split-Path $Npm -Parent);$env:PATH"
    Push-Location (Join-Path $RootDir 'frontend')
    try {
        Write-Step "Installing frontend dependencies"
        & $Npm install
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        if (-not $SkipTests) {
            Write-Step "Running frontend tests"
            & $Npm test -- --run
            if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        }
        Write-Step "Building frontend"
        & $Npm run build
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    } finally {
        Pop-Location
    }
}

Write-Step "Creating release package at $PackageDir"
New-Item -ItemType Directory -Path $ReleaseRoot -Force | Out-Null
Remove-GeneratedDirectory -Path $PackageDir -Parent $ReleaseRoot -Label 'Release package directory'
New-Item -ItemType Directory -Path $AppDir -Force | Out-Null
Copy-RepoContent -Destination $AppDir
Write-InstallerFiles -TargetPackageDir $PackageDir

$manifest = [ordered]@{
    app_name = 'IZ Clinical Notes Analyzer'
    version = $Version
    created_at = (Get-Date).ToUniversalTime().ToString('o')
    package_dir = $PackageDir
    install_command = 'Install-IZ-Clinical-Notes-Analyzer.cmd'
    launch_command = 'Launch-IZ-Clinical-Notes-Analyzer.cmd'
    uninstall_command = 'Uninstall-IZ-Clinical-Notes-Analyzer.cmd'
    source_repo = $RootDir
}
$manifest | ConvertTo-Json -Depth 4 | Set-Content -Path (Join-Path $PackageDir 'release-manifest.json') -Encoding UTF8

$zipPath = Join-Path $ReleaseRoot "$PackageName.zip"
Assert-PathInside -Path $zipPath -Parent $ReleaseRoot -Label 'Release zip path'
if (Test-Path $zipPath) { Remove-Item -LiteralPath $zipPath -Force }
Compress-Archive -Path (Join-Path $PackageDir '*') -DestinationPath $zipPath
Write-Step "Release package ready: $PackageDir"
Write-Step "Release zip ready: $zipPath"
