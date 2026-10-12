[CmdletBinding(SupportsShouldProcess)]
param([string]$DesktopPath = [Environment]::GetFolderPath('Desktop'))

# Source-checkout helper: creates shortcuts only; never starts jobs or changes data.
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
if (-not (Test-Path -LiteralPath $DesktopPath -PathType Container)) { throw 'Desktop directory does not exist.' }
$powershell = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$oneDrive = $env:OneDriveCommercial
if (-not $oneDrive) { $oneDrive = $env:OneDrive }
$items = @(
    @('(1) Start IZ Clinical Notes Analyzer', (Join-Path $PSScriptRoot 'Start-IZ-Clinical-Notes-Analyzer.cmd'), '-SkipFrontendBuild -NoPause'),
    @('(2) Stop IZ Clinical Notes Analyzer', (Join-Path $PSScriptRoot 'Stop-IZ-Clinical-Notes-Analyzer.cmd'), '-NoRestartPrompt -NoPause'),
    @('(3) Collect IZ Diagnostics', (Join-Path $PSScriptRoot 'Collect-IZ-Clinical-Notes-Analyzer-Diagnostics.cmd'), '-NoPause'),
    @('(4) Quick Assist - R3 Support', (Join-Path $env:SystemRoot 'explorer.exe'), 'shell:AppsFolder\MicrosoftCorporationII.QuickAssist_8wekyb3d8bbwe!App'),
    @('(5) Short Intro Video', (Join-Path $repo 'docs\help\R3-Treatment-Plan-Audit-Quick-Start.mp4'), ''),
    @('(6) IZ Clinical Notes Analyzer User Guide', (Join-Path $repo 'docs\guides\current\Marleigh-Setup-Install-and-User-Guide.html'), ''),
    @('(7) Reset IZ Administrator Password', $powershell, ('-NoProfile -NoExit -ExecutionPolicy Bypass -File "' + (Join-Path $PSScriptRoot 'update-local-admin.ps1') + '"')),
    @('(9) Restore IZ Data from ZIP', $powershell, ('-NoProfile -NoExit -ExecutionPolicy Bypass -File "' + (Join-Path $PSScriptRoot 'restore-onedrive-zip.ps1') + '"'))
)
if ($oneDrive -and (Test-Path -LiteralPath $oneDrive -PathType Container)) {
    $items += ,@('(8) Back Up IZ Data to OneDrive', $powershell, ('-NoProfile -NoExit -ExecutionPolicy Bypass -File "' + (Join-Path $PSScriptRoot 'backup-onedrive-zip.ps1') + '" -Destination "' + (Join-Path $oneDrive 'IZ Clinical Notes Analyzer Backups') + '"'))
} else { Write-Warning 'OneDrive folder is unavailable; backup shortcut (8) was skipped.' }
$shell = New-Object -ComObject WScript.Shell
foreach ($item in $items) {
    if (-not (Test-Path -LiteralPath $item[1] -PathType Leaf)) { throw "Missing shortcut target: $($item[0])" }
    $path = Join-Path $DesktopPath ($item[0] + '.lnk')
    if ($PSCmdlet.ShouldProcess($path, 'Create or update source shortcut')) {
        $shortcut = $shell.CreateShortcut($path)
        $shortcut.TargetPath = $item[1]
        $shortcut.Arguments = $item[2]
        $shortcut.WorkingDirectory = $repo
        $shortcut.Save()
    }
}
