#!/usr/bin/env bash
set -u
set -o pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_PYTHON="$ROOT_DIR/backend/.venv/bin/python"
HOST="127.0.0.1"
PORT="${IZ_CNA_PORT:-}"
ASSUME_YES=1
NO_BROWSER=0
STOP_ONLY=0
PREFLIGHT_SCRIPT="${IZ_CNA_PREFLIGHT_SCRIPT:-$ROOT_DIR/scripts/preflight-macos.sh}"
BROWSER_OPENER="${IZ_CNA_BROWSER_OPENER:-open}"
READINESS_TIMEOUT="${IZ_CNA_READINESS_TIMEOUT_SECONDS:-60}"
APP_DATA_ROOT=""
ENV_FILE=""
OWNER_RECORD=""
RUNTIME_LOG=""
PREFLIGHT_REPORT=""
RUNTIME_PID=""

usage() {
    printf '%s\n' 'Usage: start-macos-local.sh [--port PORT] [--no-browser] [--no-assume-yes] [--stop]'
}

fail() {
    printf '[fail] %s\n' "$1" >&2
    return 1
}

is_absolute_path() {
    [[ "$1" == /* ]]
}

resolve_data_root() {
    if [[ -n "${IZ_CNA_LOCAL_APP_DATA_DIR:-}" ]]; then
        APP_DATA_ROOT="$IZ_CNA_LOCAL_APP_DATA_DIR"
    elif [[ -n "${HOME:-}" ]]; then
        APP_DATA_ROOT="$HOME/Library/Application Support/IZ Clinical Notes Analyzer"
    else
        fail 'invalid_data_root'
        return 1
    fi
    is_absolute_path "$APP_DATA_ROOT" || fail 'invalid_data_root'
}

read_configured_port() {
    local line=""
    if [[ -n "$PORT" ]]; then
        return 0
    fi
    if [[ -f "$APP_DATA_ROOT/.env" ]]; then
        line="$(sed -n 's/^BACKEND_PORT=//p' "$APP_DATA_ROOT/.env" | head -n 1 | tr -d '\r')"
    fi
    if [[ "$line" =~ ^[0-9]+$ ]]; then
        PORT="$line"
    else
        PORT=8000
    fi
}

validate_port() {
    [[ "$PORT" =~ ^[0-9]+$ ]] || fail 'invalid_port' || return 1
    (( PORT >= 1 && PORT <= 65535 )) || fail 'invalid_port' || return 1
}

validate_timeout() {
    [[ "$READINESS_TIMEOUT" =~ ^[0-9]+$ ]] || fail 'invalid_readiness_timeout' || return 1
    (( READINESS_TIMEOUT >= 1 && READINESS_TIMEOUT <= 600 )) || fail 'invalid_readiness_timeout' || return 1
}

record_field() {
    local key="$1"
    local file="$2"
    awk -F= -v wanted="$key" '$1 == wanted { sub(/^[^=]*=/, ""); print; exit }' "$file"
}

file_mode() {
    local path="$1"
    if [[ "$(uname -s 2>/dev/null || true)" == Darwin ]]; then
        stat -f '%Lp' "$path" 2>/dev/null
    else
        stat -c '%a' "$path" 2>/dev/null
    fi
}

record_private() {
    [[ -f "$OWNER_RECORD" ]] || return 1
    local mode=""
    mode="$(file_mode "$OWNER_RECORD" || true)"
    if [[ "$mode" == 600 || "$mode" == 0600 ]]; then
        return 0
    fi
    [[ "${IZ_CNA_ALLOW_SYNTHETIC_RECORD_MODE:-0}" == 1 && "$mode" == 644 ]]
}

record_shape_valid() {
    local pid=""
    local executable=""
    local data_root=""
    local repo_root=""
    local port=""
    record_private || return 1
    pid="$(record_field pid "$OWNER_RECORD")"
    executable="$(record_field executable "$OWNER_RECORD")"
    data_root="$(record_field data_root "$OWNER_RECORD")"
    repo_root="$(record_field repo_root "$OWNER_RECORD")"
    port="$(record_field port "$OWNER_RECORD")"
    [[ "$pid" =~ ^[1-9][0-9]*$ && -n "$executable" && -n "$data_root" && -n "$repo_root" ]]
    [[ "$port" =~ ^[0-9]+$ && "$port" -ge 1 && "$port" -le 65535 ]]
}

process_is_running() {
    local pid="$1"
    [[ "$pid" =~ ^[1-9][0-9]*$ ]] || return 1
    kill -0 "$pid" 2>/dev/null || return 1
    local command=""
    command="$(process_command "$pid")"
    [[ -n "$command" ]]
}

process_command() {
    local pid="$1"
    local command=""
    command="$(ps -p "$pid" -o command= -ww 2>/dev/null | sed -e 's/^[[:space:]]*//' || true)"
    if [[ -z "$command" && -r "/proc/$pid/cmdline" ]]; then
        command="$(tr '\0' ' ' < "/proc/$pid/cmdline" | sed -e 's/[[:space:]]*$//' || true)"
    fi
    printf '%s\n' "$command"
}

process_matches_record() {
    local pid="$1"
    local executable="$2"
    local data_root="$3"
    local repo_root="$4"
    local command=""
    process_is_running "$pid" || return 1
    command="$(process_command "$pid")"
    [[ "$command" == *"$executable"* ]] || return 1
    [[ "$command" == *"app.desktop_runtime"* ]] || return 1
    [[ "$command" == *"--iz-cna-owner-data-root=$data_root"* ]] || return 1
    [[ "$command" == *"--iz-cna-owner-repo-root=$repo_root"* ]] || return 1
}

write_owner_record() {
    local pid="$1"
    local temporary="$OWNER_RECORD.tmp.$pid"
    (
        umask 077
        {
            printf 'pid=%s\n' "$pid"
            printf 'executable=%s\n' "$VENV_PYTHON"
            printf 'data_root=%s\n' "$APP_DATA_ROOT"
            printf 'repo_root=%s\n' "$ROOT_DIR"
            printf 'port=%s\n' "$PORT"
        } > "$temporary"
        chmod 600 "$temporary"
        mv -f "$temporary" "$OWNER_RECORD"
    )
}

remove_owner_record() {
    [[ -e "$OWNER_RECORD" || -L "$OWNER_RECORD" ]] && rm -f "$OWNER_RECORD"
}

terminate_owned_record() {
    local pid="$1"
    local executable="$2"
    local data_root="$3"
    local repo_root="$4"
    local attempts=0
    if ! process_matches_record "$pid" "$executable" "$data_root" "$repo_root"; then
        return 1
    fi
    kill -TERM "$pid" 2>/dev/null || return 1
    while process_is_running "$pid" && (( attempts < 50 )); do
        sleep 0.1
        attempts=$((attempts + 1))
    done
    if process_is_running "$pid"; then
        if process_matches_record "$pid" "$executable" "$data_root" "$repo_root"; then
            kill -KILL "$pid" 2>/dev/null || true
        else
            return 1
        fi
    fi
    ! process_is_running "$pid"
}

stop_owned_runtime() {
    resolve_data_root || return 1
    OWNER_RECORD="$APP_DATA_ROOT/runtime-owner"
    if [[ ! -e "$OWNER_RECORD" && ! -L "$OWNER_RECORD" ]]; then
        printf '%s\n' 'No owned macOS runtime record was found.'
        return 0
    fi
    if ! record_shape_valid; then
        fail 'unsafe_runtime_record'
        return 1
    fi
    local pid="$(record_field pid "$OWNER_RECORD")"
    local executable="$(record_field executable "$OWNER_RECORD")"
    local data_root="$(record_field data_root "$OWNER_RECORD")"
    local repo_root="$(record_field repo_root "$OWNER_RECORD")"
    if ! process_is_running "$pid"; then
        remove_owner_record
        printf '%s\n' 'Removed stale macOS runtime record.'
        return 0
    fi
    if [[ "$data_root" != "$APP_DATA_ROOT" || "$repo_root" != "$ROOT_DIR" ]] || \
       ! process_matches_record "$pid" "$executable" "$data_root" "$repo_root"; then
        fail 'owned_record_conflict'
        return 1
    fi
    if ! terminate_owned_record "$pid" "$executable" "$data_root" "$repo_root"; then
        fail 'owned_runtime_stop_failed'
        return 1
    fi
    remove_owner_record
    printf '%s\n' 'Stopped the owned macOS runtime.'
}

http_ready() {
    local probe='import sys
from urllib.request import urlopen
try:
    with urlopen(f"http://127.0.0.1:{int(sys.argv[1])}/api/readiness", timeout=1) as response:
        body = response.read(4096)
        raise SystemExit(0 if response.status == 200 and b"status" in body else 1)
except Exception:
    raise SystemExit(1)'
    "$VENV_PYTHON" -c "$probe" "$PORT" >/dev/null 2>&1
}

wait_for_readiness() {
    local pid="$1"
    local deadline=$((SECONDS + READINESS_TIMEOUT))
    while (( SECONDS < deadline )); do
        if ! process_is_running "$pid"; then
            fail 'runtime_exited_before_readiness'
            return 1
        fi
        if http_ready; then
            return 0
        fi
        sleep 0.25
    done
    fail 'readiness_timeout'
    return 1
}

open_browser() {
    [[ "$NO_BROWSER" -eq 1 ]] && return 0
    "$BROWSER_OPENER" "http://127.0.0.1:$PORT" >/dev/null 2>&1 || fail 'browser_open_failed'
}

run_preflight() {
    [[ -f "$PREFLIGHT_SCRIPT" ]] || fail 'preflight_missing' || return 1
    local -a arguments=(--port "$PORT" --report "$PREFLIGHT_REPORT")
    [[ "$ASSUME_YES" -eq 1 ]] && arguments+=(--assume-yes)
    IZ_CNA_PREFLIGHT_ROOT="$ROOT_DIR" \
    IZ_CNA_PREFLIGHT_PORT="$PORT" \
    IZ_CNA_PREFLIGHT_REPORT="$PREFLIGHT_REPORT" \
    IZ_CNA_LOCAL_APP_DATA_DIR="$APP_DATA_ROOT" \
        bash "$PREFLIGHT_SCRIPT" "${arguments[@]}" || fail 'preflight_failed'
}

run_bootstrap() {
    local bootstrap_code='from app.macos_bootstrap import bootstrap
result = bootstrap()
print(result.code.value)
raise SystemExit(0 if result.ok else 3)'
    local bootstrap_output=""
    local bootstrap_error="${TMPDIR:-/tmp}/iz-cna-bootstrap-error.$$"
    bootstrap_output="$(
        IZ_CNA_LOCAL_APP_DATA_DIR="$APP_DATA_ROOT" \
        IZ_CNA_ENV_FILE="$ENV_FILE" \
        PYTHONPATH="$ROOT_DIR/backend" \
            "$VENV_PYTHON" -c "$bootstrap_code" 2>"$bootstrap_error"
    )" || {
        rm -f "$bootstrap_error"
        fail 'bootstrap_failed'
        return 1
    }
    rm -f "$bootstrap_error"
    [[ "$bootstrap_output" == ready ]] || fail 'bootstrap_failed'
}

