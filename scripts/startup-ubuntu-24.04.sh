#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="${ROOT_DIR}/logs"
mkdir -p "${LOG_DIR}"
LOG_FILE="${LOG_DIR}/startup-ubuntu-$(date +%Y%m%d-%H%M%S).log"
exec > >(tee -a "${LOG_FILE}") 2>&1

trap 'echo "[ERROR] Startup failed on line $LINENO. Review log: ${LOG_FILE}"' ERR

NON_INTERACTIVE="${NON_INTERACTIVE:-1}"
ENABLE_HOST_VENV="${ENABLE_HOST_VENV:-0}"
RESET_INTERNAL_DB_ON_CREDENTIAL_MISMATCH="${RESET_INTERNAL_DB_ON_CREDENTIAL_MISMATCH:-0}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --interactive) NON_INTERACTIVE=0 ;;
    --non-interactive) NON_INTERACTIVE=1 ;;
    --enable-host-venv) ENABLE_HOST_VENV=1 ;;
    --disable-host-venv) ENABLE_HOST_VENV=0 ;;
    *) echo "Unknown flag: $1" >&2; exit 1 ;;
  esac
  shift
done

info() { echo "[$(date +'%F %T')] [INFO] $*" >&2; }
warn() { echo "[$(date +'%F %T')] [WARN] $*" >&2; }
pass() { echo "[$(date +'%F %T')] [PASS] $*" >&2; }

is_port_busy() { ss -ltn "( sport = :$1 )" | grep -q LISTEN; }

pick_next_open_port() {
  local start="$1" candidate
  for candidate in $(seq "$start" $((start + 40))); do
    if ! is_port_busy "$candidate"; then
      echo "$candidate"
      return 0
    fi
  done
  return 1
}

set_env_value() {
  local key="$1" value="$2"
  if grep -q "^${key}=" .env; then
    sed -i "s#^${key}=.*#${key}=${value}#" .env
  else
    echo "${key}=${value}" >> .env
  fi
}

env_value() {
  awk -F= -v k="$1" '$1==k{print substr($0, index($0,$2))}' .env | tail -n1
}

resolve_port() {
  local key="$1" default="$2" requested
  requested="${!key:-}"
  requested="${requested:-$(env_value "$key")}"
  requested="${requested:-$default}"
  if is_port_busy "$requested"; then
    local fallback
    fallback="$(pick_next_open_port $((requested + 1)))"
    warn "${key} ${requested} busy; auto-selected ${fallback}."
    echo "$fallback"
    return 0
  fi
  echo "$requested"
}

prepare_host_venv_if_enabled() {
  [[ "$ENABLE_HOST_VENV" == "1" ]] || return 0
  info 'Preparing optional backend host virtualenv'
  python3 -m venv backend/.venv
  source backend/.venv/bin/activate
  python -m pip install --upgrade pip
  python -m pip install -r backend/requirements.txt
  deactivate
}

print_db_mode_summary() {
  local db_mode db_host db_name db_user
  db_mode="$(env_value DATABASE_HOST_MODE)"
  db_mode="${db_mode:-internal}"
  db_host="$(python3 - <<'PY'
from urllib.parse import urlsplit
import os
url = os.environ.get("DATABASE_URL", "")
if not url:
    print("<unset>")
else:
    try:
        print(urlsplit(url).hostname or "<unset>")
    except Exception:
        print("<invalid>")
PY
)"
  db_name="$(env_value POSTGRES_DB)"
  db_user="$(env_value POSTGRES_USER)"
  info "DB mode: ${db_mode} (USE_INTERNAL_POSTGRES=${USE_INTERNAL_POSTGRES})"
  info "Expected DB target host: ${db_host}"
  info "Configured DB name/user: ${db_name:-<unset>}/${db_user:-<unset>}"
}

maybe_reset_internal_db_on_credential_mismatch() {
  local backend_logs="$1"
  if [[ "$backend_logs" == *"password authentication failed for user"* ]] && [[ "$RESET_INTERNAL_DB_ON_CREDENTIAL_MISMATCH" == "1" ]]; then
    warn 'Credential mismatch detected and RESET_INTERNAL_DB_ON_CREDENTIAL_MISMATCH=1; resetting internal DB volume.'
    docker compose --profile internal-db down -v
  fi
}

