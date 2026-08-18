#!/usr/bin/env bash
set -u
set -o pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="${IZ_CNA_PREFLIGHT_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"
ASSUME_YES=0
PORT="${IZ_CNA_PREFLIGHT_PORT:-8000}"
REPORT_FILE="${IZ_CNA_PREFLIGHT_REPORT:-}"
PYTHON_OVERRIDE="${IZ_CNA_PREFLIGHT_PYTHON:-}"
NPM_OVERRIDE="${IZ_CNA_PREFLIGHT_NPM:-}"
APP_DATA_OVERRIDE="${IZ_CNA_LOCAL_APP_DATA_DIR:-}"
TEMP_DIR=""
PYTHON_BIN=""
VENV_PYTHON=""
APP_DATA_ROOT=""
FAILED=0
WARNINGS=0
CHECK_NAMES=()
CHECK_STATUS=()
CHECK_MESSAGES=()
CHECK_REMEDIATIONS=()

print_usage() {
    printf '%s\n' 'Usage: preflight-macos.sh [--port PORT] [--report FILE] [--assume-yes]'
}

fail_usage() {
    printf '%s\n' 'Preflight arguments are invalid. Use --help for usage.' >&2
    exit 2
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --assume-yes)
            ASSUME_YES=1
            shift
            ;;
        --port)
            [[ $# -ge 2 ]] || fail_usage
            PORT="$2"
            shift 2
            ;;
        --port=*)
            PORT="${1#*=}"
            shift
            ;;
        --report)
            [[ $# -ge 2 ]] || fail_usage
            REPORT_FILE="$2"
            shift 2
            ;;
        --report=*)
            REPORT_FILE="${1#*=}"
            shift
            ;;
        --help|-h)
            print_usage
            exit 0
            ;;
        *)
            fail_usage
            ;;
    esac
done

if [[ -z "$REPORT_FILE" ]]; then
    if [[ -n "$APP_DATA_OVERRIDE" ]]; then
        REPORT_FILE="$APP_DATA_OVERRIDE/logs/preflight-macos-latest.json"
    elif [[ -n "${HOME:-}" ]]; then
        REPORT_FILE="$HOME/Library/Application Support/IZ Clinical Notes Analyzer/logs/preflight-macos-latest.json"
    fi
fi

record_check() {
    local name="$1"
    local status="$2"
    local message="$3"
    local remediation="${4:-}"
    CHECK_NAMES+=("$name")
    CHECK_STATUS+=("$status")
    CHECK_MESSAGES+=("$message")
    CHECK_REMEDIATIONS+=("$remediation")
    if [[ "$status" == 'fail' ]]; then
        FAILED=$((FAILED + 1))
    elif [[ "$status" == 'warn' ]]; then
        WARNINGS=$((WARNINGS + 1))
    fi
    printf '[%s] %s - %s\n' "$status" "$name" "$message"
    if [[ -n "$remediation" ]]; then
        printf '      %s\n' "$remediation"
    fi
}