start_runtime() {
    local pid=""
    mkdir -p "$APP_DATA_ROOT/logs"
    chmod 700 "$APP_DATA_ROOT" "$APP_DATA_ROOT/logs" 2>/dev/null || true
    RUNTIME_LOG="$APP_DATA_ROOT/logs/macos-runtime.log"
    (
        cd "$ROOT_DIR/backend" || exit 1
        export PYTHONPATH="$ROOT_DIR/backend"
        export IZ_CNA_LOCAL_APP_DATA_DIR="$APP_DATA_ROOT"
        export IZ_CNA_ENV_FILE="$ENV_FILE"
        export IZ_CNA_PORT="$PORT"
        exec "$VENV_PYTHON" -m app.desktop_runtime \
            "--iz-cna-owner-data-root=$APP_DATA_ROOT" \
            "--iz-cna-owner-repo-root=$ROOT_DIR"
    ) >> "$RUNTIME_LOG" 2>&1 &
    pid="$!"
    write_owner_record "$pid" || {
        kill -TERM "$pid" 2>/dev/null || true
        fail 'runtime_record_failed'
        return 1
    }
    RUNTIME_PID="$pid"
}

cleanup_failed_start() {
    local pid="$1"
    local executable="$(record_field executable "$OWNER_RECORD" 2>/dev/null || true)"
    local data_root="$(record_field data_root "$OWNER_RECORD" 2>/dev/null || true)"
    local repo_root="$(record_field repo_root "$OWNER_RECORD" 2>/dev/null || true)"
    if [[ -n "$executable" && -n "$data_root" && -n "$repo_root" ]] && \
       process_matches_record "$pid" "$executable" "$data_root" "$repo_root"; then
        terminate_owned_record "$pid" "$executable" "$data_root" "$repo_root" || true
    fi
    if ! process_is_running "$pid"; then
        remove_owner_record
    fi
}

