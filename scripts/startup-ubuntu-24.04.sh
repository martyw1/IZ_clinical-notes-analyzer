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

print_db_auth_diagnostics() {
  local db_logs
  db_logs="$(docker compose logs --tail=200 db 2>/dev/null || true)"

  if [[ "$db_logs" == *"password authentication failed for user"* ]]; then
    warn 'Detected PostgreSQL password authentication failures.'
    warn 'Likely cause: existing Postgres volume initialized with different credentials than current .env/DATABASE_URL.'
    warn 'Postgres only applies POSTGRES_USER/POSTGRES_PASSWORD on first initialization of the data volume.'
    echo '[DIAG] Suggested fixes (choose one):' >&2
    echo '[DIAG]  1) Keep existing DB data: set DATABASE_URL / POSTGRES_PASSWORD in .env to match current DB credentials.' >&2
    echo '[DIAG]  2) Reset demo DB data and reinitialize with current .env credentials:' >&2
    echo '[DIAG]     docker compose down -v' >&2
    echo '[DIAG]     docker compose up -d --build' >&2
  fi
}

rebuild_database_url() {
  local user="$1"
  local password="$2"
  local db_name="$3"
  echo "postgresql+psycopg2://${user}:${password}@db:5432/${db_name}"
}

apply_option1_db_credential_fix() {
  local db_logs="$1"
  local current_db_url
  current_db_url="$(awk -F= '$1=="DATABASE_URL"{print substr($0, index($0,$2))}' .env | tail -n1)"

  # Option 1 from diagnostics: keep existing DB volume and align app credentials.
  # The most common drift is POSTGRES_USER/DATABASE_URL changed to "chart" while the
  # existing volume was initialized with default postgres/postgres credentials.
  if [[ "$db_logs" == *'Role "chart" does not exist'* ]] || [[ "$current_db_url" == *'://chart:'* ]]; then
    local db_name
    db_name="${POSTGRES_DB:-$(awk -F= '$1=="POSTGRES_DB"{print $2}' .env | tail -n1)}"
    db_name="${db_name:-optiflow}"

    warn 'Applying Option 1 auto-fix: aligning .env database credentials to existing default postgres role.'
    set_env_value POSTGRES_USER postgres
    set_env_value POSTGRES_PASSWORD postgres
    set_env_value DATABASE_URL "$(rebuild_database_url postgres postgres "$db_name")"
    export POSTGRES_USER=postgres
    export POSTGRES_PASSWORD=postgres
    export DATABASE_URL="$(rebuild_database_url postgres postgres "$db_name")"
    return 0
  fi

  return 1
}

is_port_busy() {
  local port="$1"
  ss -ltn "( sport = :${port} )" | grep -q LISTEN
}

pick_next_open_port() {
  local start="$1"
  local candidate
  for candidate in $(seq "$start" $((start + 40))); do
    if ! is_port_busy "$candidate"; then
      echo "$candidate"
      return 0
    fi
  done
  return 1
}

set_env_value() {
  local key="$1"
  local value="$2"
  if grep -q "^${key}=" .env; then
    sed -i "s#^${key}=.*#${key}=${value}#" .env
  else
    echo "${key}=${value}" >> .env
  fi
}

resolve_port() {
  local key="$1"
  local default="$2"
  local requested="${!key:-}"
  requested="${requested:-$(awk -F= -v k="$key" '$1==k{print $2}' .env | tail -n1)}"
  requested="${requested:-$default}"

  if is_port_busy "$requested"; then
    if [[ "$NON_INTERACTIVE" == "1" ]]; then
      local fallback
      fallback="$(pick_next_open_port $((requested + 1)))"
      warn "${key} ${requested} busy; auto-selected ${fallback}."
      echo "$fallback"
      return 0
    fi

    read -r -p "${key} ${requested} busy. Enter another port: " requested
  fi

  echo "$requested"
}

