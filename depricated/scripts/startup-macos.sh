#!/usr/bin/env bash
set -Eeuo pipefail

cat >&2 <<'EOF'
[deprecated] scripts/startup-macos.sh is a legacy Docker/PostgreSQL bootstrap.

Version 1.3.0's current supported product path is the local Windows desktop
runtime started through scripts/Start-IZ-Clinical-Notes-Analyzer.cmd or
scripts/startup-windows-local.ps1.

The current branch does not contain an active root full-stack docker-compose.yml.
Legacy Docker/PostgreSQL/nginx artifacts are preserved under depriceated/ for
history and rollback reference only.

Do not use this script unless R3 explicitly restores Docker/server deployment
and updates README, CI, deployment docs, tests, and release instructions together.
EOF

exit 1
