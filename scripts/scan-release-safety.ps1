[CmdletBinding()]
param(
    [ValidateSet('Repository', 'Directory', 'Zip')][string]$Scope = 'Repository',
    [string]$Path = '',
    [string]$ExpectedHead = '',
    [switch]$AllowDirty
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
. (Join-Path $PSScriptRoot 'release-safety.ps1')

try {
    switch ($Scope) {
        'Repository' {
            $target = if ($Path) { $Path } else { $repositoryRoot }
            Assert-NoForbiddenRepositoryIndexItems -RepositoryRoot $target -ExpectedHead $ExpectedHead -AllowDirty:$AllowDirty
        }
        'Directory' {
            if (-not $Path) { throw 'directory_path_required' }
            Assert-NoForbiddenReleaseItems -TargetPackageDir $Path
        }
        'Zip' {
            if (-not $Path) { throw 'zip_path_required' }
            Assert-ZipHasNoForbiddenItems -ZipPath $Path
        }
    }
    Write-Output 'schema=release-safety-v1'
    Write-Output "scope=$($Scope.ToLowerInvariant())"
    Write-Output 'result=PASS'
    exit 0
} catch {
    Write-Output 'schema=release-safety-v1'
    Write-Output "scope=$($Scope.ToLowerInvariant())"
    Write-Output 'result=FAIL'
    Write-Output "reason=$($_.Exception.Message)"
    exit 2
}
