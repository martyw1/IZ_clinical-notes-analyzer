Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

function New-IzVersionError {
    param([string]$Reason)
    $exception = [IO.InvalidDataException]::new($Reason)
    $exception.Data['iz_reason'] = $Reason
    $exception.Data['iz_exit_code'] = 20
    return $exception
}

function ConvertTo-IzSemanticVersion {
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$Version)
    $pattern = '^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$'
    $match = [regex]::Match($Version, $pattern, [Text.RegularExpressions.RegexOptions]::CultureInvariant)
    if (-not $match.Success) { throw (New-IzVersionError 'VERSION_INVALID') }
    $pre = if ($match.Groups[4].Success) { @($match.Groups[4].Value -split '\.') } else { @() }
    foreach ($identifier in $pre) {
        if ($identifier -match '^[0-9]+$' -and $identifier.Length -gt 1 -and $identifier[0] -eq '0') {
            throw (New-IzVersionError 'VERSION_INVALID')
        }
    }
    return [pscustomobject][ordered]@{
        original=$Version
        major=$match.Groups[1].Value
        minor=$match.Groups[2].Value
        patch=$match.Groups[3].Value
        prerelease=$pre
        build_metadata=$(if ($match.Groups[5].Success) { $match.Groups[5].Value } else { $null })
    }
}

function ConvertTo-IzBuildVersion {
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$Build)
    $match = [regex]::Match($Build, '^([0-9]{4})\.([0-9]{2})\.([0-9]{2})\.(0|[1-9][0-9]*)$', [Text.RegularExpressions.RegexOptions]::CultureInvariant)
    if (-not $match.Success) { throw (New-IzVersionError 'BUILD_INVALID') }
    $parts = @([int]$match.Groups[1].Value,[int]$match.Groups[2].Value,[int]$match.Groups[3].Value,[long]$match.Groups[4].Value)
    if ($parts[1] -lt 1 -or $parts[1] -gt 12 -or $parts[2] -lt 1 -or $parts[2] -gt 31) { throw (New-IzVersionError 'BUILD_INVALID') }
    return [pscustomobject][ordered]@{ original=$Build; year=$parts[0]; month=$parts[1]; day=$parts[2]; revision=$parts[3] }
}

function Compare-IzNumericText {
    param([string]$Left,[string]$Right)
    $leftTrim = $Left.TrimStart('0'); if (-not $leftTrim) { $leftTrim='0' }
    $rightTrim = $Right.TrimStart('0'); if (-not $rightTrim) { $rightTrim='0' }
    if ($leftTrim.Length -lt $rightTrim.Length) { return -1 }
    if ($leftTrim.Length -gt $rightTrim.Length) { return 1 }
    return [Math]::Sign([StringComparer]::Ordinal.Compare($leftTrim,$rightTrim))
}

function Compare-IzSemanticVersion {
    param([object]$Left,[object]$Right)
    foreach ($name in @('major','minor','patch')) {
        $value = Compare-IzNumericText ([string]$Left.$name) ([string]$Right.$name)
        if ($value) { return $value }
    }
    $leftPre=@($Left.prerelease); $rightPre=@($Right.prerelease)
    if (-not $leftPre.Count -and -not $rightPre.Count) { return 0 }
    if (-not $leftPre.Count) { return 1 }
    if (-not $rightPre.Count) { return -1 }
    $count=[Math]::Min($leftPre.Count,$rightPre.Count)
    for($index=0;$index -lt $count;$index++) {
        $a=[string]$leftPre[$index]; $b=[string]$rightPre[$index]
        $aNumeric=$a -match '^[0-9]+$'; $bNumeric=$b -match '^[0-9]+$'
        if ($aNumeric -and $bNumeric) { $value=Compare-IzNumericText $a $b }
        elseif ($aNumeric) { $value=-1 }
        elseif ($bNumeric) { $value=1 }
        else { $value=[Math]::Sign([StringComparer]::Ordinal.Compare($a,$b)) }
        if ($value) { return $value }
    }
    return [Math]::Sign($leftPre.Count-$rightPre.Count)
}

function Compare-IzBuildVersion {
    param([object]$Left,[object]$Right)
    foreach($name in @('year','month','day','revision')) {
        if ($Left.$name -lt $Right.$name) { return -1 }
        if ($Left.$name -gt $Right.$name) { return 1 }
    }
    return 0
}

function New-IzReleaseIdentity {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$Version,
        [Parameter(Mandatory)][string]$Build,
        [Parameter(Mandatory)][ValidateRange(0,[int]::MaxValue)][int]$InstallerRevision,
        [Parameter(Mandatory)][string]$PayloadIdentity
    )
    [void](ConvertTo-IzSemanticVersion $Version)
    [void](ConvertTo-IzBuildVersion $Build)
    if ($PayloadIdentity -notmatch '^[0-9a-f]{64}$') { throw (New-IzVersionError 'PAYLOAD_IDENTITY_INVALID') }
    return [pscustomobject][ordered]@{ version=$Version; build=$Build; installer_revision=$InstallerRevision; payload_identity=$PayloadIdentity }
}

