#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ROOT_DIR}/.env"
LOG_DIR="${ROOT_DIR}/logs"
mkdir -p "${LOG_DIR}"
LOG_FILE="${LOG_DIR}/startup-ubuntu-$(date +%Y%m%d-%H%M%S).log"
exec > >(tee -a "${LOG_FILE}") 2>&1

trap 'echo "[ERROR] Startup failed on line $LINENO. Review log: ${LOG_FILE}"' ERR

source "${ROOT_DIR}/scripts/lib/dedicated-postgres.sh"

NON_INTERACTIVE="${NON_INTERACTIVE:-1}"
ENABLE_HOST_VENV="${ENABLE_HOST_VENV:-0}"
RESET_DEDICATED_DB_VOLUME_ON_AUTH_FAILURE="${RESET_DEDICATED_DB_VOLUME_ON_AUTH_FAILURE:-0}"

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

resolve_port() {
  local key="$1" default="$2" requested
  requested="${!key:-}"
  requested="${requested:-$(startup_db_env_value "$ENV_FILE" "$key")}"
  requested="${requested:-$default}"
  if startup_db_is_port_busy "$requested"; then
    local fallback
    fallback="$(startup_db_pick_next_open_port $((requested + 1)))"
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
  local db_host db_name db_user db_port
  db_host="$(startup_db_env_value "$ENV_FILE" DATABASE_HOST)"
  db_port="$(startup_db_env_value "$ENV_FILE" DATABASE_PORT)"
  db_name="$(startup_db_env_value "$ENV_FILE" DATABASE_NAME)"
  db_user="$(startup_db_env_value "$ENV_FILE" DATABASE_USER)"
  info 'DB mode: dedicated application-owned PostgreSQL container'
  info "Expected DB target host: ${db_host:-<unset>}:${db_port:-<unset>}"
  info "Configured DB name/user: ${db_name:-<unset>}/${db_user:-<unset>}"
}

maybe_reset_dedicated_db_volume() {
  if [[ "$RESET_DEDICATED_DB_VOLUME_ON_AUTH_FAILURE" == "1" ]]; then
    warn 'RESET_DEDICATED_DB_VOLUME_ON_AUTH_FAILURE=1; recreating dedicated PostgreSQL volume.'
    docker compose down -v || true
    startup_db_bootstrap "$ROOT_DIR" "$ENV_FILE"
    return 0
  fi
  return 1
}

print_db_failure_diagnostics() {
  local backend_logs="$1"
  if [[ "$backend_logs" == *"password authentication failed for user"* ]]; then
    warn 'Detected DB credential mismatch.'
    echo '[DIAG] Dedicated Postgres volumes keep the original DATABASE_USER/DATABASE_PASSWORD after first initialization.' >&2
    echo '[DIAG] Option A (safe): restore the original DB credentials in .env.' >&2
    echo '[DIAG] Option B (destructive): export RESET_DEDICATED_DB_VOLUME_ON_AUTH_FAILURE=1 and rerun to recreate the DB volume.' >&2
  elif [[ "$backend_logs" == *"could not translate host name"* ]] || [[ "$backend_logs" == *"Name or service not known"* ]]; then
    warn 'Detected DB host resolution/connectivity failure.'
  elif [[ "$backend_logs" == *"does not exist"* ]]; then
    warn 'Detected missing database or role; the provisioning step may have failed.'
  fi
}

cd "$ROOT_DIR"
info "Starting Ubuntu 24.04 bootstrap from ${ROOT_DIR}"

[[ -f .env ]] || { cp .env.example .env; info 'Created .env from .env.example'; }

BACKEND_PORT="$(resolve_port BACKEND_PORT 8000)"
FRONTEND_PORT="$(resolve_port FRONTEND_PORT 5173)"
POSTGRES_PORT="$(resolve_port POSTGRES_PORT 5432)"
if [[ "$BACKEND_PORT" == "$FRONTEND_PORT" ]]; then
  FRONTEND_PORT="$(startup_db_pick_next_open_port $((FRONTEND_PORT + 1)))"
  warn "Frontend port matched backend; switched to ${FRONTEND_PORT}."
fi

startup_db_set_env_value "$ENV_FILE" BACKEND_PORT "$BACKEND_PORT"
startup_db_set_env_value "$ENV_FILE" FRONTEND_PORT "$FRONTEND_PORT"
startup_db_apply_env_defaults "$ENV_FILE" "$POSTGRES_PORT"
export FRONTEND_PORT BACKEND_PORT POSTGRES_PORT

if ! command -v docker >/dev/null 2>&1; then
  warn 'Docker is required but not installed.'
  exit 1
fi

prepare_host_venv_if_enabled
print_db_mode_summary

info 'Pulling latest container images where available'
docker compose pull || warn 'docker compose pull failed; continuing with local cache'

if ! startup_db_bootstrap "$ROOT_DIR" "$ENV_FILE"; then
  maybe_reset_dedicated_db_volume || exit 1
fi

info 'Starting Docker Compose stack'
if ! docker compose up -d --build; then
  warn 'docker compose up failed; collecting diagnostics.'
  backend_logs="$(docker compose logs --tail=200 backend 2>/dev/null || true)"
  print_db_failure_diagnostics "$backend_logs"
  docker compose logs --tail=200 || true
  exit 1
fi

docker compose ps

info 'Running smoke test'
if FRONTEND_PORT="$FRONTEND_PORT" ./scripts/smoke.sh; then
  pass 'Smoke test passed.'
else
  warn 'Smoke failed; collecting recent logs.'
  docker compose logs --tail=200 || true
  exit 1
fi

pass "Startup complete."
pass "Frontend URL: http://localhost:${FRONTEND_PORT}"
pass "Backend URL: http://localhost:${BACKEND_PORT}"
pass "Log file: ${LOG_FILE}"