prepare_host_venv_if_enabled() {
  [[ "$ENABLE_HOST_VENV" == "1" ]] || return 0

  local run_user
  run_user="$(id -un)"
  local venv_path="backend/.venv"

  if [[ -e "$venv_path" ]] && [[ ! -w "$venv_path" ]]; then
    warn "${venv_path} is not writable by ${run_user}; skipping host venv setup."
    return 0
  fi

  info "Preparing optional backend host virtualenv"
  python3 -m venv "$venv_path"
  source "${venv_path}/bin/activate"
  python -m pip install --upgrade pip
  python -m pip install -r backend/requirements.txt
  deactivate
}

cd "$ROOT_DIR"
info "Starting Ubuntu 24.04 bootstrap from ${ROOT_DIR}"

if [[ ! -f .env ]]; then
  cp .env.example .env
  info "Created .env from .env.example"
fi

BACKEND_PORT="$(resolve_port BACKEND_PORT 8000)"
FRONTEND_PORT="$(resolve_port FRONTEND_PORT 5173)"
if [[ "$BACKEND_PORT" == "$FRONTEND_PORT" ]]; then
  FRONTEND_PORT="$(pick_next_open_port $((FRONTEND_PORT + 1)))"
  warn "Frontend port matched backend; switched to ${FRONTEND_PORT}."
fi

export BACKEND_PORT FRONTEND_PORT
set_env_value BACKEND_PORT "$BACKEND_PORT"
set_env_value FRONTEND_PORT "$FRONTEND_PORT"

# Force this app to use a dedicated Postgres data volume so it never reuses credentials
# from unrelated stacks or previous initializations.
POSTGRES_VOLUME_NAME="${POSTGRES_VOLUME_NAME:-iz_clinical_notes_analyzer_pgdata_app}"
export POSTGRES_VOLUME_NAME
set_env_value POSTGRES_VOLUME_NAME "$POSTGRES_VOLUME_NAME"
info "Using dedicated Postgres volume: ${POSTGRES_VOLUME_NAME}"

if ! command -v docker >/dev/null 2>&1; then
  warn 'Docker is required but not installed.'
  exit 1
fi

prepare_host_venv_if_enabled

info 'Starting Docker Compose stack'
docker compose pull || warn 'docker compose pull failed; continuing with local build cache'
if ! docker compose up -d --build; then
  warn 'docker compose up failed; collecting diagnostics.'
  docker compose ps || true
  docker compose logs --tail=200 db backend frontend || true
  db_logs="$(docker compose logs --tail=200 db 2>/dev/null || true)"
  if apply_option1_db_credential_fix "$db_logs"; then
    info 'Retrying docker compose up after applying Option 1 credential correction.'
    if ! docker compose up -d --build; then
      warn 'Retry failed after Option 1 correction; collecting diagnostics.'
      docker compose ps || true
      docker compose logs --tail=200 db backend frontend || true
      print_db_auth_diagnostics
      exit 1
    fi
  fi
  print_db_auth_diagnostics
  if ! docker compose ps --format json >/tmp/compose-ps.json 2>/dev/null || grep -q '"Health":"unhealthy"' /tmp/compose-ps.json; then
    exit 1
  fi
fi

echo '[INFO] Service status:'
docker compose ps

if docker compose ps --format json >/tmp/compose-ps.json 2>/dev/null; then
  if grep -q '"Health":"unhealthy"' /tmp/compose-ps.json; then
    warn 'Detected unhealthy containers after startup; collecting diagnostics.'
    docker compose logs --tail=200 db backend frontend || true
    print_db_auth_diagnostics
    exit 1
  fi
  info 'No unhealthy containers detected immediately after startup.'
else
  warn 'docker compose ps --format json not supported; skipping immediate health scan.'
fi

info 'Running smoke test'
if FRONTEND_PORT="$FRONTEND_PORT" ./scripts/smoke.sh; then
  pass 'Smoke test passed.'
else
  warn 'Smoke failed; collecting recent logs.'
  docker compose logs --tail=200 db backend frontend || true
  exit 1
fi

pass "Startup complete."
pass "Frontend URL: http://localhost:${FRONTEND_PORT}"
pass "Backend URL: http://localhost:${BACKEND_PORT}"
pass "Log file: ${LOG_FILE}"
