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

info() { echo "[$(date +'%F %T')] [INFO] $*"; }
warn() { echo "[$(date +'%F %T')] [WARN] $*"; }
pass() { echo "[$(date +'%F %T')] [PASS] $*"; }

need_cmd() {
  local cmd="$1"
  local package="$2"
  if command -v "${cmd}" >/dev/null 2>&1; then
    pass "Found ${cmd}."
  else
    info "Installing missing dependency: ${package}"
    ${SUDO} apt-get install -y "${package}"
  fi
}

info "Starting Ubuntu 24.04 bootstrap from ${ROOT_DIR}"
cd "${ROOT_DIR}"

if [[ ! -f ".env" ]]; then
  cp .env.example .env
  info "Created .env from .env.example"
else
  pass ".env already exists"
fi

info "Refreshing apt package index"
${SUDO} apt-get update -y

need_cmd curl curl
need_cmd git git
need_cmd python3 python3
need_cmd pip3 python3-pip
need_cmd npm npm

if ! command -v docker >/dev/null 2>&1; then
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
  ${SUDO} groupadd docker
fi
if ! groups "${USER}" | grep -q '\bdocker\b'; then
  warn "User ${USER} is not in docker group; adding now. You may need to re-login for group changes to apply."
  ${SUDO} usermod -aG docker "${USER}"
fi

info "Ensuring Docker service is running"
${SUDO} systemctl enable docker
${SUDO} systemctl start docker

info "Running backend Python environment setup"
python3 -m venv backend/.venv
source backend/.venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r backend/requirements.txt
deactivate

info "Running frontend Node environment setup"
cd frontend
npm install
cd "${ROOT_DIR}"

info "Starting application stack with Docker Compose"
docker compose pull || warn "docker compose pull had issues; proceeding with local build"
docker compose up -d --build

info "Current service status"
docker compose ps

pass "Startup complete. Logs are in ${LOG_FILE}"
