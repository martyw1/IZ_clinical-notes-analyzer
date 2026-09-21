[CmdletBinding()]
param([Parameter(Mandatory)][string]$PackageRoot,[Parameter(Mandatory)][string]$CloudParent,[string]$ReportPath='')
Set-StrictMode -Version 2.0
$ErrorActionPreference='Stop'
Import-Module (Join-Path $PSScriptRoot '..\installer\maintenance-common.psm1') -Force
Import-Module (Join-Path $PSScriptRoot '..\installer\package-source.psm1') -Force
$checks=[Collections.Generic.List[string]]::new()
$identifier=[Guid]::NewGuid().ToString('N')
$fixture=Join-Path ([IO.Path]::GetTempPath()) ('IZ-Package-Test-'+$identifier)
$cloudFixture=Join-Path $CloudParent ('IZ Package Test & '+[char]0x00e9+' '+$identifier)
$stage=$null
function Assert-Test { param([bool]$Value,[string]$Name) if(-not $Value){throw ('ASSERTION_FAILED:'+ $Name)}; $checks.Add($Name) }
function Assert-Rejected { param([scriptblock]$Operation,[string]$Reason) $actual=''; try { & $Operation | Out-Null } catch { $actual=$_.Exception.Message }; Assert-Test ($actual -eq $Reason) $Reason }
try {
    [void][IO.Directory]::CreateDirectory($fixture)
    [void][IO.Directory]::CreateDirectory($cloudFixture)
    & robocopy $PackageRoot $fixture /E /NFL /NDL /NJH /NJS /NP | Out-Null
    if ($LASTEXITCODE -gt 7) { throw 'FIXTURE_COPY_FAILED' }
    & robocopy $PackageRoot $cloudFixture /E /NFL /NDL /NJH /NJS /NP | Out-Null
    if ($LASTEXITCODE -gt 7) { throw 'FIXTURE_COPY_FAILED' }
    foreach ($source in @($fixture,$cloudFixture)) {
        $stage=New-IzPackageStage $source
        Assert-Test (Test-IzReleasePayload $stage.package_root (Read-IzReleaseManifest $stage.package_root)) 'verified_staged_payload'
        Assert-Test (Remove-IzPackageStage $stage) 'staging_cleanup'
        Assert-Test (-not (Test-Path -LiteralPath $stage.root)) 'temporary_folder_removed'
        $stage=$null
    }
    $strictRejected=$false
    try { [void](Get-IzCanonicalPath $cloudFixture) } catch { $strictRejected=$_.Exception.Data['iz_reason'] -eq 'PATH_REPARSE_POINT' }
    Assert-Test $strictRejected 'cloud_source_reproduces_original_path_rejection'
    $target=Join-Path $fixture 'app\VERSION'
    $original=[IO.File]::ReadAllBytes($target)
    [IO.File]::AppendAllText($target,'tampered')
    Assert-Rejected { New-IzPackageStage $fixture } 'PACKAGE_SOURCE_HASH_MISMATCH'
    [IO.File]::WriteAllBytes($target,$original)
    [IO.File]::Delete($target)
    Assert-Rejected { New-IzPackageStage $fixture } 'PACKAGE_SOURCE_FILE_SET_MISMATCH'
    [IO.File]::WriteAllBytes($target,$original)
    $extra=Join-Path $fixture 'unexpected.txt'
    [IO.File]::WriteAllText($extra,'synthetic')
    Assert-Rejected { New-IzPackageStage $fixture } 'PACKAGE_SOURCE_FILE_SET_MISMATCH'
    [IO.File]::Delete($extra)
    $link=Join-Path $fixture 'linked-folder'
    [void](New-Item -ItemType Junction -Path $link -Target $cloudFixture)
    try { Assert-Rejected { New-IzPackageStage $fixture } 'PACKAGE_MEMBER_REPARSE_POINT' }
    finally { [IO.Directory]::Delete($link) }
    $stage=New-IzPackageStage $fixture
    [IO.File]::WriteAllText((Join-Path $stage.root 'unexpected.txt'),'synthetic')
    Assert-Test (-not (Remove-IzPackageStage $stage)) 'cleanup_refuses_unowned_file'
    [IO.File]::Delete((Join-Path $stage.root 'unexpected.txt'))
    Assert-Test (Remove-IzPackageStage $stage) 'cleanup_after_unowned_file_removed'
    $stage=$null
    $receipt=[ordered]@{status='passed';assertions=@($checks.ToArray());completed_utc=[DateTime]::UtcNow.ToString('o')}
    if($ReportPath){[IO.File]::WriteAllText([IO.Path]::GetFullPath($ReportPath),($receipt|ConvertTo-Json -Depth 4),[Text.UTF8Encoding]::new($false))}
    Write-Output ('PACKAGE_SOURCE_TESTS_PASS: '+$checks.Count)
} finally {
    if($stage){[void](Remove-IzPackageStage $stage)}
    foreach($root in @($fixture,$cloudFixture)) {
        $full=[IO.Path]::GetFullPath($root)
        if(-not $full.EndsWith($identifier,[StringComparison]::Ordinal)){throw 'TEST_CLEANUP_REFUSED'}
        if(Test-Path -LiteralPath $full){
            $cleanup=Join-Path ([IO.Path]::GetTempPath()) ('izp-'+[Guid]::NewGuid().ToString('N').Substring(0,8))
            if([IO.Path]::GetDirectoryName($cleanup) -ine [IO.Path]::GetTempPath().TrimEnd('\')){throw 'TEST_CLEANUP_REFUSED'}
            [IO.Directory]::Move($full,$cleanup)
            Remove-Item -LiteralPath $cleanup -Recurse -Force
        }
    }
}
