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

if [[ ! -f ".env" ]]; then
  cp .env.example .env
  info "Created .env from .env.example"
else
  pass ".env already exists"
fi

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
docker compose up -d --build

info "Current service status"
docker compose ps

pass "Startup complete. Logs are in ${LOG_FILE}"