is_absolute_path() {
    [[ "$1" == /* ]]
}

file_mtime() {
    local path="$1"
    local value=""
    value="$(stat -f %m "$path" 2>/dev/null || true)"
    if [[ "$value" =~ ^[0-9]+$ ]]; then
        printf '%s\n' "$value"
        return 0
    fi
    value="$(stat -c %Y "$path" 2>/dev/null || true)"
    if [[ "$value" =~ ^[0-9]+$ ]]; then
        printf '%s\n' "$value"
        return 0
    fi
    return 1
}

run_quiet() {
    local output_file="$1"
    shift
    "$@" >"$output_file" 2>&1
}

version_is_supported() {
    local version="$1"
    local major="${version%%.*}"
    local remainder="${version#*.}"
    local minor="${remainder%%.*}"
    [[ "$major" =~ ^[0-9]+$ && "$minor" =~ ^[0-9]+$ ]] || return 1
    (( major > 3 || (major == 3 && minor >= 11) ))
}

macos_version_is_supported() {
    local version="$1"
    local major="${version%%.*}"
    [[ "$major" =~ ^[0-9]+$ ]] || return 1
    (( major >= 14 ))
}

check_platform() {
    local os_name="$(uname -s 2>/dev/null || true)"
    local architecture="$(uname -m 2>/dev/null || true)"
    local macos_version=""
    if [[ "$os_name" != 'Darwin' ]]; then
        record_check 'platform' 'fail' 'macOS is required for source preflight.' 'Run this launcher on macOS 14 or newer.'
        return
    fi
    if [[ "$architecture" != 'arm64' ]]; then
        record_check 'architecture' 'fail' 'Apple Silicon arm64 is required for this build.' 'Use an Apple Silicon Mac; Intel and universal builds are not supported.'
    else
        record_check 'architecture' 'ok' 'Apple Silicon arm64 detected.'
    fi
    macos_version="$(sw_vers -productVersion 2>/dev/null || true)"
    if macos_version_is_supported "$macos_version"; then
        record_check 'macos_version' 'ok' 'macOS 14 or newer detected.'
    else
        record_check 'macos_version' 'fail' 'macOS 14 or newer is required.' 'Update macOS before starting the local app.'
    fi
}

find_python() {
    if [[ "$PYTHON_OVERRIDE" == 'none' ]]; then
        return 0
    fi
    if [[ -n "$PYTHON_OVERRIDE" ]]; then
        [[ -x "$PYTHON_OVERRIDE" ]] && PYTHON_BIN="$PYTHON_OVERRIDE"
        return 0
    fi
    PYTHON_BIN="$(command -v python3 2>/dev/null || true)"
    if [[ -z "$PYTHON_BIN" ]]; then
        PYTHON_BIN="$(command -v python 2>/dev/null || true)"
    fi
}

check_python() {
    local version_text=""
    local version=""
    find_python
    if [[ -z "$PYTHON_BIN" ]]; then
        record_check 'python' 'fail' 'Python 3.11 or newer was not found.' 'Install Python 3.12 for this user account, then rerun this preflight.'
        return
    fi
    version_text="$($PYTHON_BIN --version 2>&1 || true)"
    version="$(printf '%s' "$version_text" | sed -nE 's/^Python ([0-9]+\.[0-9]+\.[0-9]+).*$/\1/p')"
    if version_is_supported "$version"; then
        record_check 'python' 'ok' 'Python 3.11 or newer is available.'
    else
        record_check 'python' 'fail' 'The available Python runtime is too old or unusable.' 'Install Python 3.12 for this user account, then rerun this preflight.'
        PYTHON_BIN=""
    fi
}

resolve_app_data() {
    if [[ -n "$APP_DATA_OVERRIDE" ]]; then
        if ! is_absolute_path "$APP_DATA_OVERRIDE"; then
            record_check 'app_data' 'fail' 'The local app-data override must be an absolute path.' 'Use the macOS Application Support location or an absolute synthetic test directory.'
            return
        fi
        APP_DATA_ROOT="$APP_DATA_OVERRIDE"
    elif [[ -n "${HOME:-}" ]]; then
        APP_DATA_ROOT="$HOME/Library/Application Support/IZ Clinical Notes Analyzer"
    else
        record_check 'app_data' 'fail' 'The macOS user home directory is unavailable.' 'Run as the signed-in desktop user; administrator access is not required.'
        return
    fi
    if [[ -d "$APP_DATA_ROOT" && -w "$APP_DATA_ROOT" ]]; then
        record_check 'app_data' 'ok' 'The OS-local application data directory is writable.'
        return
    fi
    if [[ "$ASSUME_YES" -eq 1 ]]; then
        if mkdir -p "$APP_DATA_ROOT" 2>/dev/null && [[ -w "$APP_DATA_ROOT" ]]; then
            record_check 'app_data' 'ok' 'The OS-local application data directory is writable.'
            return
        fi
    fi
    record_check 'app_data' 'fail' 'The OS-local application data directory is unavailable or not writable.' 'Create the macOS Application Support directory as the current user, or rerun with --assume-yes.'
}

check_repository() {
    if [[ -d "$ROOT_DIR" && -r "$ROOT_DIR" && -x "$ROOT_DIR" && -w "$ROOT_DIR" ]]; then
        record_check 'repository' 'ok' 'The source checkout is readable and writable.'
    else
        record_check 'repository' 'fail' 'The source checkout is unavailable or not writable.' 'Move the checkout to a user-writable folder and rerun this preflight.'
    fi
}

create_virtual_environment() {
    local output_file="$1"
    if [[ -z "$PYTHON_BIN" ]]; then
        return 1
    fi
    run_quiet "$output_file" "$PYTHON_BIN" -m venv "$ROOT_DIR/backend/.venv"
}

install_backend_requirements() {
    local output_file="$1"
    local requirements="$ROOT_DIR/backend/requirements-windows-local.txt"
    [[ -f "$requirements" ]] || requirements="$ROOT_DIR/backend/requirements.txt"
    [[ -f "$requirements" ]] || return 1
    run_quiet "$output_file" "$VENV_PYTHON" -m pip install -r "$requirements"
}

check_backend() {
    local output_file=""
    local import_status=0
    VENV_PYTHON="$ROOT_DIR/backend/.venv/bin/python"
    TEMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/iz-cna-preflight.XXXXXX")"
    output_file="$TEMP_DIR/backend.log"
    if [[ ! -x "$VENV_PYTHON" ]]; then
        if [[ "$ASSUME_YES" -eq 1 && -n "$PYTHON_BIN" ]]; then
            if create_virtual_environment "$output_file" && [[ -x "$VENV_PYTHON" ]]; then
                record_check 'backend_venv' 'ok' 'The backend virtual environment was created.'
            else
                record_check 'backend_venv' 'fail' 'The backend virtual environment is missing.' 'Rerun with --assume-yes to create backend/.venv from the available Python runtime.'
                return
            fi
        else
            record_check 'backend_venv' 'fail' 'The backend virtual environment is missing.' 'Rerun with --assume-yes to create backend/.venv from the available Python runtime.'
            return
        fi
    else
        record_check 'backend_venv' 'ok' 'The backend virtual environment is present.'
    fi
    PYTHONPATH="$ROOT_DIR/backend" "$VENV_PYTHON" -c 'import fastapi, uvicorn, sqlalchemy, yaml, pydantic_settings' >"$output_file" 2>&1 || import_status=$?
    if [[ "$import_status" -ne 0 && "$ASSUME_YES" -eq 1 ]]; then
        if install_backend_requirements "$output_file"; then
            import_status=0
            PYTHONPATH="$ROOT_DIR/backend" "$VENV_PYTHON" -c 'import fastapi, uvicorn, sqlalchemy, yaml, pydantic_settings' >"$output_file" 2>&1 || import_status=$?
        fi
    fi
    if [[ "$import_status" -eq 0 ]]; then
        record_check 'backend_imports' 'ok' 'Backend runtime imports are available.'
    elif [[ "$ASSUME_YES" -eq 1 ]]; then
        record_check 'backend_imports' 'fail' 'Backend runtime dependencies could not be installed or imported.' 'Review the local Python requirements for this checkout.'
    else
        record_check 'backend_imports' 'fail' 'Backend runtime dependencies are missing or could not be imported.' 'Rerun with --assume-yes to install the pinned backend requirements.'
    fi
}

frontend_valid() {
    local dist="$ROOT_DIR/frontend/dist"
    local index="$dist/index.html"
    local js_count=0
    local css_count=0
    [[ -s "$index" && -d "$dist/assets" ]] || return 1
    while IFS= read -r -d '' path; do
        case "$path" in
            *.js) js_count=$((js_count + 1)) ;;
            *.css) css_count=$((css_count + 1)) ;;
        esac
    done < <(find "$dist/assets" -type f -size +0c -print0 2>/dev/null)
    (( js_count > 0 && css_count > 0 )) || return 1
    grep -Eq '/assets/[^"[:space:]]+\.js' "$index"
}

latest_source_mtime() {
    local latest=0
    local path=""
    local value=""
    while IFS= read -r -d '' path; do
        value="$(file_mtime "$path" || true)"
        if [[ "$value" =~ ^[0-9]+$ && "$value" -gt "$latest" ]]; then
            latest="$value"
        fi
    done < <(find "$ROOT_DIR/frontend/src" -type f -print0 2>/dev/null)
    for path in "$ROOT_DIR/frontend/index.html" "$ROOT_DIR/frontend/package.json" "$ROOT_DIR/frontend/package-lock.json" "$ROOT_DIR/frontend/tsconfig.json" "$ROOT_DIR/frontend/vite.config.ts"; do
        [[ -f "$path" ]] || continue
        value="$(file_mtime "$path" || true)"
        if [[ "$value" =~ ^[0-9]+$ && "$value" -gt "$latest" ]]; then
            latest="$value"
        fi
    done
    printf '%s\n' "$latest"
}

oldest_build_mtime() {
    local oldest=9223372036854775807
    local path=""
    local value=""
    while IFS= read -r -d '' path; do
        value="$(file_mtime "$path" || true)"
        if [[ "$value" =~ ^[0-9]+$ && "$value" -lt "$oldest" ]]; then
            oldest="$value"
        fi
    done < <(find "$ROOT_DIR/frontend/dist" -type f -print0 2>/dev/null)
    if [[ "$oldest" == 9223372036854775807 ]]; then
        printf '%s\n' '0'
    else
        printf '%s\n' "$oldest"
    fi
}

find_npm() {
    if [[ "$NPM_OVERRIDE" == 'none' ]]; then
        return 0
    fi
    if [[ -n "$NPM_OVERRIDE" ]]; then
        [[ -x "$NPM_OVERRIDE" ]] && printf '%s\n' "$NPM_OVERRIDE"
        return 0
    fi
    command -v npm 2>/dev/null || true
}

build_frontend() {
    local npm_bin="$1"
    local output_file="$TEMP_DIR/frontend.log"
    if [[ -f "$ROOT_DIR/frontend/package-lock.json" ]]; then
        (cd "$ROOT_DIR/frontend" && run_quiet "$output_file" "$npm_bin" ci) || return 1
    else
        (cd "$ROOT_DIR/frontend" && run_quiet "$output_file" "$npm_bin" install) || return 1
    fi
    (cd "$ROOT_DIR/frontend" && run_quiet "$output_file" "$npm_bin" run build)
}

check_frontend() {
    local source_mtime=0
    local build_mtime=0
    local npm_bin=""
    if frontend_valid; then
        source_mtime="$(latest_source_mtime)"
        build_mtime="$(oldest_build_mtime)"
        if [[ "$source_mtime" -le "$build_mtime" ]]; then
            record_check 'frontend' 'ok' 'The built frontend is present and current.'
            return
        fi
    fi
    npm_bin="$(find_npm)"
    if [[ -z "$npm_bin" ]]; then
        record_check 'frontend' 'fail' 'The frontend build is missing or stale and npm is unavailable.' 'Install Node.js LTS or use a prepared package with current frontend assets.'
        return
    fi
    if [[ "$ASSUME_YES" -ne 1 ]]; then
        record_check 'frontend' 'fail' 'The frontend build is missing or stale.' 'Rerun with --assume-yes to run npm install and npm run build for this checkout.'
        return
    fi
    if build_frontend "$npm_bin" && frontend_valid; then
        record_check 'frontend' 'ok' 'The frontend was built and validated.'
    else
        record_check 'frontend' 'fail' 'The frontend build did not produce valid assets.' 'Review the local frontend build dependencies and rerun this preflight.'
    fi
}

check_configuration() {
    local output_file="$TEMP_DIR/config.log"
    local status=0
    [[ -x "$VENV_PYTHON" ]] || return
    (
        cd "$ROOT_DIR" || exit 1
        ENVIRONMENT=development IZ_CNA_LOCAL_APP_DATA_DIR="$APP_DATA_ROOT" PYTHONPATH="$ROOT_DIR/backend" "$VENV_PYTHON" -c 'import json
from pathlib import Path
import yaml
from app.core import config
from app.services.version import build_version_payload
root = Path.cwd()
rules_path = root / "config" / "rules" / "alleva_treatment_plan_completeness_rules.yaml"
checklist_path = root / "config" / "checklists" / "treatment-plan-v1.json"
rules = yaml.safe_load(rules_path.read_text(encoding="utf-8"))
checklist = json.loads(checklist_path.read_text(encoding="utf-8"))
assert isinstance(rules, dict) and rules.get("rules") and rules.get("levels_of_care")
assert rules.get("loc_change_blocker", {}).get("status") == "unvalidated"
steps = checklist.get("steps")
assert isinstance(steps, list) and len(steps) == 42
assert [step.get("step") for step in steps] == list(range(1, 43))
assert build_version_payload().get("version") == config.APP_VERSION
' >"$output_file" 2>&1
    ) || status=$?
    if [[ "$status" -eq 0 ]]; then
        record_check 'configuration' 'ok' 'Application configuration, deterministic rules, and checklist imports passed.'
    else
        record_check 'configuration' 'fail' 'Application configuration, rules, or checklist validation failed.' 'Repair the checkout configuration and rerun this preflight.'
    fi
}

check_port() {
    local status=0
    case "$PORT" in
        ''|*[!0-9]*)
            record_check 'port' 'fail' 'The configured localhost port is invalid.' 'Choose a TCP port from 1 through 65535.'
            return
            ;;
    esac
    if (( PORT < 1 || PORT > 65535 )); then
        record_check 'port' 'fail' 'The configured localhost port is invalid.' 'Choose a TCP port from 1 through 65535.'
        return
    fi
    if command -v nc >/dev/null 2>&1; then
        nc -z -w 1 127.0.0.1 "$PORT" >/dev/null 2>&1
        status=$?
        if [[ "$status" -eq 0 ]]; then
            record_check 'port' 'fail' 'The configured localhost port is already in use.' 'Stop the owning local app or choose another configured port.'
        else
            record_check 'port' 'ok' 'The configured localhost port is available.'
        fi
        return
    fi
    if [[ -x "$VENV_PYTHON" ]]; then
        "$VENV_PYTHON" -c 'import socket, sys
port = int(sys.argv[1])
with socket.socket() as sock:
    sock.settimeout(0.5)
    try:
        sock.connect(("127.0.0.1", port))
    except OSError:
        raise SystemExit(0)
    raise SystemExit(1)
' "$PORT" >/dev/null 2>&1
        status=$?
        if [[ "$status" -eq 0 ]]; then
            record_check 'port' 'ok' 'The configured localhost port is available.'
        else
            record_check 'port' 'fail' 'The configured localhost port is already in use.' 'Stop the owning local app or choose another configured port.'
        fi
    else
        record_check 'port' 'fail' 'The configured localhost port could not be checked.' 'Provide a working backend virtual environment and rerun this preflight.'
    fi
}

json_escape() {
    printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g; s/	/\\t/g; s/\r/\\r/g; s/\n/\\n/g'
}

write_report() {
    local report_parent=""
    local index=0
    local comma=""
    [[ -n "$REPORT_FILE" ]] || return 0
    report_parent="$(dirname "$REPORT_FILE")"
    if [[ ! -d "$report_parent" ]]; then
        [[ "$ASSUME_YES" -eq 1 ]] || return 0
        mkdir -p "$report_parent" 2>/dev/null || return 0
    fi
    [[ -w "$report_parent" ]] || return 0
    {
        printf '{\n  "status": "%s",\n  "failed": %d,\n  "warnings": %d,\n  "checks": [\n' "$([[ "$FAILED" -gt 0 ]] && printf fail || ([[ "$WARNINGS" -gt 0 ]] && printf warn || printf ok))" "$FAILED" "$WARNINGS"
        for ((index = 0; index < ${#CHECK_NAMES[@]}; index++)); do
            if [[ "$index" -gt 0 ]]; then comma=','; else comma=''; fi
            printf '%s    {"name":"%s","status":"%s","message":"%s","remediation":"%s"}' \
                "$comma" \
                "$(json_escape "${CHECK_NAMES[$index]}")" \
                "$(json_escape "${CHECK_STATUS[$index]}")" \
                "$(json_escape "${CHECK_MESSAGES[$index]}")" \
                "$(json_escape "${CHECK_REMEDIATIONS[$index]}")"
            printf '\n'
        done
        printf '  ]\n}\n'
    } >"$REPORT_FILE" 2>/dev/null || true
}

cleanup() {
    if [[ -n "$TEMP_DIR" && -d "$TEMP_DIR" ]]; then
        rm -rf "$TEMP_DIR"
    fi
}
trap cleanup EXIT

check_platform
check_repository
resolve_app_data
check_python
check_backend
check_frontend
check_configuration
check_port
write_report

if [[ "$FAILED" -gt 0 ]]; then
    printf '%s\n' 'macOS source preflight failed. Resolve the listed checks and rerun.' >&2
    exit 1
fi
if [[ "$WARNINGS" -gt 0 ]]; then
    printf '%s\n' 'macOS source preflight passed with warnings.'
else
    printf '%s\n' 'macOS source preflight passed.'
fi
exit 0