function Assert-IzReleaseIdentityObject {
    param([object]$Identity)
    if (-not $Identity) { throw (New-IzVersionError 'RELEASE_IDENTITY_INVALID') }
    $names=@($Identity.PSObject.Properties.Name); $expected=@('version','build','installer_revision','payload_identity')
    if ($names.Count -ne 4 -or @($expected | Where-Object { $_ -notin $names }).Count) { throw (New-IzVersionError 'RELEASE_IDENTITY_INVALID') }
    if($Identity.version -isnot [string] -or $Identity.build -isnot [string] -or $Identity.payload_identity -isnot [string] -or
       ($Identity.installer_revision -isnot [int] -and $Identity.installer_revision -isnot [long]) -or [long]$Identity.installer_revision -lt 0 -or [long]$Identity.installer_revision -gt [int]::MaxValue){throw(New-IzVersionError 'RELEASE_IDENTITY_INVALID')}
    return New-IzReleaseIdentity -Version ([string]$Identity.version) -Build ([string]$Identity.build) -InstallerRevision ([int]$Identity.installer_revision) -PayloadIdentity ([string]$Identity.payload_identity)
}

function Compare-IzReleaseIdentity {
    [CmdletBinding()]
    param([Parameter(Mandatory,Position=0)][object]$Left,[Parameter(Mandatory,Position=1)][object]$Right)
    $leftIdentity=Assert-IzReleaseIdentityObject $Left; $rightIdentity=Assert-IzReleaseIdentityObject $Right
    $value=Compare-IzSemanticVersion (ConvertTo-IzSemanticVersion $leftIdentity.version) (ConvertTo-IzSemanticVersion $rightIdentity.version)
    if (-not $value) { $value=Compare-IzBuildVersion (ConvertTo-IzBuildVersion $leftIdentity.build) (ConvertTo-IzBuildVersion $rightIdentity.build) }
    if (-not $value) { $value=[Math]::Sign($leftIdentity.installer_revision-$rightIdentity.installer_revision) }
    if (-not $value -and $leftIdentity.payload_identity -ne $rightIdentity.payload_identity) { throw (New-IzVersionError 'ARTIFACT_COLLISION') }
    return $value
}

function Test-IzProductionVersionTransition {
    [CmdletBinding()]
    param([Parameter(Mandatory)][object]$SourceRelease,[Parameter(Mandatory)][object]$Manifest)
    $source=Assert-IzReleaseIdentityObject $SourceRelease
    if ($Manifest.version -cne '1.0.0' -or $Manifest.build -cne '2026.09.21.1' -or
        $Manifest.installer_revision -ne 1 -or $Manifest.release_channel -cne 'stable-local-desktop' -or
        $source.version -cnotin @('2.0.0-beta.3','2.0.0-beta.4') -or $source.installer_revision -gt 1) { return $false }
    $build=ConvertTo-IzBuildVersion $source.build
    return ((Compare-IzBuildVersion $build (ConvertTo-IzBuildVersion '2026.09.03.1')) -ge 0 -and
        (Compare-IzBuildVersion $build (ConvertTo-IzBuildVersion '2026.09.15.2')) -le 0)
}

function Test-IzReleaseCompatibility {
    param([object]$SourceRelease,[int]$SourceSchema,[object]$Manifest,[switch]$Repair)
    $source=Assert-IzReleaseIdentityObject $SourceRelease
    if ($Repair -and $source.version -eq $Manifest.version -and $source.build -eq $Manifest.build -and
        $source.installer_revision -eq $Manifest.installer_revision) {
        if ($source.payload_identity -ne $Manifest.payload_identity) { throw (New-IzVersionError 'ARTIFACT_COLLISION') }
        return $true
    }
    $compat=$Manifest.compatibility
    $sourceVersion=ConvertTo-IzSemanticVersion $source.version
    $sourceBuild=ConvertTo-IzBuildVersion $source.build
    if ((Compare-IzSemanticVersion $sourceVersion (ConvertTo-IzSemanticVersion $compat.source_version_minimum)) -lt 0 -or
        (Compare-IzSemanticVersion $sourceVersion (ConvertTo-IzSemanticVersion $compat.source_version_maximum)) -gt 0 -or
        (Compare-IzBuildVersion $sourceBuild (ConvertTo-IzBuildVersion $compat.source_build_minimum)) -lt 0 -or
        (Compare-IzBuildVersion $sourceBuild (ConvertTo-IzBuildVersion $compat.source_build_maximum)) -gt 0 -or
        $SourceSchema -lt [int]$compat.source_schema_minimum -or $SourceSchema -gt [int]$compat.source_schema_maximum) {
        throw (New-IzVersionError 'SOURCE_NOT_COMPATIBLE')
    }
    return $true
}

Export-ModuleMember -Function ConvertTo-IzSemanticVersion,ConvertTo-IzBuildVersion,New-IzReleaseIdentity,Compare-IzReleaseIdentity,Test-IzReleaseCompatibility,Test-IzProductionVersionTransition,Assert-IzReleaseIdentityObject
