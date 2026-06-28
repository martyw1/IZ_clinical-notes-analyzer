#!/usr/bin/env bash
set -Eeuo pipefail

echo '[deprecated] scripts/startup-ubuntu-24.04.sh is a legacy Docker/PostgreSQL bootstrap.' >&2
echo 'Use the Version 1.3.0 Windows local desktop path instead: scripts/Start-IZ-Clinical-Notes-Analyzer.cmd or scripts/startup-windows-local.ps1.' >&2
echo 'Legacy server/container artifacts are preserved under depriceated/ for history only and are not current launch instructions.' >&2
exit 1
