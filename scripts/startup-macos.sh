#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="${ROOT_DIR}/logs"
mkdir -p "${LOG_DIR}"
LOG_FILE="${LOG_DIR}/startup-macos-$(date +%Y%m%d-%H%M%S).log"
exec > >(tee -a "${LOG_FILE}") 2>&1

trap 'echo "[ERROR] Startup failed on line $LINENO. Review log: ${LOG_FILE}"' ERR

info() { echo "[$(date +'%F %T')] [INFO] $*"; }
warn() { echo "[$(date +'%F %T')] [WARN] $*"; }
pass() { echo "[$(date +'%F %T')] [PASS] $*"; }

busy_ports_csv() {
  lsof -nP -iTCP -sTCP:LISTEN 2>/dev/null | awk 'NR>1 {split($9, parts, ":"); print parts[length(parts)]}' | awk '/^[0-9]+$/' | sort -n -u | paste -sd ', ' -
}

is_port_busy() {
  local port="$1"
  lsof -nP -iTCP:"${port}" -sTCP:LISTEN >/dev/null 2>&1
}

set_env_value() {
  local key="$1"
  local value="$2"

  if grep -q "^${key}=" .env; then
    sed -i '' "s/^${key}=.*/${key}=${value}/" .env
  else
    echo "${key}=${value}" >> .env
  fi
}

prompt_for_port() {
  local var_name="$1"
  local default_port="$2"
  local chosen_port

  while true; do
    read -r -p "Enter ${var_name} [${default_port}]: " chosen_port
    chosen_port="${chosen_port:-${default_port}}"

    if [[ ! "${chosen_port}" =~ ^[0-9]+$ ]] || (( chosen_port < 1 || chosen_port > 65535 )); then
      warn "${chosen_port} is not a valid TCP port."
      continue
    fi

    if is_port_busy "${chosen_port}"; then
      warn "Port ${chosen_port} is busy. These are the ports already busy: ${BUSY_PORTS_DISPLAY}"
      continue
    fi

    echo "${chosen_port}"
    return 0
  done
}

install_brew_package_if_missing() {
  local cmd="$1"
  local package="$2"
  if command -v "${cmd}" >/dev/null 2>&1; then
    pass "Found ${cmd}."
  else
    info "Installing ${package} via Homebrew"
    brew install "${package}"
  fi
}

info "Starting macOS bootstrap from ${ROOT_DIR}"
cd "${ROOT_DIR}"

BUSY_PORTS_DISPLAY="$(busy_ports_csv)"
BUSY_PORTS_DISPLAY="${BUSY_PORTS_DISPLAY:-none}"
info "Ports currently busy on this host: ${BUSY_PORTS_DISPLAY}"

if [[ ! -f ".env" ]]; then
  cp .env.example .env
  info "Created .env from .env.example"
else
  pass ".env already exists"
fi

BACKEND_DEFAULT="${BACKEND_PORT:-$(awk -F= '/^BACKEND_PORT=/{print $2}' .env | tail -n1)}"
FRONTEND_DEFAULT="${FRONTEND_PORT:-$(awk -F= '/^FRONTEND_PORT=/{print $2}' .env | tail -n1)}"
BACKEND_DEFAULT="${BACKEND_DEFAULT:-8000}"
FRONTEND_DEFAULT="${FRONTEND_DEFAULT:-5173}"

BACKEND_PORT="$(prompt_for_port BACKEND_PORT "${BACKEND_DEFAULT}")"
while [[ "${BACKEND_PORT}" == "${FRONTEND_PORT:-}" ]]; do
  warn "Backend and frontend ports must be different."
  BACKEND_PORT="$(prompt_for_port BACKEND_PORT "${BACKEND_DEFAULT}")"
done

FRONTEND_PORT="$(prompt_for_port FRONTEND_PORT "${FRONTEND_DEFAULT}")"
while [[ "${FRONTEND_PORT}" == "${BACKEND_PORT}" ]]; do
  warn "Frontend and backend ports must be different."
  FRONTEND_PORT="$(prompt_for_port FRONTEND_PORT "${FRONTEND_DEFAULT}")"
done

export BACKEND_PORT FRONTEND_PORT
set_env_value BACKEND_PORT "${BACKEND_PORT}"
set_env_value FRONTEND_PORT "${FRONTEND_PORT}"
info "Using BACKEND_PORT=${BACKEND_PORT}, FRONTEND_PORT=${FRONTEND_PORT}"

if ! command -v brew >/dev/null 2>&1; then
  warn "Homebrew is required but not installed. Install from https://brew.sh and rerun this script."
  exit 1
fi

info "Updating Homebrew formulas"
brew update

install_brew_package_if_missing git git
install_brew_package_if_missing curl curl
install_brew_package_if_missing python3 python
install_brew_package_if_missing npm node

if ! command -v docker >/dev/null 2>&1; then
  info "Installing Docker Desktop via Homebrew Cask"
  brew install --cask docker
  warn "Docker Desktop was installed. Launch Docker Desktop once and wait for engine startup, then rerun this script."
  exit 1
fi

if ! docker info >/dev/null 2>&1; then
  warn "Docker engine is not available. Launch Docker Desktop and rerun this script."
  exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
  warn "docker compose plugin not found. Ensure your Docker Desktop installation is complete."
  exit 1
fi
pass "Docker compose version: $(docker compose version | head -n1)"

info "Setting up backend Python environment"
python3 -m venv backend/.venv
source backend/.venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r backend/requirements.txt
deactivate

info "Setting up frontend Node environment"
cd frontend
npm install
cd "${ROOT_DIR}"

info "Starting Docker Compose stack"
docker compose pull || warn "docker compose pull had issues; proceeding with local build"
COMPOSE_ARGS=()
if [[ "${USE_INTERNAL_POSTGRES:-1}" == "1" ]]; then
  COMPOSE_ARGS+=(--profile internal-db)
fi
info "DB mode: ${DATABASE_HOST_MODE:-internal} (USE_INTERNAL_POSTGRES=${USE_INTERNAL_POSTGRES:-1})"
docker compose "${COMPOSE_ARGS[@]}" up -d --build

info "Current service status"
docker compose "${COMPOSE_ARGS[@]}" ps

pass "Startup complete. Logs are in ${LOG_FILE}"
