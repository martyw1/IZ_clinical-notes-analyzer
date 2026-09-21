Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'maintenance-common.psm1')

function Get-IzSourceReparseTag {
    param([string]$Path)
    if (-not ('IzPackageSource.Native' -as [type])) {
        Add-Type -TypeDefinition @'
using System;
using System.ComponentModel;
using System.Collections.Generic;
using System.IO;
using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;
namespace IzPackageSource {
    public static class Native {
        [StructLayout(LayoutKind.Sequential)]
        private struct TagInfo { public uint Attributes; public uint Tag; }
        [StructLayout(LayoutKind.Sequential, CharSet=CharSet.Unicode)]
        private struct FindData {
            public uint Attributes;
            public System.Runtime.InteropServices.ComTypes.FILETIME Created, Accessed, Written;
            public uint SizeHigh, SizeLow, Reserved0, Reserved1;
            [MarshalAs(UnmanagedType.ByValTStr, SizeConst=260)] public string Name;
            [MarshalAs(UnmanagedType.ByValTStr, SizeConst=14)] public string Alternate;
        }
        [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)]
        private static extern IntPtr FindFirstFile(string path, out FindData data);
        [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)]
        private static extern bool FindNextFile(IntPtr handle, out FindData data);
        [DllImport("kernel32.dll")] private static extern bool FindClose(IntPtr handle);
        [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)]
        private static extern bool CopyFile(string source, string destination, bool failIfExists);
        [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)]
        private static extern uint GetFileAttributes(string path);
        [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)]
        private static extern SafeFileHandle CreateFile(string path, uint access, uint share, IntPtr security, uint creation, uint flags, IntPtr template);
        [DllImport("kernel32.dll", SetLastError=true)]
        private static extern bool GetFileInformationByHandleEx(SafeFileHandle file, int kind, out TagInfo info, uint size);
        private static string Extended(string path) { return @"\\?\" + path; }
        public static uint Attributes(string path) {
            uint value=GetFileAttributes(Extended(path));
            if(value==0xffffffff) throw new Win32Exception(Marshal.GetLastWin32Error());
            return value;
        }
        public static string[] Entries(string path) {
            var result=new List<string>(); FindData data;
            IntPtr handle=FindFirstFile(Extended(path)+@"\*",out data);
            if(handle==new IntPtr(-1)) throw new Win32Exception(Marshal.GetLastWin32Error());
            try {
                do { if(data.Name!="." && data.Name!="..") result.Add(path+@"\"+data.Name); }
                while(FindNextFile(handle,out data));
                if(Marshal.GetLastWin32Error()!=18) throw new Win32Exception(Marshal.GetLastWin32Error());
            } finally { FindClose(handle); }
            return result.ToArray();
        }
        public static byte[] ManifestBytes(string path) {
            using(var handle=CreateFile(Extended(path),0x80000000,1,IntPtr.Zero,3,0,IntPtr.Zero)) {
                if(handle.IsInvalid) throw new Win32Exception(Marshal.GetLastWin32Error());
                using(var input=new FileStream(handle,FileAccess.Read)) {
                    if(input.Length>16777216) throw new InvalidDataException("PACKAGE_MANIFEST_TOO_LARGE");
                    using(var output=new MemoryStream()) { input.CopyTo(output);return output.ToArray(); }
                }
            }
        }
        public static void Copy(string source,string destination) {
            if(!CopyFile(Extended(source),Extended(destination),true)) throw new Win32Exception(Marshal.GetLastWin32Error());
        }
        public static uint ReparseTag(string path) {
            using (var file = CreateFile(Extended(path), 0, 7, IntPtr.Zero, 3, 0x02200000, IntPtr.Zero)) {
                if (file.IsInvalid) throw new Win32Exception(Marshal.GetLastWin32Error());
                TagInfo info;
                if (!GetFileInformationByHandleEx(file, 9, out info, 8)) throw new Win32Exception(Marshal.GetLastWin32Error());
                return info.Tag;
            }
        }
    }
}
'@
    }
    return [IzPackageSource.Native]::ReparseTag($Path)
}

