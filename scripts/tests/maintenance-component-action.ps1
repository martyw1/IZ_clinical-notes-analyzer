[CmdletBinding()]
param(
    [Parameter(Mandatory)][ValidateSet('AutoInstall','Uninstall','RemoveData')][string]$Action,
    [Parameter(Mandatory)][string]$DispatcherPath,
    [Parameter(Mandatory)][string]$PackageRoot,
    [Parameter(Mandatory)][string]$ComponentTestRoot,
    [Parameter(Mandatory)][string]$ResultPath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$package = [IO.Path]::GetFullPath($PackageRoot).TrimEnd('\')
$dispatcher = [IO.Path]::GetFullPath($DispatcherPath)
$expectedDispatcher = Join-Path $package 'installer\maintenance-windows.ps1'
if (-not $dispatcher.Equals($expectedDispatcher, [StringComparison]::OrdinalIgnoreCase) -or
    -not (Test-Path -LiteralPath $dispatcher -PathType Leaf)) {
    throw 'COMPONENT_DISPATCHER_INVALID'
}
if (Test-Path -LiteralPath $ResultPath) { throw 'COMPONENT_RESULT_EXISTS' }

$requestedAction = $Action
$requestedResultPath = $ResultPath
. $dispatcher -NoRun
$context = Get-IzMaintenanceContext -PackageRoot $package -ComponentTestRoot $ComponentTestRoot
$result = Invoke-IzMaintenanceAction -Action $requestedAction -PackageRoot $package -NoPause -NonInteractive `
    -ResultPath $requestedResultPath -Context $context
if($result.transaction_id -and [int]$result.code -ne 0){
    $failureReference='transactions/'+$result.transaction_id+'/results/installer-failure.json'
    if($failureReference -in @($result.evidence)){
        $source=Assert-IzContainedPath (Join-Path $context.maintenance_root $failureReference.Replace('/','\')) $context.maintenance_root
        if(Test-Path -LiteralPath $source -PathType Leaf){
            $item=Get-Item -LiteralPath $source -Force
            if(($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -eq 0){
                $diagnosticPath=[IO.Path]::ChangeExtension($requestedResultPath,'installer-failure.json')
                [IO.File]::Copy($source,$diagnosticPath,$false)
            }
        }
    }
}
Write-Output ($result | ConvertTo-Json -Depth 8 -Compress)
exit [int]$result.code