print_db_failure_diagnostics() {
  local backend_logs="$1" db_logs="$2"
  if [[ "$backend_logs" == *"password authentication failed for user"* ]]; then
    warn 'Detected DB credential mismatch.'
    echo '[DIAG] Internal DB volumes apply POSTGRES_USER/POSTGRES_PASSWORD only on first initialization.' >&2
    echo '[DIAG] Option A (safe): update DATABASE_URL/.env credentials to match existing DB role/password.' >&2
    echo '[DIAG] Option B (destructive): export RESET_INTERNAL_DB_ON_CREDENTIAL_MISMATCH=1 and rerun to recreate DB volume.' >&2
  elif [[ "$backend_logs" == *"could not translate host name"* ]] || [[ "$backend_logs" == *"Name or service not known"* ]]; then
    warn 'Detected DB host resolution/connectivity failure. Check DATABASE_URL host and DATABASE_HOST_MODE.'
  elif [[ "$backend_logs" == *"does not exist"* ]]; then
    warn 'Detected missing role or database. Ensure target PostgreSQL has the configured user/database.'
  fi

  if [[ -n "$db_logs" ]] && [[ "$db_logs" == *"database system is ready to accept connections"* ]]; then
    info 'Internal Postgres container is reachable; failure is likely credentials/database/role mismatch.'
  fi
}

cd "$ROOT_DIR"
info "Starting Ubuntu 24.04 bootstrap from ${ROOT_DIR}"

[[ -f .env ]] || { cp .env.example .env; info 'Created .env from .env.example'; }

BACKEND_PORT="$(resolve_port BACKEND_PORT 8000)"
FRONTEND_PORT="$(resolve_port FRONTEND_PORT 5173)"
if [[ "$BACKEND_PORT" == "$FRONTEND_PORT" ]]; then
  FRONTEND_PORT="$(pick_next_open_port $((FRONTEND_PORT + 1)))"
  warn "Frontend port matched backend; switched to ${FRONTEND_PORT}."
fi

set_env_value BACKEND_PORT "$BACKEND_PORT"
set_env_value FRONTEND_PORT "$FRONTEND_PORT"
POSTGRES_VOLUME_NAME="${POSTGRES_VOLUME_NAME:-$(env_value POSTGRES_VOLUME_NAME)}"
POSTGRES_VOLUME_NAME="${POSTGRES_VOLUME_NAME:-iz_clinical_notes_analyzer_pgdata_app}"
set_env_value POSTGRES_VOLUME_NAME "$POSTGRES_VOLUME_NAME"

USE_INTERNAL_POSTGRES="${USE_INTERNAL_POSTGRES:-$(env_value USE_INTERNAL_POSTGRES)}"
USE_INTERNAL_POSTGRES="${USE_INTERNAL_POSTGRES:-1}"
DATABASE_URL="${DATABASE_URL:-$(env_value DATABASE_URL)}"
export USE_INTERNAL_POSTGRES DATABASE_URL FRONTEND_PORT BACKEND_PORT

if ! command -v docker >/dev/null 2>&1; then
  warn 'Docker is required but not installed.'
  exit 1
fi

prepare_host_venv_if_enabled
print_db_mode_summary

compose_cmd=(docker compose)
if [[ "$USE_INTERNAL_POSTGRES" == "1" ]]; then
  compose_cmd+=(--profile internal-db)
fi

info 'Starting Docker Compose stack'
"${compose_cmd[@]}" pull || warn 'docker compose pull failed; continuing with local cache'
if ! "${compose_cmd[@]}" up -d --build; then
  warn 'docker compose up failed; collecting diagnostics.'
  backend_logs="$("${compose_cmd[@]}" logs --tail=200 backend 2>/dev/null || true)"
  db_logs="$(docker compose --profile internal-db logs --tail=200 db 2>/dev/null || true)"
  maybe_reset_internal_db_on_credential_mismatch "$backend_logs"
  if [[ "$RESET_INTERNAL_DB_ON_CREDENTIAL_MISMATCH" == "1" && "$USE_INTERNAL_POSTGRES" == "1" ]]; then
    "${compose_cmd[@]}" up -d --build || true
    backend_logs="$("${compose_cmd[@]}" logs --tail=200 backend 2>/dev/null || true)"
    db_logs="$(docker compose --profile internal-db logs --tail=200 db 2>/dev/null || true)"
  fi
  print_db_failure_diagnostics "$backend_logs" "$db_logs"
  "${compose_cmd[@]}" logs --tail=200 || true
  exit 1
fi

"${compose_cmd[@]}" ps

info 'Running smoke test'
if FRONTEND_PORT="$FRONTEND_PORT" ./scripts/smoke.sh; then
  pass 'Smoke test passed.'
else
  warn 'Smoke failed; collecting recent logs.'
  "${compose_cmd[@]}" logs --tail=200 || true
  exit 1
fi

pass "Startup complete."
pass "Frontend URL: http://localhost:${FRONTEND_PORT}"
pass "Backend URL: http://localhost:${BACKEND_PORT}"
pass "Log file: ${LOG_FILE}"