function Get-IzPackageSourceRoot {
    param([string]$Path)
    Assert-IzPathSyntax $Path
    $root = [IO.Path]::GetFullPath($Path).TrimEnd('\')
    if (-not (Test-Path -LiteralPath $root -PathType Container)) { throw 'PACKAGE_SOURCE_MISSING' }
    return $root
}

function Assert-IzReadablePackageMember {
    param([string]$Root, [string]$Path)
    $full = $Path
    if (-not $full.StartsWith($Root + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'PACKAGE_SOURCE_OUTSIDE_ROOT' }
    $cursor = $Root
    foreach ($part in $full.Substring($Root.Length + 1).Split('\')) {
        $cursor = Join-Path $cursor $part
        if (([IzPackageSource.Native]::Attributes($cursor) -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            $tag = [uint32](Get-IzSourceReparseTag $cursor)
            if (($tag -band [uint32]4294905855) -ne [uint32]2415919130) { throw 'PACKAGE_MEMBER_REPARSE_POINT' }
        }
    }
}

function Get-IzPackageSourceFiles {
    param([string]$Root)
    $pending = [Collections.Generic.Stack[string]]::new()
    $pending.Push($Root)
    $files = [Collections.Generic.List[string]]::new()
    $visited = 0
    while ($pending.Count) {
        $directory = $pending.Pop()
        foreach ($item in [IzPackageSource.Native]::Entries($directory)) {
            $visited++
            if ($visited -gt 20000) { throw 'PACKAGE_SOURCE_TOO_LARGE' }
            Assert-IzReadablePackageMember $Root $item
            if (([IzPackageSource.Native]::Attributes($item) -band [IO.FileAttributes]::Directory) -ne 0) { $pending.Push($item) }
            else { $files.Add($item.Substring($Root.Length + 1).Replace('\', '/')) }
        }
    }
    return @($files.ToArray())
}

function New-IzPackageStage {
    param([string]$SourceRoot)
    $source = Get-IzPackageSourceRoot $SourceRoot
    [void](Get-IzSourceReparseTag $source)
    $manifestPath = Join-Path $source 'release-manifest.json'
    Assert-IzReadablePackageMember $source $manifestPath
    $manifestBytes = [IzPackageSource.Native]::ManifestBytes($manifestPath)
    $manifest = ConvertTo-IzManifest ([Text.UTF8Encoding]::new($false, $true).GetString($manifestBytes) | ConvertFrom-Json -ErrorAction Stop)
    if (@($manifest.files).Count -gt 10000) { throw 'PACKAGE_SOURCE_TOO_LARGE' }
    $expected = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
    [void]$expected.Add('release-manifest.json')
    foreach ($record in $manifest.files) { [void]$expected.Add([string]$record.path) }
    $actual = @(Get-IzPackageSourceFiles $source)
    if ($actual.Count -ne $expected.Count -or @($actual | Where-Object { -not $expected.Contains($_) }).Count) { throw 'PACKAGE_SOURCE_FILE_SET_MISMATCH' }
    $parent = Get-IzCanonicalPath ([IO.Path]::GetTempPath())
    Assert-IzCurrentUserOwner $parent
    $identifier = [Guid]::NewGuid().ToString('N')
    $root = Get-IzCanonicalPath (Join-Path $parent ('IZ-CNA-Package-' + $identifier)) -AllowMissingLeaf
    $owner = Get-IzCurrentUserSid
    $security = [Security.AccessControl.DirectorySecurity]::new()
    $security.SetAccessRuleProtection($true, $false)
    $sid = [Security.Principal.SecurityIdentifier]::new($owner)
    $security.SetOwner($sid)
    $security.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new($sid, 'FullControl', 'ContainerInherit,ObjectInherit', 'None', 'Allow'))
    [void][IO.Directory]::CreateDirectory($root, $security)
    $package = Join-Path $root 'package'
    $stage = [pscustomobject]@{ root=$root; package_root=$package; parent=$parent; identifier=$identifier; owner=$owner; files=@('owner.json') }
    $created = [Collections.Generic.List[string]]::new()
    $created.Add('owner.json')
    [IO.File]::WriteAllText((Join-Path $root 'owner.json'), (@{schema='iz-cna-package-stage-v1';id=$identifier;owner=$owner} | ConvertTo-Json -Compress), [Text.UTF8Encoding]::new($false))
    try {
        [void][IO.Directory]::CreateDirectory($package)
        [IO.File]::WriteAllBytes((Join-Path $package 'release-manifest.json'), $manifestBytes)
        $created.Add('package/release-manifest.json')
        foreach ($record in $manifest.files) {
            $sourceFile = Join-Path $source $record.path.Replace('/', '\')
            Assert-IzReadablePackageMember $source $sourceFile
            $destination = Assert-IzContainedPath (Join-Path $package $record.path.Replace('/', '\')) $package -AllowMissingLeaf
            [void][IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($destination))
            $created.Add('package/' + $record.path)
            [IzPackageSource.Native]::Copy($sourceFile, $destination)
            if ((Get-Item -LiteralPath $destination).Length -ne [long]$record.length -or (Get-IzFileSha256 $destination) -cne $record.sha256) { throw 'PACKAGE_SOURCE_HASH_MISMATCH' }
        }
        [void](Test-IzReleasePayload $package (Read-IzReleaseManifest $package))
        $stage.files = @($created.ToArray())
        return $stage
    } catch {
        $stage.files = @($created.ToArray())
        [void](Remove-IzPackageStage $stage)
        throw
    }
}

function Remove-IzPackageStage {
    param([object]$Stage)
    if (-not $Stage -or -not (Test-Path -LiteralPath $Stage.root)) { return $true }
    try {
        $root = Get-IzCanonicalPath $Stage.root
        if ((Split-Path $root -Parent) -ine $Stage.parent -or (Split-Path $root -Leaf) -cne ('IZ-CNA-Package-' + $Stage.identifier)) { return $false }
        Assert-IzCurrentUserOwner $root
        $marker = [IO.File]::ReadAllText((Join-Path $root 'owner.json')) | ConvertFrom-Json
        if ($marker.schema -cne 'iz-cna-package-stage-v1' -or $marker.id -cne $Stage.identifier -or $marker.owner -cne $Stage.owner) { return $false }
        $allowed = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
        $allowedDirectories = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
        [void]$allowedDirectories.Add('package')
        foreach ($name in $Stage.files) {
            [void]$allowed.Add([string]$name)
            $parentName = [IO.Path]::GetDirectoryName($name).Replace('\', '/')
            while ($parentName) {
                [void]$allowedDirectories.Add($parentName)
                $parentName = [IO.Path]::GetDirectoryName($parentName).Replace('\', '/')
            }
        }
        $directories = [Collections.Generic.List[string]]::new()
        $pending = [Collections.Generic.Stack[string]]::new()
        $pending.Push($root)
        while ($pending.Count) {
            $directory = $pending.Pop()
            foreach ($item in @(Get-ChildItem -LiteralPath $directory -Force)) {
                if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { return $false }
                if ($item.PSIsContainer) {
                    if (-not $allowedDirectories.Contains($item.FullName.Substring($root.Length + 1).Replace('\', '/'))) { return $false }
                    $pending.Push($item.FullName); $directories.Add($item.FullName)
                }
                elseif (-not $allowed.Contains($item.FullName.Substring($root.Length + 1).Replace('\', '/'))) { return $false }
            }
        }
        foreach ($name in @($Stage.files | Where-Object { $_ -ne 'owner.json' })) { $file=Join-Path $root $name.Replace('/', '\'); if (Test-Path -LiteralPath $file -PathType Leaf) { [IO.File]::Delete($file) } }
        foreach ($directory in @($directories.ToArray() | Sort-Object Length -Descending)) { [IO.Directory]::Delete($directory, $false) }
        [IO.File]::Delete((Join-Path $root 'owner.json'))
        [IO.Directory]::Delete($root, $false)
        return $true
    } catch { return $false }
}

Export-ModuleMember -Function New-IzPackageStage, Remove-IzPackageStage
