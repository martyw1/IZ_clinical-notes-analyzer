#!/bin/zsh
set -e

echo "Fetching latest remote state..."
git fetch origin

counts=$(git rev-list --left-right --count origin/main...main)
remoteAhead=$(echo "$counts" | awk '{print $1}')
localAhead=$(echo "$counts" | awk '{print $2}')

echo
echo "Remote ahead by: $remoteAhead commit(s)"
echo "Local ahead by:  $localAhead commit(s)"
echo

if [[ "$remoteAhead" -gt 0 && "$localAhead" -eq 0 ]]; then
  echo "Remote is newer. Pulling latest changes..."
  git pull --ff-only origin main
elif [[ "$localAhead" -gt 0 && "$remoteAhead" -eq 0 ]]; then
  echo "Local is newer. Pushing local commits..."
  git push origin main
elif [[ "$remoteAhead" -eq 0 && "$localAhead" -eq 0 ]]; then
  echo "Local and remote are already synchronized."
else
  echo "WARNING: Both local and remote have unique commits."
  echo "Manual review required. No pull or push was performed."
  git log --oneline --left-right origin/main...main
  exit 1
fi

echo
git status
git log --oneline --decorate -5
