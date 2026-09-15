[CmdletBinding()]
param(
    [string]$EvidenceRoot = '',
    [string]$ReportPath = ''
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Assert-True {
    param(
        [Parameter(Mandatory = $true)]
        [bool]$Condition,
        [Parameter(Mandatory = $true)]
        [string]$Label
    )
    if (-not $Condition) { throw "assertion_failed:$Label" }
    Write-Host "[pass] $Label"
}

function Get-Sha256Lower {
    param([Parameter(Mandatory = $true)][string]$Path)
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Get-StringSha256Lower {
    param([Parameter(Mandatory = $true)][string]$Value)
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [System.Text.UTF8Encoding]::new($false).GetBytes($Value)
        return ([System.BitConverter]::ToString($sha.ComputeHash($bytes))).Replace('-', '').ToLowerInvariant()
    } finally {
        $sha.Dispose()
    }
}

function Read-Utf8Json {
    param([Parameter(Mandatory = $true)][string]$Path)

    $json = [System.IO.File]::ReadAllText($Path, [System.Text.UTF8Encoding]::new($false, $true))
    return $json | ConvertFrom-Json -ErrorAction Stop
}

function Assert-ExactJsonKeys {
    param(
        [Parameter(Mandatory = $true)]$Value,
        [Parameter(Mandatory = $true)][string[]]$Expected,
        [Parameter(Mandatory = $true)][string]$Label
    )
    $actual = @($Value.PSObject.Properties.Name | Sort-Object)
    $wanted = @($Expected | Sort-Object)
    Assert-True -Condition (($actual -join "`n") -ceq ($wanted -join "`n")) -Label $Label
}

$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$packagingModule = Join-Path $repositoryRoot 'scripts\installer\build-windows-package.psm1'
$templateRoot = Join-Path $repositoryRoot 'scripts\installer\templates'
$requiredTemplates = @(
    'Install-IZ-Clinical-Notes-Analyzer.cmd',
    'Launch-IZ-Clinical-Notes-Analyzer.cmd',
    'Stop-IZ-Clinical-Notes-Analyzer.cmd',
    'Collect-IZ-Clinical-Notes-Analyzer-Diagnostics.cmd',
    'Backup-IZ-Clinical-Notes-Analyzer.cmd',
    'Restore-IZ-Clinical-Notes-Analyzer.cmd',
    'Uninstall-IZ-Clinical-Notes-Analyzer.cmd',
    'Complete-Uninstall-IZ-Clinical-Notes-Analyzer.cmd',
    'Remove-IZ-Clinical-Notes-Analyzer.bootstrap.ps1'
)

Assert-True -Condition (Test-Path -LiteralPath $packagingModule -PathType Leaf) -Label 'packaging_helper_module_exists'
foreach ($templateName in $requiredTemplates) {
    Assert-True -Condition (Test-Path -LiteralPath (Join-Path $templateRoot $templateName) -PathType Leaf) -Label "template_exists:$templateName"
}

$qaParent = Join-Path ([Environment]::GetFolderPath('UserProfile')) 'IZ-CNA-QA'
if (-not (Test-Path -LiteralPath $qaParent -PathType Container)) {
    New-Item -ItemType Directory -Path $qaParent | Out-Null
}
Assert-True -Condition (-not ((Get-Item -LiteralPath $qaParent).Attributes -band [System.IO.FileAttributes]::ReparsePoint)) -Label 'qa_parent_is_physical'
if (-not $EvidenceRoot) {
    $EvidenceRoot = Join-Path $qaParent ('pkg-' + [Guid]::NewGuid().ToString('N').Substring(0, 12))
}
$ownerRoot = [System.IO.Path]::GetFullPath($EvidenceRoot)
Assert-True -Condition ((Split-Path $ownerRoot -Parent) -ceq $qaParent) -Label 'owned_root_parent'
Assert-True -Condition ((Split-Path $ownerRoot -Leaf) -cmatch '^pkg-[a-f0-9]{12}$') -Label 'owned_root_name'
Assert-True -Condition (-not (Test-Path -LiteralPath $ownerRoot)) -Label 'owned_root_is_fresh'
New-Item -ItemType Directory -Path $ownerRoot | Out-Null
$ownerMarker = Join-Path $ownerRoot 'owner.json'
[System.IO.File]::WriteAllText(
    $ownerMarker,
    '{"owner":"iz-cna-installer-packaging-test-v1"}',
    [System.Text.UTF8Encoding]::new($false)
)
$savedEnvironment = @{}
foreach ($name in @(
    'LOCALAPPDATA', 'APPDATA', 'USERPROFILE', 'TEMP', 'TMP',
    'IZ_CNA_LOCAL_APP_DATA_DIR', 'IZ_CNA_ENV_FILE', 'PSModuleAnalysisCachePath'
)) {
    $item = Get-Item -LiteralPath "Env:$name" -ErrorAction SilentlyContinue
    $savedEnvironment[$name] = if ($null -eq $item) { $null } else { [string]$item.Value }
}
$isolatedProfile = Join-Path $ownerRoot 'profile'
$env:LOCALAPPDATA = Join-Path $isolatedProfile 'LocalAppData'
$env:APPDATA = Join-Path $isolatedProfile 'AppData'
$env:USERPROFILE = Join-Path $isolatedProfile 'UserProfile'
$env:TEMP = Join-Path $isolatedProfile 'Temp'
$env:TMP = $env:TEMP
$env:IZ_CNA_LOCAL_APP_DATA_DIR = Join-Path $env:LOCALAPPDATA 'IZ Clinical Notes Analyzer'
$env:IZ_CNA_ENV_FILE = Join-Path $env:IZ_CNA_LOCAL_APP_DATA_DIR '.env'
$env:PSModuleAnalysisCachePath = Join-Path $isolatedProfile 'PowerShell\ModuleAnalysisCache'
New-Item -ItemType Directory -Path @(
    $env:LOCALAPPDATA, $env:APPDATA, $env:USERPROFILE, $env:TEMP,
    $env:IZ_CNA_LOCAL_APP_DATA_DIR, (Split-Path $env:PSModuleAnalysisCachePath -Parent)
) -Force | Out-Null

$result = [ordered]@{
    schema = 'iz-cna-installer-packaging-test-v1'
    source_revision = (& git -C $repositoryRoot rev-parse HEAD).Trim()
    completed_utc = $null
    wrapper = $null
    launch_wrapper = $null
    maintenance_bundle = $null
    release_manifest = $null
    build_receipt = $null
    collision = $null
    negative_cases = $null
}
$legacyFiles = @(
    [pscustomobject][ordered]@{ path = 'VERSION.json'; length = 0L; sha256 = ('0' * 64) },
    [pscustomobject][ordered]@{ path = 'frontend/dist/index.html'; length = 0L; sha256 = ('0' * 64) },
    [pscustomobject][ordered]@{ path = 'runtime/IZClinicalNotesAnalyzer.exe'; length = 0L; sha256 = ('0' * 64) }
)
$legacyProgramInventory = [pscustomobject][ordered]@{
    schema = 'iz-cna-legacy-program-inventory-v1'
    product_id = 'r3.iz-clinical-notes-analyzer.desktop'
    sources = @(
        [pscustomobject][ordered]@{ archive_name = 'IZ-Clinical-Notes-Analyzer-v2.0.0-beta.3.zip'; archive_length = 43716351L; archive_sha256 = '9c5fd47203242e1a21df612f719f1c14fa4240c86ba869f924ec4690834fc89c'; version = '2.0.0-beta.3'; build = '2026.09.03.1'; files = $legacyFiles },
        [pscustomobject][ordered]@{ archive_name = 'IZ-Clinical-Notes-Analyzer-v2.0.0-beta.4.zip'; archive_length = 43873389L; archive_sha256 = '67b83eea402566658dea6d64ac6cba37a192a7d1bd670cf560541324c0092b14'; version = '2.0.0-beta.4'; build = '2026.09.10.2'; files = $legacyFiles }
    )
}

try {
    Import-Module $packagingModule -Force
    $packageRoot = Join-Path $ownerRoot ('package path & meta ' + [char]0x00e9)
    New-Item -ItemType Directory -Path $packageRoot | Out-Null
    $renderResult = Write-IzPackageInstallerFiles -RepositoryRoot $repositoryRoot -PackageRoot $packageRoot -LegacyProgramInventory $legacyProgramInventory

    $expectedRootCommands = @(
        'Install-IZ-Clinical-Notes-Analyzer.cmd',
        'Launch-IZ-Clinical-Notes-Analyzer.cmd',
        'Stop-IZ-Clinical-Notes-Analyzer.cmd',
        'Collect-IZ-Clinical-Notes-Analyzer-Diagnostics.cmd',
        'Backup-IZ-Clinical-Notes-Analyzer.cmd',
        'Restore-IZ-Clinical-Notes-Analyzer.cmd',
        'Uninstall-IZ-Clinical-Notes-Analyzer.cmd',
        'Complete-Uninstall-IZ-Clinical-Notes-Analyzer.cmd'
    )
    foreach ($relativePath in $expectedRootCommands) {
        $renderedPath = Join-Path $packageRoot $relativePath
        Assert-True -Condition (Test-Path -LiteralPath $renderedPath -PathType Leaf) -Label "rendered_root_command:$relativePath"
        $renderedText = [System.IO.File]::ReadAllText($renderedPath)
        $renderedBytes = [System.IO.File]::ReadAllBytes($renderedPath)
        Assert-True -Condition ($renderedText -notmatch '@@[A-Z][A-Z0-9_]*@@') -Label "no_unresolved_token:$relativePath"
        $withoutCrlf = $renderedText.Replace("`r`n", '')
        Assert-True -Condition (-not $withoutCrlf.Contains("`r") -and -not $withoutCrlf.Contains("`n")) -Label "cmd_uses_only_crlf:$relativePath"
        Assert-True -Condition (@($renderedBytes | Where-Object { $_ -gt 127 }).Count -eq 0) -Label "cmd_is_ascii:$relativePath"
    }

    Push-Location $packageRoot
    try {
        $launchAbsentOutput = @(& $env:ComSpec /d /c "Launch-IZ-Clinical-Notes-Analyzer.cmd -NoBrowser -NoPause" 2>&1)
        $launchAbsentExit = [int]$LASTEXITCODE
    } finally {
        Pop-Location
    }
    Assert-True -Condition ($launchAbsentExit -eq 20) -Label 'package_launch_requires_installed_app'
    Assert-True -Condition (($launchAbsentOutput -join "`n") -match 'Run Install-IZ-Clinical-Notes-Analyzer\.cmd first') -Label 'package_launch_missing_message_is_actionable'

    $installedScripts = Join-Path $env:LOCALAPPDATA 'Programs\IZ Clinical Notes Analyzer\scripts'
    New-Item -ItemType Directory -Path $installedScripts -Force | Out-Null
    $launchArgumentReport = Join-Path $ownerRoot 'installed-launch-arguments.txt'
    $previousLaunchArgumentReport = $env:IZ_CNA_LAUNCH_ARGUMENT_REPORT
    $env:IZ_CNA_LAUNCH_ARGUMENT_REPORT = $launchArgumentReport
    [System.IO.File]::WriteAllText(
        (Join-Path $installedScripts 'launch-packaged-runtime.cmd'),
        "@echo off`r`nsetlocal DisableDelayedExpansion`r`n> `"%IZ_CNA_LAUNCH_ARGUMENT_REPORT%`" echo(%*`r`nexit /b 37`r`n",
        [System.Text.ASCIIEncoding]::new()
    )
    try {
        Push-Location $packageRoot
        try {
            $null = & $env:ComSpec /d /c "Launch-IZ-Clinical-Notes-Analyzer.cmd -NoBrowser -NoPause" 2>&1
            $launchInstalledExit = [int]$LASTEXITCODE
        } finally {
            Pop-Location
        }
    } finally {
        if ($null -eq $previousLaunchArgumentReport) { Remove-Item Env:\IZ_CNA_LAUNCH_ARGUMENT_REPORT -ErrorAction SilentlyContinue }
        else { $env:IZ_CNA_LAUNCH_ARGUMENT_REPORT = $previousLaunchArgumentReport }
    }
    Assert-True -Condition ($launchInstalledExit -eq 37) -Label 'package_launch_preserves_installed_launcher_exit'
    Assert-True -Condition (
        [System.IO.File]::ReadAllText($launchArgumentReport).Trim() -ceq '-NoBrowser -NoPause'
    ) -Label 'package_launch_forwards_installed_launcher_arguments'
    $result.launch_wrapper = [ordered]@{
        missing_install_exit_code = $launchAbsentExit
        installed_launcher_exit_code = $launchInstalledExit
        forwarded_arguments = [System.IO.File]::ReadAllText($launchArgumentReport).Trim()
    }

    $installerPaths = @(Get-IzInstallerRuntimeRelativePaths)
    $actualInstallerPaths = @(
        Get-ChildItem -LiteralPath (Join-Path $packageRoot 'installer') -File |
            ForEach-Object Name |
            Sort-Object
    )
    Assert-True -Condition (($actualInstallerPaths -join "`n") -ceq ((@($installerPaths | Sort-Object)) -join "`n")) -Label 'installer_allowlist_is_exact'

    $copiedRuntime = @($installerPaths | Where-Object {
        $_ -notin @('Remove-IZ-Clinical-Notes-Analyzer.bootstrap.ps1', 'maintenance-bundle-manifest.json', 'legacy-program-inventory.json')
    })
    foreach ($fileName in $copiedRuntime) {
        $sourcePath = Join-Path (Join-Path $repositoryRoot 'scripts\installer') $fileName
        $targetPath = Join-Path (Join-Path $packageRoot 'installer') $fileName
        Assert-True -Condition ((Get-Sha256Lower $sourcePath) -ceq (Get-Sha256Lower $targetPath)) -Label "runtime_copy_is_byte_exact:$fileName"
    }

    $bundlePath = Join-Path $packageRoot 'installer\maintenance-bundle-manifest.json'
    $bundle = Read-Utf8Json -Path $bundlePath
    Assert-ExactJsonKeys -Value $bundle -Expected @('schema', 'product_id', 'files') -Label 'bundle_exact_top_keys'
    Assert-True -Condition ($bundle.schema -ceq 'iz-cna-maintenance-bundle-v1') -Label 'bundle_schema'
    $expectedBundleFiles = @(
        'maintenance-windows.ps1',
        'uninstall-windows-release.ps1',
        'maintenance-common.psm1',
        'maintenance-contracts.psm1',
        'maintenance-paths.psm1',
        'maintenance-version.psm1',
        'maintenance-lock.psm1',
        'maintenance-journal.psm1',
        'maintenance-runtime.psm1'
    )
    Assert-True -Condition ((@($bundle.files.path) -join "`n") -ceq ((@($expectedBundleFiles | Sort-Object)) -join "`n")) -Label 'bundle_exact_nine_files'
    foreach ($entry in $bundle.files) {
        Assert-ExactJsonKeys -Value $entry -Expected @('path', 'length', 'sha256') -Label "bundle_file_exact_keys:$($entry.path)"
        $runtimePath = Join-Path (Join-Path $packageRoot 'installer') $entry.path
        Assert-True -Condition ([long]$entry.length -eq (Get-Item -LiteralPath $runtimePath).Length) -Label "bundle_file_length:$($entry.path)"
        Assert-True -Condition ([string]$entry.sha256 -ceq (Get-Sha256Lower $runtimePath)) -Label "bundle_file_hash:$($entry.path)"
    }
    Assert-True -Condition ([string]$renderResult.maintenance_bundle_manifest_sha256 -ceq (Get-Sha256Lower $bundlePath)) -Label 'bundle_hash_returned_by_renderer'
    $bootstrapText = [System.IO.File]::ReadAllText((Join-Path $packageRoot 'installer\Remove-IZ-Clinical-Notes-Analyzer.bootstrap.ps1'))
    $bootstrapBytes = [System.IO.File]::ReadAllBytes((Join-Path $packageRoot 'installer\Remove-IZ-Clinical-Notes-Analyzer.bootstrap.ps1'))
    Assert-True -Condition ($bootstrapBytes.Count -ge 3 -and $bootstrapBytes[0] -eq 0xef -and $bootstrapBytes[1] -eq 0xbb -and $bootstrapBytes[2] -eq 0xbf) -Label 'bootstrap_is_utf8_bom'
    Assert-True -Condition ($bootstrapText.Contains([string]$renderResult.maintenance_bundle_manifest_sha256)) -Label 'bootstrap_embeds_bundle_hash'
    Assert-True -Condition ($bootstrapText -notmatch '@@[A-Z][A-Z0-9_]*@@') -Label 'bootstrap_has_no_unresolved_token'
    $result.maintenance_bundle = [ordered]@{
        path = 'installer/maintenance-bundle-manifest.json'
        sha256 = Get-Sha256Lower $bundlePath
        files = @($bundle.files.path)
    }

    $stubSource = @'
[CmdletBinding()]
param(
    [string]$Action,
    [string]$PackageRoot,
    [switch]$NoPause,
    [switch]$NonInteractive,
    [string]$ResultPath,
    [switch]$UnknownSyntheticFlag
)
$record = [ordered]@{
    action = $Action
    raw_package_root = $PackageRoot
    package_root = [System.IO.Path]::GetFullPath($PackageRoot).TrimEnd([char[]]@('\', '/'))
    no_pause = [bool]$NoPause
    non_interactive = [bool]$NonInteractive
    unknown_flag = [bool]$UnknownSyntheticFlag
}
[System.IO.File]::WriteAllText($ResultPath, ($record | ConvertTo-Json), [System.Text.UTF8Encoding]::new($false))
if ($UnknownSyntheticFlag) { exit 20 }
if (-not $NoPause) {
    Write-Host 'SYNTHETIC_FINAL_PAUSE'
    $null = Read-Host 'Press Enter to close'
}
exit [int]$env:IZ_CNA_SYNTHETIC_DISPATCH_EXIT
'@
    $pathVariants = [ordered]@{
        spaces = 'wrapper space path'
        apostrophe = "wrapper apostrophe's path"
        ampersand = 'wrapper ampersand & path'
        parentheses = 'wrapper parentheses (path)'
        unicode = ('wrapper unicode ' + [char]0x00e9 + [char]0x4e2d)
        percent = 'wrapper percent %IZ_CNA_SYNTHETIC_UNSET% path'
        exclamation = 'wrapper exclamation !IZ_CNA_SYNTHETIC_UNSET! path'
    }
    $previousSyntheticExit = $env:IZ_CNA_SYNTHETIC_DISPATCH_EXIT
    $wrapperObservations = @()
    try {
        $env:IZ_CNA_SYNTHETIC_DISPATCH_EXIT = '31'
        foreach ($variant in $pathVariants.GetEnumerator()) {
            $behaviorRoot = Join-Path $ownerRoot $variant.Value
            New-Item -ItemType Directory -Path $behaviorRoot | Out-Null
            $null = Write-IzPackageInstallerFiles -RepositoryRoot $repositoryRoot -PackageRoot $behaviorRoot -LegacyProgramInventory $legacyProgramInventory
            [System.IO.File]::WriteAllText(
                (Join-Path $behaviorRoot 'installer\maintenance-windows.ps1'),
                $stubSource,
                [System.Text.UTF8Encoding]::new($true)
            )
            $wrapperResultPath = Join-Path $ownerRoot ("wrapper-result-{0}.json" -f $variant.Key)
            Push-Location $behaviorRoot
            try {
                $wrapperOutput = @(& $env:ComSpec /d /c "Install-IZ-Clinical-Notes-Analyzer.cmd -NoPause -NonInteractive -ResultPath `"$wrapperResultPath`"" 2>&1)
                $wrapperExitCode = [int]$LASTEXITCODE
            } finally {
                Pop-Location
            }
            Assert-True -Condition ($wrapperExitCode -eq 31) -Label "install_wrapper_exit:$($variant.Key)"
            Assert-True -Condition (Test-Path -LiteralPath $wrapperResultPath -PathType Leaf) -Label "install_wrapper_invokes_dispatcher:$($variant.Key)"
            $wrapperRecord = Read-Utf8Json -Path $wrapperResultPath
            Assert-True -Condition ($wrapperRecord.action -ceq 'AutoInstall') -Label "install_wrapper_action:$($variant.Key)"
            Assert-True -Condition ([bool]$wrapperRecord.no_pause -and [bool]$wrapperRecord.non_interactive) -Label "install_wrapper_flags:$($variant.Key)"
            Assert-True -Condition ([string]$wrapperRecord.raw_package_root -match '[\\/]$') -Label "install_wrapper_trailing_separator:$($variant.Key)"
            Assert-True -Condition ([string]::Equals($wrapperRecord.package_root, $behaviorRoot, [System.StringComparison]::OrdinalIgnoreCase)) -Label "install_wrapper_quotes_package_root:$($variant.Key)"
            Assert-True -Condition (-not (($wrapperOutput -join "`n") -match 'SYNTHETIC_FINAL_PAUSE')) -Label "install_wrapper_no_pause:$($variant.Key)"
            $wrapperObservations += [ordered]@{
                variant = $variant.Key
                exit_code = $wrapperExitCode
                package_root_sha256 = Get-StringSha256Lower $wrapperRecord.package_root
            }
        }

        $controlRoot = Join-Path $ownerRoot $pathVariants.spaces
        $unknownResultPath = Join-Path $ownerRoot 'wrapper-result-unknown.json'
        Push-Location $controlRoot
        try {
            $null = & $env:ComSpec /d /c "Install-IZ-Clinical-Notes-Analyzer.cmd -NoPause -NonInteractive -UnknownSyntheticFlag -ResultPath `"$unknownResultPath`"" 2>&1
            $unknownExitCode = [int]$LASTEXITCODE
        } finally { Pop-Location }
        Assert-True -Condition ($unknownExitCode -eq 20) -Label 'install_wrapper_preserves_unknown_flag_failure'

        $env:IZ_CNA_SYNTHETIC_DISPATCH_EXIT = '0'
        $pauseResultPath = Join-Path $ownerRoot 'wrapper-result-pause.json'
        $processInfo = [System.Diagnostics.ProcessStartInfo]::new()
        $processInfo.FileName = $env:ComSpec
        $processInfo.Arguments = "/d /c Install-IZ-Clinical-Notes-Analyzer.cmd -NonInteractive -ResultPath `"$pauseResultPath`""
        $processInfo.WorkingDirectory = $controlRoot
        $processInfo.UseShellExecute = $false
        $processInfo.RedirectStandardInput = $true
        $processInfo.RedirectStandardOutput = $true
        $processInfo.RedirectStandardError = $true
        $process = [System.Diagnostics.Process]::new()
        $process.StartInfo = $processInfo
        Assert-True -Condition $process.Start() -Label 'install_wrapper_pause_process_started'
        $process.StandardInput.WriteLine('')
        $process.StandardInput.Close()
        Assert-True -Condition $process.WaitForExit(10000) -Label 'install_wrapper_pause_process_completed'
        $pauseOutput = $process.StandardOutput.ReadToEnd() + $process.StandardError.ReadToEnd()
        Assert-True -Condition ($process.ExitCode -eq 0) -Label 'install_wrapper_preserves_success_exit'
        Assert-True -Condition ($pauseOutput.Contains('SYNTHETIC_FINAL_PAUSE')) -Label 'install_wrapper_default_pause_delegated'
        $process.Dispose()
    } finally {
        if ($null -eq $previousSyntheticExit) { Remove-Item Env:\IZ_CNA_SYNTHETIC_DISPATCH_EXIT -ErrorAction SilentlyContinue }
        else { $env:IZ_CNA_SYNTHETIC_DISPATCH_EXIT = $previousSyntheticExit }
    }

    $realUnknownRoot = Join-Path $ownerRoot ('real unknown & ' + [char]0x00e9)
    New-Item -ItemType Directory -Path $realUnknownRoot | Out-Null
    $null = Write-IzPackageInstallerFiles -RepositoryRoot $repositoryRoot -PackageRoot $realUnknownRoot -LegacyProgramInventory $legacyProgramInventory
    $realUnknownResultPath = Join-Path $ownerRoot 'real-unknown-result.json'
    Push-Location $realUnknownRoot
    try {
        $realUnknownOutput = @(& $env:ComSpec /d /c "Install-IZ-Clinical-Notes-Analyzer.cmd -NoPause -NonInteractive -ResultPath `"$realUnknownResultPath`" -DefinitelyUnsupportedPackagingFlag" 2>&1)
        $realUnknownExitCode = [int]$LASTEXITCODE
    } finally { Pop-Location }
    Assert-True -Condition ($realUnknownExitCode -eq 20) -Label 'real_dispatcher_unknown_flag_exit'
    Assert-True -Condition (Test-Path -LiteralPath $realUnknownResultPath -PathType Leaf) -Label 'real_dispatcher_unknown_flag_result'
    $realUnknownResult = Read-Utf8Json -Path $realUnknownResultPath
    Assert-True -Condition ([int]$realUnknownResult.code -eq 20) -Label 'real_dispatcher_unknown_flag_result_code'
    Assert-True -Condition ([string]$realUnknownResult.reason -match 'UNKNOWN|ARGUMENT|PARAMETER') -Label 'real_dispatcher_unknown_flag_reason'
    Assert-True -Condition (-not (($realUnknownOutput -join "`n") -match 'SYNTHETIC_FINAL_PAUSE|Press any key to continue')) -Label 'real_dispatcher_unknown_flag_no_pause'
    $result.wrapper = [ordered]@{
        variants = $wrapperObservations
        unknown_flag_exit_code = $unknownExitCode
        real_unknown_flag_exit_code = $realUnknownExitCode
        real_unknown_flag_reason = [string]$realUnknownResult.reason
        success_exit_code = 0
        default_pause_observed = $true
    }

    $appRoot = Join-Path $packageRoot 'app'
    foreach ($relativePath in @(
        'runtime\IZClinicalNotesAnalyzer.exe',
        'frontend\dist\index.html',
        'frontend\dist\assets\app.js',
        'config\rules\synthetic.yaml',
        'config\checklists\treatment-plan-v1.json',
        'VERSION',
        'VERSION.json'
    )) {
        $path = Join-Path $appRoot $relativePath
        New-Item -ItemType Directory -Path (Split-Path $path -Parent) -Force | Out-Null
        [System.IO.File]::WriteAllText($path, "synthetic:$relativePath", [System.Text.UTF8Encoding]::new($false))
    }

    $negativeReasons = [ordered]@{}
    foreach ($caseName in @('missing-member', 'unsafe-canary', 'bundle-tamper')) {
        $negativeRoot = Join-Path $ownerRoot $caseName
        New-Item -ItemType Directory -Path $negativeRoot | Out-Null
        Get-ChildItem -LiteralPath $packageRoot -Force | Copy-Item -Destination $negativeRoot -Recurse
        if ($caseName -eq 'missing-member') {
            Remove-Item -LiteralPath (Join-Path $negativeRoot 'installer\maintenance-lock.psm1') -Force
        } elseif ($caseName -eq 'unsafe-canary') {
            $canaryPath = Join-Path $negativeRoot 'app\tests\unsafe-canary.txt'
            New-Item -ItemType Directory -Path (Split-Path $canaryPath -Parent) | Out-Null
            [System.IO.File]::WriteAllText($canaryPath, 'unsafe packaging canary', [System.Text.UTF8Encoding]::new($false))
        } else {
            $tamperedBundlePath = Join-Path $negativeRoot 'installer\maintenance-bundle-manifest.json'
            $tamperedBundle = Read-Utf8Json -Path $tamperedBundlePath
            $tamperedBundle.files[0].sha256 = '0' * 64
            [System.IO.File]::WriteAllText(
                $tamperedBundlePath,
                ($tamperedBundle | ConvertTo-Json -Depth 5),
                [System.Text.UTF8Encoding]::new($false)
            )
        }
        try {
            $null = Write-IzReleaseManifest `
                -PackageRoot $negativeRoot `
                -Version '2.0.0-beta.4' `
                -Build '2026.09.14.1' `
                -InstallerRevision 1 `
                -ReleaseChannel 'beta-local-desktop-v2'
            $negativeReasons[$caseName] = 'NO_ERROR'
        } catch {
            $negativeReasons[$caseName] = $_.Exception.Message
        }
    }
    Assert-True -Condition (
        [string]$negativeReasons['missing-member'] -ceq 'REQUIRED_PACKAGE_MEMBER_MISSING:installer/maintenance-lock.psm1'
    ) -Label 'release_manifest_rejects_missing_required_member'
    Assert-True -Condition (
        [string]$negativeReasons['unsafe-canary'] -ceq 'FORBIDDEN_PACKAGE_DEVELOPER_MEMBER'
    ) -Label 'release_manifest_rejects_unsafe_canary'
    Assert-True -Condition (
        [string]$negativeReasons['bundle-tamper'] -ceq 'MAINTENANCE_BUNDLE_FILE_MISMATCH'
    ) -Label 'release_manifest_rejects_bundle_hash_mismatch'
    $result.negative_cases = $negativeReasons

    $manifest = Write-IzReleaseManifest `
        -PackageRoot $packageRoot `
        -Version '2.0.0-beta.4' `
        -Build '2026.09.14.1' `
        -InstallerRevision 1 `
        -ReleaseChannel 'beta-local-desktop-v2'
    $manifestPath = Join-Path $packageRoot 'release-manifest.json'
    $manifestFromDisk = Read-Utf8Json -Path $manifestPath
    Assert-ExactJsonKeys -Value $manifestFromDisk -Expected @(
        'schema', 'product_id', 'version', 'build', 'installer_revision', 'release_channel',
        'compatibility', 'payload_identity', 'files'
    ) -Label 'release_manifest_exact_top_keys'
    Assert-ExactJsonKeys -Value $manifestFromDisk.compatibility -Expected @(
        'source_version_minimum', 'source_version_maximum', 'source_build_minimum',
        'source_build_maximum', 'source_schema_minimum', 'source_schema_maximum', 'target_schema'
    ) -Label 'release_manifest_exact_compatibility_keys'
    Assert-True -Condition (-not (@($manifestFromDisk.files.path) -contains 'release-manifest.json')) -Label 'release_manifest_excludes_itself'
    $ordinalPaths = [string[]]@($manifestFromDisk.files.path)
    $sortedPaths = [string[]]@($ordinalPaths)
    [Array]::Sort($sortedPaths, [System.StringComparer]::Ordinal)
    Assert-True -Condition (($ordinalPaths -join "`n") -ceq ($sortedPaths -join "`n")) -Label 'release_manifest_paths_sorted_ordinal'
    $canonicalRecords = @($manifestFromDisk.files | ForEach-Object { "{0}`t{1}`t{2}`n" -f $_.path, $_.length, $_.sha256 }) -join ''
    Assert-True -Condition ([string]$manifestFromDisk.payload_identity -ceq (Get-StringSha256Lower $canonicalRecords)) -Label 'release_manifest_payload_identity'
    $bootstrapRecords = @($manifestFromDisk.files | Where-Object {
        [string]$_.path -ceq 'installer/Remove-IZ-Clinical-Notes-Analyzer.bootstrap.ps1'
    })
    Assert-True -Condition ($bootstrapRecords.Count -eq 1) -Label 'release_manifest_has_one_rendered_bootstrap_record'
    Assert-True -Condition (
        [string]$bootstrapRecords[0].sha256 -ceq (Get-Sha256Lower (Join-Path $packageRoot 'installer\Remove-IZ-Clinical-Notes-Analyzer.bootstrap.ps1'))
    ) -Label 'release_manifest_rendered_bootstrap_hash_matches_bytes'
    Assert-IzReleaseManifest -PackageRoot $packageRoot | Out-Null
    $result.release_manifest = [ordered]@{
        sha256 = Get-Sha256Lower $manifestPath
        payload_identity = [string]$manifest.payload_identity
        file_count = @($manifest.files).Count
        rendered_bootstrap_sha256 = [string]$bootstrapRecords[0].sha256
    }

    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zipPath = Join-Path $ownerRoot 'candidate.zip'
    [System.IO.Compression.ZipFile]::CreateFromDirectory($packageRoot, $zipPath)
    $gateEvidencePath = Join-Path $ownerRoot 'candidate.build-gates.json'
    [System.IO.File]::WriteAllText($gateEvidencePath, '{"observable":"synthetic packaging contract gate"}', [System.Text.UTF8Encoding]::new($false))
    $gateNames = @(
        'backend_tests',
        'frontend_tests',
        'frontend_build',
        'repository_safety',
        'directory_safety',
        'zip_safety',
        'frozen_bundle_inspection'
    )
    $gates = @($gateNames | ForEach-Object {
        [ordered]@{
            name = $_
            status = 'passed'
            command = 'synthetic packaging unit boundary'
            exit_code = 0
            evidence = 'candidate.build-gates.json'
        }
    })
    $receiptPath = Join-Path $ownerRoot 'candidate.build-receipt.json'
    $receipt = Write-IzBuildReceipt `
        -ReceiptPath $receiptPath `
        -ProductId 'r3.iz-clinical-notes-analyzer.desktop' `
        -Version '2.0.0-beta.4' `
        -Build '2026.09.14.1' `
        -InstallerRevision 1 `
        -SourceRevision '0123456789abcdef0123456789abcdef01234567' `
        -PackageDirectory $packageRoot `
        -ZipPath $zipPath `
        -ManifestPath $manifestPath `
        -PayloadIdentity $manifest.payload_identity `
        -Gates $gates
    $receiptFromDisk = Read-Utf8Json -Path $receiptPath
    Assert-ExactJsonKeys -Value $receiptFromDisk -Expected @(
        'schema', 'product_id', 'version', 'build', 'installer_revision', 'source_revision',
        'package_directory', 'zip_path', 'zip_length', 'zip_sha256', 'manifest_sha256',
        'payload_identity', 'gates', 'created_utc'
    ) -Label 'build_receipt_exact_top_keys'
    Assert-True -Condition ($receiptFromDisk.schema -ceq 'iz-cna-build-receipt-v1') -Label 'build_receipt_schema'
    Assert-True -Condition ((@($receiptFromDisk.gates.name) -join "`n") -ceq ($gateNames -join "`n")) -Label 'build_receipt_exact_gate_names'
    Assert-True -Condition ([long]$receiptFromDisk.zip_length -eq (Get-Item -LiteralPath $zipPath).Length) -Label 'build_receipt_zip_length'
    Assert-True -Condition ([string]$receiptFromDisk.zip_sha256 -ceq (Get-Sha256Lower $zipPath)) -Label 'build_receipt_zip_hash'
    Assert-True -Condition ([string]$receiptFromDisk.manifest_sha256 -ceq (Get-Sha256Lower $manifestPath)) -Label 'build_receipt_manifest_hash'
    $mismatchReceiptPath = Join-Path $ownerRoot 'mismatched.build-receipt.json'
    $mismatchReason = ''
    try {
        $null = Write-IzBuildReceipt `
            -ReceiptPath $mismatchReceiptPath `
            -ProductId 'r3.iz-clinical-notes-analyzer.desktop' `
            -Version '2.0.0-beta.4' `
            -Build '2026.09.14.2' `
            -InstallerRevision 1 `
            -SourceRevision '0123456789abcdef0123456789abcdef01234567' `
            -PackageDirectory $packageRoot `
            -ZipPath $zipPath `
            -ManifestPath $manifestPath `
            -PayloadIdentity $manifest.payload_identity `
            -Gates $gates
    } catch {
        $mismatchReason = $_.Exception.Message
    }
    Assert-True -Condition ($mismatchReason -ceq 'BUILD_RECEIPT_MANIFEST_MISMATCH') -Label 'build_receipt_rejects_manifest_identity_mismatch'
    Assert-True -Condition (-not (Test-Path -LiteralPath $mismatchReceiptPath)) -Label 'build_receipt_mismatch_is_not_written'
    $result.build_receipt = [ordered]@{
        sha256 = Get-Sha256Lower $receiptPath
        zip_length = [long]$receipt.zip_length
        zip_sha256 = [string]$receipt.zip_sha256
        gate_names = @($receipt.gates.name)
        mismatch_reason = $mismatchReason
    }

    $collisionRoot = Join-Path $ownerRoot 'collision'
    $collisionZip = Join-Path $ownerRoot 'collision.zip'
    $collisionReceipt = Join-Path $ownerRoot 'collision.build-receipt.json'
    New-Item -ItemType Directory -Path $collisionRoot | Out-Null
    [System.IO.File]::WriteAllText((Join-Path $collisionRoot 'sentinel.txt'), 'directory-sentinel', [System.Text.UTF8Encoding]::new($false))
    [System.IO.File]::WriteAllText($collisionZip, 'zip-sentinel', [System.Text.UTF8Encoding]::new($false))
    [System.IO.File]::WriteAllText($collisionReceipt, 'receipt-sentinel', [System.Text.UTF8Encoding]::new($false))
    $beforeHashes = @(
        (Get-Sha256Lower (Join-Path $collisionRoot 'sentinel.txt'))
        (Get-Sha256Lower $collisionZip)
        (Get-Sha256Lower $collisionReceipt)
    )
    $collisionReason = ''
    try {
        Assert-IzArtifactPathsAvailable -Paths @($collisionRoot, $collisionZip, $collisionReceipt)
    } catch {
        $collisionReason = $_.Exception.Message
    }
    $afterHashes = @(
        (Get-Sha256Lower (Join-Path $collisionRoot 'sentinel.txt'))
        (Get-Sha256Lower $collisionZip)
        (Get-Sha256Lower $collisionReceipt)
    )
    Assert-True -Condition ($collisionReason -ceq 'ARTIFACT_COLLISION') -Label 'artifact_collision_reason'
    Assert-True -Condition (($beforeHashes -join "`n") -ceq ($afterHashes -join "`n")) -Label 'artifact_collision_preserves_existing_bytes'
    $result.collision = [ordered]@{
        reason = $collisionReason
        sentinel_hashes = $afterHashes
    }

    $result.completed_utc = [DateTime]::UtcNow.ToString('o')
    if ($ReportPath) {
        $fullReportPath = [System.IO.Path]::GetFullPath($ReportPath)
        $reportParent = Split-Path $fullReportPath -Parent
        if (-not (Test-Path -LiteralPath $reportParent -PathType Container)) {
            New-Item -ItemType Directory -Path $reportParent -Force | Out-Null
        }
        [System.IO.File]::WriteAllText(
            $fullReportPath,
            ($result | ConvertTo-Json -Depth 10),
            [System.Text.UTF8Encoding]::new($false)
        )
    }
    Write-Host 'windows_installer_packaging=PASS'
} finally {
    foreach ($name in $savedEnvironment.Keys) {
        if ($null -eq $savedEnvironment[$name]) { Remove-Item -LiteralPath "Env:$name" -ErrorAction SilentlyContinue }
        else { Set-Item -LiteralPath "Env:$name" -Value $savedEnvironment[$name] }
    }
    if (Test-Path -LiteralPath $ownerRoot -PathType Container) {
        $resolvedOwnerRoot = (Resolve-Path -LiteralPath $ownerRoot).Path
        $resolvedQaParent = (Resolve-Path -LiteralPath $qaParent).Path
        $markerText = if (Test-Path -LiteralPath $ownerMarker -PathType Leaf) { [System.IO.File]::ReadAllText($ownerMarker) } else { '' }
        if ((Split-Path $resolvedOwnerRoot -Parent) -ceq $resolvedQaParent -and
            (Split-Path $resolvedOwnerRoot -Leaf) -cmatch '^pkg-[a-f0-9]{12}$' -and
            $markerText -ceq '{"owner":"iz-cna-installer-packaging-test-v1"}' -and
            -not ((Get-Item -LiteralPath $resolvedOwnerRoot).Attributes -band [System.IO.FileAttributes]::ReparsePoint)) {
            Remove-Item -LiteralPath $resolvedOwnerRoot -Recurse -Force
        } else {
            Write-Warning 'Owned test root cleanup was refused because its identity did not validate.'
        }
    }
}
