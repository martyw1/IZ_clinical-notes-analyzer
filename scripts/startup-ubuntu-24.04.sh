#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="${ROOT_DIR}/logs"
mkdir -p "${LOG_DIR}"
LOG_FILE="${LOG_DIR}/startup-ubuntu-$(date +%Y%m%d-%H%M%S).log"
exec > >(tee -a "${LOG_FILE}") 2>&1

trap 'echo "[ERROR] Startup failed on line $LINENO. Review log: ${LOG_FILE}"' ERR

if [[ "${EUID}" -eq 0 ]]; then
  SUDO=""
else
  SUDO="sudo"
fi

# Use the effective runtime user for non-root executions.
# When the script is launched with `sudo -u <user>`, SUDO_USER points at the
# original admin account, but docker/group checks must be done for the target
# account that is actually running this script.
if [[ "${EUID}" -eq 0 ]]; then
  RUN_USER="${SUDO_USER:-${USER}}"
else
  RUN_USER="${USER}"
fi
DOCKER_COMPOSE_CMD=(docker compose)

info() { echo "[$(date +'%F %T')] [INFO] $*" >&2; }
warn() { echo "[$(date +'%F %T')] [WARN] $*" >&2; }
pass() { echo "[$(date +'%F %T')] [PASS] $*" >&2; }

can_run_sudo_non_interactive() {
  [[ -n "${SUDO}" ]] && ${SUDO} -n true >/dev/null 2>&1
}

busy_ports_csv() {
  ss -ltnH | awk '{print $4}' | awk -F: '{print $NF}' | awk '/^[0-9]+$/' | sort -n -u | paste -sd ', ' -
}

is_port_busy() {
  local port="$1"
  ss -ltn "( sport = :${port} )" | grep -q LISTEN
}

