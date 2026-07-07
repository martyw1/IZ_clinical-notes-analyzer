<#
Compatibility wrapper.

The original backend-driving script has been intentionally replaced. This now launches the
standalone remote Alleva diagnostic harness, which bypasses the local app and calls Alleva
directly while preserving the app's treatment-plan retrieval assumptions.
#>
[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments=$true)]
    [string[]]$RemainingArguments
)
$scriptPath = Join-Path $PSScriptRoot 'Invoke-AllevaRemoteDiagnostics.ps1'
if (-not (Test-Path -LiteralPath $scriptPath)) { throw "Missing $scriptPath" }
& $scriptPath @RemainingArguments
