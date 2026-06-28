$ErrorActionPreference = "Stop"

Write-Host "Fetching latest remote state..."
git fetch origin

$counts = git rev-list --left-right --count origin/main...main
$parts = $counts -split '\s+'

$remoteAhead = [int]$parts[0]
$localAhead  = [int]$parts[1]

Write-Host ""
Write-Host "Remote ahead by: $remoteAhead commit(s)"
Write-Host "Local ahead by:  $localAhead commit(s)"
Write-Host ""

if ($remoteAhead -gt 0 -and $localAhead -eq 0) {
    Write-Host "Remote is newer. Pulling latest changes..."
    git pull --ff-only origin main
}
elseif ($localAhead -gt 0 -and $remoteAhead -eq 0) {
    Write-Host "Local is newer. Pushing local commits..."
    git push origin main
}
elseif ($remoteAhead -eq 0 -and $localAhead -eq 0) {
    Write-Host "Local and remote are already synchronized."
}
else {
    Write-Host "WARNING: Both local and remote have unique commits."
    Write-Host "Manual review required. No pull or push was performed."
    git log --oneline --left-right origin/main...main
    exit 1
}

Write-Host ""
git status
git log --oneline --decorate -5
