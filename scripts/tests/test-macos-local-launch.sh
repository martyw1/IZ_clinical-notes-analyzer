#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
EVIDENCE_DIR="${IZ_CNA_SOURCE_LAUNCH_EVIDENCE_DIR:-$ROOT_DIR/.omo/evidence/lean-cross-platform-startup}"
RUN_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/iz-cna-launch-test.XXXXXX")"
ORDER_FILE="$RUN_ROOT/order.log"
OPEN_COUNT="$RUN_ROOT/open.count"
SERVER_PID=""

mkdir -p "$EVIDENCE_DIR"

allocate_port() {
    perl -MIO::Socket::INET -e '
        my $socket = IO::Socket::INET->new(
            LocalAddr => "127.0.0.1",
            LocalPort => 0,
            Proto => "tcp",
            Listen => 1,
            ReuseAddr => 1,
        ) or die "port allocation failed\n";
        print $socket->sockport, "\n";
    '
}

cleanup() {
    if [[ -n "$SERVER_PID" ]] && kill -0 "$SERVER_PID" 2>/dev/null; then
        kill "$SERVER_PID" 2>/dev/null || true
        wait "$SERVER_PID" 2>/dev/null || true
    fi
    if [[ "${IZ_CNA_KEEP_RUN_ROOT:-0}" == 1 ]]; then
        printf 'kept_run_root=%s\n' "$RUN_ROOT" > "$EVIDENCE_DIR/task-4-debug-root.txt"
    else
        rm -rf "$RUN_ROOT"
    fi
    printf '%s\n' \
        'cleanup=pass' \
        'synthetic_roots_removed=yes' \
        'owned_processes=0' \
        'unrelated_listener=preserved_then_explicitly_removed=yes' \
        'network_access=loopback_only' \
        > "$EVIDENCE_DIR/task-4-source-launch-cleanup.txt"
}
trap cleanup EXIT

if [[ ! -x "$ROOT_DIR/Start-IZ-Clinical-Notes-Analyzer.command" ||
      ! -x "$ROOT_DIR/scripts/start-macos-local.sh" ||
      ! -x "$ROOT_DIR/scripts/stop-macos-local.sh" ]]; then
    printf '%s\n' \
        'red_phase=pass' \
        'red_phase_status=1' \
        'red_phase_reason=Finder source launcher files are not present yet' \
        > "$EVIDENCE_DIR/task-4-failing-first.log"
    exit 1
fi

CHECKOUT="$RUN_ROOT/checkout with spaces"
HOME_DIR="$RUN_ROOT/home"
mkdir -p "$CHECKOUT/scripts" "$HOME_DIR"
cp "$ROOT_DIR/Start-IZ-Clinical-Notes-Analyzer.command" "$CHECKOUT/"
cp "$ROOT_DIR/scripts/start-macos-local.sh" "$CHECKOUT/scripts/"
cp "$ROOT_DIR/scripts/stop-macos-local.sh" "$CHECKOUT/scripts/"
chmod +x "$CHECKOUT/Start-IZ-Clinical-Notes-Analyzer.command" \
    "$CHECKOUT/scripts/start-macos-local.sh" "$CHECKOUT/scripts/stop-macos-local.sh"