handle_existing_record() {
    [[ -e "$OWNER_RECORD" || -L "$OWNER_RECORD" ]] || return 1
    record_shape_valid || {
        fail 'unsafe_runtime_record'
        return 2
    }
    local pid="$(record_field pid "$OWNER_RECORD")"
    local executable="$(record_field executable "$OWNER_RECORD")"
    local data_root="$(record_field data_root "$OWNER_RECORD")"
    local repo_root="$(record_field repo_root "$OWNER_RECORD")"
    local record_port="$(record_field port "$OWNER_RECORD")"
    if ! process_is_running "$pid"; then
        if [[ "$data_root" == "$APP_DATA_ROOT" && "$repo_root" == "$ROOT_DIR" && \
              "$record_port" == "$PORT" ]]; then
            remove_owner_record
            return 1
        fi
        fail 'owned_record_conflict'
        return 2
    fi
    if [[ "$data_root" != "$APP_DATA_ROOT" || "$repo_root" != "$ROOT_DIR" || \
          "$record_port" != "$PORT" ]] || \
       ! process_matches_record "$pid" "$executable" "$data_root" "$repo_root"; then
        fail 'owned_record_conflict'
        return 2
    fi
    VENV_PYTHON="$executable"
    [[ -x "$VENV_PYTHON" ]] || {
        fail 'runtime_executable_missing'
        return 2
    }
    if ! wait_for_readiness "$pid"; then
        cleanup_failed_start "$pid"
        return 2
    fi
    if ! open_browser; then
        cleanup_failed_start "$pid"
        return 2
    fi
    printf '%s\n' "Reused the ready macOS runtime (PID $pid)."
    return 0
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --port)
            [[ $# -ge 2 ]] || { usage >&2; exit 2; }
            PORT="$2"
            shift 2
            ;;
        --port=*)
            PORT="${1#*=}"
            shift
            ;;
        --no-browser)
            NO_BROWSER=1
            shift
            ;;
        --no-assume-yes)
            ASSUME_YES=0
            shift
            ;;
        --stop)
            STOP_ONLY=1
            shift
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        *)
            usage >&2
            exit 2
            ;;
    esac
done

resolve_data_root || exit 2
read_configured_port
validate_port || exit 2
validate_timeout || exit 2
OWNER_RECORD="$APP_DATA_ROOT/runtime-owner"
ENV_FILE="$APP_DATA_ROOT/.env"
PREFLIGHT_REPORT="$APP_DATA_ROOT/logs/preflight-macos-latest.json"

if [[ "$STOP_ONLY" -eq 1 ]]; then
    stop_owned_runtime
    exit "$?"
fi

existing_status=0
handle_existing_record
existing_status="$?"
if [[ "$existing_status" -eq 0 ]]; then
    exit 0
elif [[ "$existing_status" -eq 2 ]]; then
    exit 2
fi

run_preflight || exit 1
[[ -x "$VENV_PYTHON" ]] || { fail 'runtime_executable_missing'; exit 1; }
run_bootstrap || exit 1
start_runtime || exit 1
pid="$RUNTIME_PID"
if ! wait_for_readiness "$pid"; then
    cleanup_failed_start "$pid"
    exit 1
fi
if ! open_browser; then
    cleanup_failed_start "$pid"
    exit 1
fi
printf '%s\n' "Started macOS runtime on http://$HOST:$PORT (PID $pid)."