set_env_value() {
  local key="$1"
  local value="$2"

  if grep -q "^${key}=" .env; then
    sed -i "s/^${key}=.*/${key}=${value}/" .env
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

pick_open_port() {
  local candidate
  for candidate in 55432 55433 55434 55435 55436; do
    if ! ss -ltn "( sport = :${candidate} )" | grep -q LISTEN; then
      echo "${candidate}"
      return 0
    fi
  done

  return 1
}

prepare_backend_venv_path() {
  local preferred_path="backend/.venv"

  if [[ ! -e "${preferred_path}" ]]; then
    echo "${preferred_path}"
    return 0
  fi

  if [[ -w "${preferred_path}" ]]; then
    # venv can fail even when the directory itself is writable if files inside
    # are owned by another account (for example from a previous root/admin run).
    local unwritable_entry
    unwritable_entry="$(find "${preferred_path}" -mindepth 1 \( -type f -o -type d \) ! -w -print -quit 2>/dev/null || true)"
    if [[ -z "${unwritable_entry}" ]]; then
      echo "${preferred_path}"
      return 0
    fi

    warn "${preferred_path} contains entries not writable by user ${RUN_USER}: ${unwritable_entry}"
  fi

  local fallback_path="backend/.venv-${RUN_USER}"
  warn "${preferred_path} exists but is not writable by user ${RUN_USER}."
  warn "Using fallback virtualenv path ${fallback_path}."
  echo "${fallback_path}"
}

create_backend_venv() {
  local venv_path="$1"

  if python3 -m venv "${venv_path}"; then
    return 0
  fi

  local fallback_path="backend/.venv-${RUN_USER}"
  if [[ "${venv_path}" == "${fallback_path}" ]]; then
    return 1
  fi

  warn "Failed to create ${venv_path}. Retrying with fallback ${fallback_path}."
  python3 -m venv "${fallback_path}"
  echo "${fallback_path}"
}

configure_docker_invocation() {
  if docker info >/dev/null 2>&1; then
    return 0
  fi

  if can_run_sudo_non_interactive && ${SUDO} docker info >/dev/null 2>&1; then
    warn "Current shell cannot access /var/run/docker.sock directly; using sudo for Docker commands in this run."
    DOCKER_COMPOSE_CMD=(${SUDO} docker compose)
    return 0
  fi

  warn "Docker is installed but not reachable by this user yet. If you were just added to the docker group, re-login and rerun."
  return 1
}

need_cmd() {
  local cmd="$1"
  local package="$2"
  if command -v "${cmd}" >/dev/null 2>&1; then
    pass "Found ${cmd}."
  elif [[ -n "${SUDO}" ]] && ! can_run_sudo_non_interactive; then
    warn "Missing ${cmd} (${package}), but sudo is unavailable without a password in this account."
    warn "Install ${package} as an admin user, then rerun this script."
    exit 1
  else
    info "Installing missing dependency: ${package}"
    ${SUDO} apt-get install -y "${package}"
  fi
}

info "Starting Ubuntu 24.04 bootstrap from ${ROOT_DIR}"
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

info "Refreshing apt package index"
if [[ -n "${SUDO}" ]] && ! can_run_sudo_non_interactive; then
  warn "Skipping apt package installation because sudo requires a password for user ${USER}."
  warn "Run once as an admin account (or configure passwordless sudo for this script) to install dependencies."
else
  ${SUDO} apt-get update -y
fi

need_cmd curl curl
need_cmd git git
need_cmd python3 python3
need_cmd pip3 python3-pip
need_cmd npm npm

if ! command -v docker >/dev/null 2>&1; then
  if [[ -n "${SUDO}" ]] && ! can_run_sudo_non_interactive; then
    warn "Docker is not installed and cannot be installed from this account without passwordless sudo."
    exit 1
  fi
  info "Installing Docker Engine and Compose plugin"
  ${SUDO} apt-get install -y ca-certificates gnupg
  ${SUDO} install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | ${SUDO} gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  ${SUDO} chmod a+r /etc/apt/keyrings/docker.gpg
  echo \
    "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
    $(. /etc/os-release && echo \"$VERSION_CODENAME\") stable" | \
    ${SUDO} tee /etc/apt/sources.list.d/docker.list >/dev/null
  ${SUDO} apt-get update -y
  ${SUDO} apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi

pass "Docker version: $(docker --version 2>/dev/null || true)"
if ! docker compose version >/dev/null 2>&1; then
  info "Installing docker-compose-plugin"
  ${SUDO} apt-get install -y docker-compose-plugin
fi
pass "Docker compose version: $(docker compose version | head -n1)"

if ! getent group docker >/dev/null; then
  if [[ -n "${SUDO}" ]] && ! can_run_sudo_non_interactive; then
    warn "Docker group is missing and cannot be created without sudo access."
    exit 1
  fi
  ${SUDO} groupadd docker
fi
if ! groups "${RUN_USER}" | grep -q '\bdocker\b'; then
  if [[ -n "${SUDO}" ]] && ! can_run_sudo_non_interactive; then
    warn "User ${RUN_USER} is not in docker group and cannot be modified from this account."
    warn "Add ${RUN_USER} to docker group as admin: sudo usermod -aG docker ${RUN_USER}"
    exit 1
  fi
  warn "User ${RUN_USER} is not in docker group; adding now. You may need to re-login for group changes to apply."
  ${SUDO} usermod -aG docker "${RUN_USER}"
fi

info "Ensuring Docker service is running"
if [[ -n "${SUDO}" ]] && ! can_run_sudo_non_interactive; then
  warn "Cannot manage Docker service without sudo access in this account. Assuming service is already running."
else
  ${SUDO} systemctl enable docker
  ${SUDO} systemctl start docker
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

configure_docker_invocation

info "Running backend Python environment setup"
BACKEND_VENV_PATH="$(prepare_backend_venv_path)"
if remapped_path="$(create_backend_venv "${BACKEND_VENV_PATH}")"; then
  if [[ -n "${remapped_path}" ]]; then
    BACKEND_VENV_PATH="${remapped_path}"
  fi
else
  warn "Unable to create Python virtual environment at ${BACKEND_VENV_PATH}."
  warn "If this path was created by another account, fix ownership: sudo chown -R ${RUN_USER}:${RUN_USER} backend/.venv"
  exit 1
fi

source "${BACKEND_VENV_PATH}/bin/activate"
python -m pip install --upgrade pip
python -m pip install -r backend/requirements.txt
deactivate

info "Running frontend Node environment setup"
cd frontend
npm install
cd "${ROOT_DIR}"

info "Starting application stack with Docker Compose"
if [[ -z "${POSTGRES_PORT:-}" ]] && ss -ltn '( sport = :5432 )' | grep -q LISTEN; then
  if suggested_port="$(pick_open_port)"; then
    export POSTGRES_PORT="${suggested_port}"
    warn "Host port 5432 is already in use; remapping Postgres to ${POSTGRES_PORT} for this run."
  else
    warn "Host port 5432 is in use and no fallback Postgres port was found automatically."
  fi
fi

"${DOCKER_COMPOSE_CMD[@]}" pull || warn "docker compose pull had issues; proceeding with local build"
"${DOCKER_COMPOSE_CMD[@]}" up -d --build

info "Current service status"
"${DOCKER_COMPOSE_CMD[@]}" ps

pass "Startup complete. Logs are in ${LOG_FILE}"