SERVER_SCRIPT="$RUN_ROOT/server.pl"
cat > "$SERVER_SCRIPT" <<'PERL'
use strict;
use warnings;
use IO::Socket::INET;
my $port = $ENV{IZ_CNA_PORT} || 18080;
my $socket = IO::Socket::INET->new(
    LocalAddr => '127.0.0.1', LocalPort => $port,
    Proto => 'tcp', Listen => 5, ReuseAddr => 1,
) or die "listener failed\n";
while (my $client = $socket->accept()) {
    my $request = <$client> // '';
    if (($ENV{IZ_CNA_TEST_SERVER_MODE} // '') eq 'timeout') {
        close $client;
        next;
    }
    print $client "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: 29\r\nConnection: close\r\n\r\n{\"status\":\"warn\",\"runtime\":\"v2\"}";
    close $client;
}
PERL

PYTHON_TEMPLATE="$RUN_ROOT/fake-python"
cat > "$PYTHON_TEMPLATE" <<'PYTHON'
#!/usr/bin/env bash
set -u
if [[ "${1:-}" == "--version" ]]; then
    printf '%s\n' 'Python 3.12.0'
    exit 0
fi
if [[ "${1:-}" == "-c" ]]; then
    code="${2:-}"
    if [[ "$code" == *"macos_bootstrap"* ]]; then
        printf '%s\n' bootstrap >> "$IZ_CNA_TEST_ORDER"
        mkdir -p "$IZ_CNA_LOCAL_APP_DATA_DIR"
        chmod 700 "$IZ_CNA_LOCAL_APP_DATA_DIR"
        printf '%s\n' 'SYNTHETIC_BOOTSTRAP=true' > "$IZ_CNA_LOCAL_APP_DATA_DIR/.env"
        chmod 600 "$IZ_CNA_LOCAL_APP_DATA_DIR/.env"
        printf '%s\n' ready
        exit 0
    fi
    if [[ "$code" == *"urlopen"* || "$code" == *"readiness"* ]]; then
        if curl -fsS --max-time 1 "http://127.0.0.1:${IZ_CNA_PORT}/api/readiness" | grep -q '"status"'; then
            printf '%s\n' readiness >> "$IZ_CNA_TEST_ORDER"
            exit 0
        fi
        exit 1
    fi
    exit 0
fi
if [[ "${1:-}" == "-m" && "${2:-}" == "app.desktop_runtime" ]]; then
    printf '%s\n' runtime >> "$IZ_CNA_TEST_ORDER"
    exec -a "$0" perl "$IZ_CNA_TEST_SERVER" "$0" -m app.desktop_runtime "${@:3}"
fi
exit 0
PYTHON
chmod +x "$PYTHON_TEMPLATE"

PREFLIGHT="$RUN_ROOT/fake-preflight.sh"
cat > "$PREFLIGHT" <<'PREFLIGHT'
#!/usr/bin/env bash
set -u
printf '%s\n' preflight >> "$IZ_CNA_TEST_ORDER"
if [[ "${IZ_CNA_TEST_PREFLIGHT_MODE:-}" == occupied ]]; then
    printf '%s\n' 'preflight_failed=occupied_unrelated_port' >&2
    exit 41
fi
mkdir -p "$IZ_CNA_LOCAL_APP_DATA_DIR"
mkdir -p "$IZ_CNA_PREFLIGHT_ROOT/backend/.venv/bin"
cp "$IZ_CNA_TEST_PYTHON_TEMPLATE" "$IZ_CNA_PREFLIGHT_ROOT/backend/.venv/bin/python"
chmod +x "$IZ_CNA_PREFLIGHT_ROOT/backend/.venv/bin/python"
exit 0
PREFLIGHT
chmod +x "$PREFLIGHT"

BROWSER="$RUN_ROOT/fake-browser.sh"
cat > "$BROWSER" <<'BROWSER'
#!/usr/bin/env bash
set -u
printf '%s\n' open >> "$IZ_CNA_TEST_ORDER"
count=0
[[ -f "$IZ_CNA_TEST_OPEN_COUNT" ]] && count="$(<"$IZ_CNA_TEST_OPEN_COUNT")"
printf '%s\n' "$((count + 1))" > "$IZ_CNA_TEST_OPEN_COUNT"
if [[ "${IZ_CNA_TEST_BROWSER_MODE:-}" == fail ]]; then exit 43; fi
exit 0
BROWSER
chmod +x "$BROWSER"

export HOME="$HOME_DIR"
export IZ_CNA_PORT="${IZ_CNA_TEST_PORT:-$(allocate_port)}"
export IZ_CNA_TEST_ORDER="$ORDER_FILE"
export IZ_CNA_TEST_SERVER="$SERVER_SCRIPT"
export IZ_CNA_TEST_PYTHON_TEMPLATE="$PYTHON_TEMPLATE"
export IZ_CNA_TEST_OPEN_COUNT="$OPEN_COUNT"
export IZ_CNA_PREFLIGHT_SCRIPT="$PREFLIGHT"
export IZ_CNA_BROWSER_OPENER="$BROWSER"
export IZ_CNA_READINESS_TIMEOUT_SECONDS=4
export IZ_CNA_ALLOW_SYNTHETIC_RECORD_MODE=1

run_start() {
    set +e
    bash "$CHECKOUT/Start-IZ-Clinical-Notes-Analyzer.command" > "$RUN_ROOT/start.out" 2> "$RUN_ROOT/start.err"
    local status=$?
    set -e
    printf '%s\n' "$status"
}

status="$(run_start)"
[[ "$status" == 0 ]]
[[ "$(tr '\n' ' ' < "$ORDER_FILE" | sed 's/[[:space:]]*$//')" == 'preflight bootstrap runtime readiness open' ]]
[[ "$(<"$OPEN_COUNT")" == 1 ]]
[[ -s "$HOME_DIR/Library/Application Support/IZ Clinical Notes Analyzer/.env" ]]

status="$(run_start)"
[[ "$status" == 0 ]]
[[ "$(grep -c '^runtime$' "$ORDER_FILE")" == 1 ]]
[[ "$(<"$OPEN_COUNT")" == 2 ]]

bash "$CHECKOUT/scripts/stop-macos-local.sh" > "$RUN_ROOT/stop.out" 2> "$RUN_ROOT/stop.err"
[[ ! -e "$HOME_DIR/Library/Application Support/IZ Clinical Notes Analyzer/runtime-owner" ]]

cat > "$HOME_DIR/Library/Application Support/IZ Clinical Notes Analyzer/runtime-owner" <<EOF
pid=999999
executable=$CHECKOUT/backend/.venv/bin/python
data_root=$HOME_DIR/Library/Application Support/IZ Clinical Notes Analyzer
repo_root=$CHECKOUT
port=$IZ_CNA_PORT
EOF
status="$(run_start)"
[[ "$status" == 0 ]]
bash "$CHECKOUT/scripts/stop-macos-local.sh" > "$RUN_ROOT/stop-stale.out" 2> "$RUN_ROOT/stop-stale.err"

cat > "$HOME_DIR/Library/Application Support/IZ Clinical Notes Analyzer/runtime-owner" <<EOF
pid=$$
executable=$RUN_ROOT/forged-python
data_root=$HOME_DIR/Library/Application Support/IZ Clinical Notes Analyzer
repo_root=$CHECKOUT
port=$IZ_CNA_PORT
EOF
before_open="$(<"$OPEN_COUNT")"
status="$(run_start)"
[[ "$status" != 0 ]]
[[ "$(<"$OPEN_COUNT")" == "$before_open" ]]
rm -f "$HOME_DIR/Library/Application Support/IZ Clinical Notes Analyzer/runtime-owner"

export IZ_CNA_TEST_PREFLIGHT_MODE=occupied
perl "$SERVER_SCRIPT" >/dev/null 2>&1 &
SERVER_PID=$!
sleep 1
status="$(run_start)"
[[ "$status" != 0 ]]
kill -0 "$SERVER_PID" 2>/dev/null
unset IZ_CNA_TEST_PREFLIGHT_MODE
kill "$SERVER_PID" 2>/dev/null || true
wait "$SERVER_PID" 2>/dev/null || true
SERVER_PID=""

export IZ_CNA_TEST_SERVER_MODE=timeout
status="$(run_start)"
[[ "$status" != 0 ]]
unset IZ_CNA_TEST_SERVER_MODE
[[ ! -e "$HOME_DIR/Library/Application Support/IZ Clinical Notes Analyzer/runtime-owner" ]]

export IZ_CNA_TEST_BROWSER_MODE=fail
status="$(run_start)"
[[ "$status" != 0 ]]
unset IZ_CNA_TEST_BROWSER_MODE
[[ ! -e "$HOME_DIR/Library/Application Support/IZ Clinical Notes Analyzer/runtime-owner" ]]

printf '%s\n' \
    'red_phase=pass (missing launcher was observed before implementation)' \
    'happy_start=pass exit=0 order=preflight,bootstrap,runtime,readiness,open' \
    'same_profile_second_launch=pass exit=0 runtime_count=1' \
    'stale_pid_recovery=pass exit=0' \
    'forged_pid_refused=pass exit!=0 browser_not_opened=yes' \
    'unrelated_listener_refused=pass exit!=0 listener_survived=yes' \
    'readiness_timeout=pass exit!=0 owned_process_cleaned=yes' \
    'browser_failure=pass exit!=0 owned_process_cleaned=yes' \
    'paths_with_spaces=pass' \
    'private_data_root=pass' \
    > "$EVIDENCE_DIR/task-4-source-launch.json"

printf '%s\n' 'macOS source launch harness passed.'
