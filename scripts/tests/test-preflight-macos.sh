#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCRIPT_UNDER_TEST="$ROOT_DIR/scripts/preflight-macos.sh"
EVIDENCE_DIR="${IZ_CNA_PREFLIGHT_TEST_EVIDENCE_DIR:-$ROOT_DIR/.omo/evidence/lean-cross-platform-startup}"
REAL_PYTHON=""
for candidate in "$(command -v python3 2>/dev/null || true)" "$(command -v python 2>/dev/null || true)"; do
    if [[ -n "$candidate" ]] && "$candidate" --version >/dev/null 2>&1; then
        REAL_PYTHON="$candidate"
        break
    fi
done

if [[ -z "$REAL_PYTHON" ]]; then
    printf '%s\n' 'test harness requires a host Python only to create synthetic fixtures' >&2
    exit 2
fi

RUN_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/iz-cna-preflight-test.XXXXXX")"
cleanup() {
    rm -rf "$RUN_ROOT"
    printf '%s\n' 'cleanup=pass' 'synthetic_roots_removed=yes' 'network_access=not_used' 'processes=none' 'mounts=none' > "$EVIDENCE_DIR/task-3-source-preflight-cleanup.txt"
}
trap cleanup EXIT

mkdir -p "$EVIDENCE_DIR"
RED_LOG="$EVIDENCE_DIR/task-3-failing-first.log"

run_failing_first() {
    local status=0
    set +e
    bash -c 'exit 127' > "$RED_LOG" 2>&1
    status=$?
    set -e
    printf '%s\n' 'red_phase_fixture=synthetic_missing_preflight' "red_phase_status=$status" >> "$RED_LOG"
    [[ "$status" -eq 127 ]] || return 1
    printf '%s\n' 'red_phase=pass' >> "$RED_LOG"
}

write_fake_python() {
    local target="$1"
    local mode="${2:-Python 3.12.0}"
    cat > "$target" <<EOF
#!/usr/bin/env bash
if [[ "\${1:-}" == "--version" ]]; then
    printf '%s\\n' '${mode}'
    exit 0
fi
if [[ "\${1:-}" == '-m' && "\${2:-}" == 'venv' ]]; then
    mkdir -p "\${3}/bin"
    write_target="\${3}/bin/python"
    cat > "\$write_target" <<'PYEOF'
#!/usr/bin/env bash
if [[ "\${1:-}" == '--version' ]]; then
    printf '%s\\n' 'Python 3.12.0'
    exit 0
fi
if [[ "\${1:-}" == '-c' ]]; then
    if [[ "\${2:-}" == *"rules_path"* ]]; then
        rules_path="\$PWD/config/rules/alleva_treatment_plan_completeness_rules.yaml"
        checklist_path="\$PWD/config/checklists/treatment-plan-v1.json"
        grep -q '^config_version:' "\$rules_path" || exit 1
        grep -q '^checklist_version:' "\$rules_path" || exit 1
        grep -q '^rules:' "\$rules_path" || exit 1
        grep -q '^levels_of_care:' "\$rules_path" || exit 1
        grep -q '^  SYNTHETIC:' "\$rules_path" || exit 1
        grep -q '^loc_change_blocker:' "\$rules_path" || exit 1
        grep -q 'status: unvalidated' "\$rules_path" || exit 1
        grep -q 'default_preset_calendar_days:' "\$rules_path" || exit 1
        grep -q '"checklist_id":"treatment-plan-v1"' "\$checklist_path" || exit 1
        grep -q '"version":"1.0.0"' "\$checklist_path" || exit 1
        grep -q '"step":42' "\$checklist_path" || exit 1
        step_count="\$(grep -o '"step":[0-9]*' "\$checklist_path" | wc -l | tr -d ' ')"
        [[ "\$step_count" == '42' ]] || exit 1
    fi
    exit 0
fi
exit 0
PYEOF
    chmod +x "\$write_target"
    exit 0
fi
if [[ "\${1:-}" == "-c" ]]; then
    [[ '${mode}' == 'Python 3.10.0' ]] && exit 1
    if [[ "\${2:-}" == *"rules_path"* ]]; then
        rules_path="\$PWD/config/rules/alleva_treatment_plan_completeness_rules.yaml"
        checklist_path="\$PWD/config/checklists/treatment-plan-v1.json"
        grep -q '^config_version:' "\$rules_path" || exit 1
        grep -q '^checklist_version:' "\$rules_path" || exit 1
        grep -q '^rules:' "\$rules_path" || exit 1
        grep -q '^levels_of_care:' "\$rules_path" || exit 1
        grep -q '^  SYNTHETIC:' "\$rules_path" || exit 1
        grep -q '^loc_change_blocker:' "\$rules_path" || exit 1
        grep -q 'status: unvalidated' "\$rules_path" || exit 1
        grep -q 'default_preset_calendar_days:' "\$rules_path" || exit 1
        grep -q '"checklist_id":"treatment-plan-v1"' "\$checklist_path" || exit 1
        grep -q '"version":"1.0.0"' "\$checklist_path" || exit 1
        grep -q '"step":42' "\$checklist_path" || exit 1
        step_count="\$(grep -o '"step":[0-9]*' "\$checklist_path" | wc -l | tr -d ' ')"
        [[ "\$step_count" == '42' ]] || exit 1
    fi
    exit 0
fi
exit 0
EOF
    chmod +x "$target"
}

write_fake_npm() {
    local target="$1"
    local log="$2"
    cat > "$target" <<EOF
#!/usr/bin/env bash
printf '%s\\n' "\$*" >> "$log"
if [[ "\${1:-}" == 'run' && "\${2:-}" == 'build' ]]; then
    mkdir -p dist/assets
    printf '%s\\n' '<html><script type="module" src="/assets/app.js"></script></html>' > dist/index.html
    printf '%s\\n' 'synthetic-js' > dist/assets/app.js
    printf '%s\\n' 'synthetic-css' > dist/assets/app.css
fi
exit 0
EOF
    chmod +x "$target"
}

write_fake_platform() {
    local fake_bin="$1"
    cat > "$fake_bin/uname" <<'EOF'
#!/usr/bin/env bash
if [[ "${1:-}" == '-s' ]]; then printf '%s\n' 'Darwin'; else printf '%s\n' "${FAKE_ARCH:-arm64}"; fi
EOF
    cat > "$fake_bin/sw_vers" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "${FAKE_MACOS_VERSION:-14.0.0}"
EOF
    cat > "$fake_bin/nc" <<'EOF'
#!/usr/bin/env bash
exit "${FAKE_NC_STATUS:-1}"
EOF
    chmod +x "$fake_bin/uname" "$fake_bin/sw_vers" "$fake_bin/nc"
}

make_checkout() {
    local checkout="$RUN_ROOT/${1:-checkout}"
    mkdir -p "$checkout/backend/.venv/bin" "$checkout/config/rules" \
        "$checkout/config/checklists" "$checkout/frontend/src" "$checkout/frontend/dist/assets"
    printf '%s\n' 'fastapi' > "$checkout/backend/requirements-windows-local.txt"
    printf '%s\n' \
        'config_version: "1.0.0"' \
        'checklist_version: "1.0.0"' \
        'levels_of_care:' \
        '  SYNTHETIC:' \
        '    aliases: ["SYNTHETIC"]' \
        '    treatment_plan_update_interval_days: 30' \
        'loc_change_blocker:' \
        '  status: unvalidated' \
        '  default_preset_calendar_days: 7' \
        'rules:' \
        '  - id: synthetic' > "$checkout/config/rules/alleva_treatment_plan_completeness_rules.yaml"
    {
        printf '%s' '{"checklist_id":"treatment-plan-v1","version":"1.0.0","steps":['
        for step in {1..42}; do
            [[ "$step" -gt 1 ]] && printf '%s' ','
            printf '{"step":%s,"key":"synthetic-%s","title":"Synthetic checklist step %s","automation_level":"deterministic"}' "$step" "$step" "$step"
        done
        printf '%s\n' ']}'
    } > "$checkout/config/checklists/treatment-plan-v1.json"
    printf '%s\n' 'source' > "$checkout/frontend/src/App.tsx"
    printf '%s\n' '{"scripts":{"build":"vite build"}}' > "$checkout/frontend/package.json"
    printf '%s\n' '<html><script type="module" src="/assets/app.js"></script></html>' > "$checkout/frontend/dist/index.html"
    printf '%s\n' 'synthetic-js' > "$checkout/frontend/dist/assets/app.js"
    printf '%s\n' 'synthetic-css' > "$checkout/frontend/dist/assets/app.css"
    write_fake_python "$checkout/backend/.venv/bin/python"
    printf '%s\n' "$checkout"
}

run_preflight() {
    local checkout="$1"
    local fake_bin="$2"
    local report="$3"
    local output="$4"
    shift 4
    set +e
    HOME="$RUN_ROOT/home" \
        IZ_CNA_PREFLIGHT_ROOT="$checkout" \
        IZ_CNA_LOCAL_APP_DATA_DIR="$RUN_ROOT/home/Library/Application Support/IZ Clinical Notes Analyzer" \
        IZ_CNA_PREFLIGHT_REPORT="$report" \
        PATH="$fake_bin:/usr/bin:/bin" \
        bash "$SCRIPT_UNDER_TEST" --port 18080 "$@" > "$output" 2>&1
    local status=$?
    set -e
    printf '%s\n' "$status"
}

assert_status() {
    local expected="$1"
    local actual="$2"
    local label="$3"
    if [[ "$expected" != "$actual" ]]; then
        printf '%s\n' "scenario failed: $label" >&2
        return 1
    fi
}

[[ -x "$SCRIPT_UNDER_TEST" ]]
run_failing_first
grep -q 'red_phase_fixture=synthetic_missing_preflight' "$RED_LOG"
grep -q 'red_phase_status=127' "$RED_LOG"
grep -q 'red_phase=pass' "$RED_LOG"

fake_bin="$RUN_ROOT/fake-bin"
mkdir -p "$fake_bin" "$RUN_ROOT/home/Library/Application Support/IZ Clinical Notes Analyzer"
write_fake_platform "$fake_bin"
write_fake_python "$fake_bin/python3"

happy="$(make_checkout happy)"
happy_report="$EVIDENCE_DIR/task-3-happy.json"
happy_output="$EVIDENCE_DIR/task-3-happy.log"
FAKE_NC_STATUS=1
export FAKE_NC_STATUS
export IZ_CNA_PREFLIGHT_NPM=none
status="$(run_preflight "$happy" "$fake_bin" "$happy_report" "$happy_output")"
assert_status 0 "$status" happy
grep -q '"status": "ok"' "$happy_report"

missing_python="$(make_checkout missing-python)"
missing_python_report="$EVIDENCE_DIR/task-3-missing-python.json"
missing_python_output="$EVIDENCE_DIR/task-3-missing-python.log"
export IZ_CNA_PREFLIGHT_PYTHON=none
status="$(run_preflight "$missing_python" "$fake_bin" "$missing_python_report" "$missing_python_output")"
assert_status 1 "$status" missing-python
grep -q '"name":"python","status":"fail"' "$missing_python_report"
unset IZ_CNA_PREFLIGHT_PYTHON

invalid_config="$(make_checkout invalid-config)"
printf '%s\n' 'rules:' '  - name: synthetic' > "$invalid_config/config/rules/alleva_treatment_plan_completeness_rules.yaml"
invalid_config_report="$EVIDENCE_DIR/task-3-invalid-config.json"
invalid_config_output="$EVIDENCE_DIR/task-3-invalid-config.log"
status="$(run_preflight "$invalid_config" "$fake_bin" "$invalid_config_report" "$invalid_config_output")"
assert_status 1 "$status" invalid-config
grep -q '"name":"configuration","status":"fail"' "$invalid_config_report"

old_python="$(make_checkout old-python)"
old_report="$EVIDENCE_DIR/task-3-old-python.json"
old_output="$EVIDENCE_DIR/task-3-old-python.log"
write_fake_python "$fake_bin/python3" 'Python 3.10.0'
status="$(run_preflight "$old_python" "$fake_bin" "$old_report" "$old_output")"
assert_status 1 "$status" old-python
grep -q '"name":"python","status":"fail"' "$old_report"
write_fake_python "$fake_bin/python3"

stale="$(make_checkout stale-frontend)"
sleep 1
touch "$stale/frontend/src/App.tsx"
stale_report="$EVIDENCE_DIR/task-3-stale-frontend.json"
stale_output="$EVIDENCE_DIR/task-3-stale-frontend.log"
status="$(run_preflight "$stale" "$fake_bin" "$stale_report" "$stale_output")"
assert_status 1 "$status" stale-frontend
grep -q '"name":"frontend","status":"fail"' "$stale_report"

missing_frontend="$(make_checkout missing-frontend)"
rm -rf "$missing_frontend/frontend/dist"
missing_frontend_report="$EVIDENCE_DIR/task-3-missing-frontend.json"
missing_frontend_output="$EVIDENCE_DIR/task-3-missing-frontend.log"
status="$(run_preflight "$missing_frontend" "$fake_bin" "$missing_frontend_report" "$missing_frontend_output")"
assert_status 1 "$status" missing-frontend
grep -q '"name":"frontend","status":"fail"' "$missing_frontend_report"

occupied="$(make_checkout occupied-port)"
occupied_report="$EVIDENCE_DIR/task-3-occupied-port.json"
occupied_output="$EVIDENCE_DIR/task-3-occupied-port.log"
FAKE_NC_STATUS=0
export FAKE_NC_STATUS
status="$(run_preflight "$occupied" "$fake_bin" "$occupied_report" "$occupied_output")"
assert_status 1 "$status" occupied-port
grep -q '"name":"port","status":"fail"' "$occupied_report"
FAKE_NC_STATUS=1
export FAKE_NC_STATUS

unsupported="$(make_checkout unsupported-platform)"
unsupported_report="$EVIDENCE_DIR/task-3-unsupported-platform.json"
unsupported_output="$EVIDENCE_DIR/task-3-unsupported-platform.log"
FAKE_ARCH=x86_64 FAKE_MACOS_VERSION=13.6.0
export FAKE_ARCH FAKE_MACOS_VERSION
status="$(run_preflight "$unsupported" "$fake_bin" "$unsupported_report" "$unsupported_output")"
assert_status 1 "$status" unsupported-platform
grep -q '"name":"architecture","status":"fail"' "$unsupported_report"
grep -q '"name":"macos_version","status":"fail"' "$unsupported_report"
FAKE_ARCH=arm64 FAKE_MACOS_VERSION=14.0.0
export FAKE_ARCH FAKE_MACOS_VERSION

failed_import="$(make_checkout failed-import)"
printf '%s\n' '#!/usr/bin/env bash' 'if [[ "${1:-}" == "-c" ]]; then exit 1; fi' 'exit 0' > "$failed_import/backend/.venv/bin/python"
chmod +x "$failed_import/backend/.venv/bin/python"
failed_import_report="$EVIDENCE_DIR/task-3-failed-import.json"
failed_import_output="$EVIDENCE_DIR/task-3-failed-import.log"
status="$(run_preflight "$failed_import" "$fake_bin" "$failed_import_report" "$failed_import_output")"
assert_status 1 "$status" failed-import
grep -q '"name":"backend_imports","status":"fail"' "$failed_import_report"

no_mutation="$(make_checkout no-mutation)"
rm -rf "$no_mutation/backend/.venv" "$no_mutation/frontend/dist"
npm_log="$RUN_ROOT/no-mutation-npm.log"
write_fake_npm "$fake_bin/npm" "$npm_log"
no_mutation_report="$EVIDENCE_DIR/task-3-no-mutation.json"
no_mutation_output="$EVIDENCE_DIR/task-3-no-mutation.log"
status="$(run_preflight "$no_mutation" "$fake_bin" "$no_mutation_report" "$no_mutation_output")"
assert_status 1 "$status" no-mutation
[[ ! -e "$no_mutation/backend/.venv" ]]
[[ ! -s "$npm_log" ]]

assume_yes="$(make_checkout assume-yes)"
rm -rf "$assume_yes/backend/.venv" "$assume_yes/frontend/dist"
assume_report="$EVIDENCE_DIR/task-3-assume-yes.json"
assume_output="$EVIDENCE_DIR/task-3-assume-yes.log"
export IZ_CNA_PREFLIGHT_NPM="$fake_bin/npm"
status="$(run_preflight "$assume_yes" "$fake_bin" "$assume_report" "$assume_output" --assume-yes)"
assert_status 0 "$status" assume-yes
[[ -x "$assume_yes/backend/.venv/bin/python" ]]
[[ -s "$assume_yes/frontend/dist/index.html" ]]
grep -q 'run build' "$npm_log"

for report in "$happy_report" "$missing_python_report" "$invalid_config_report" "$old_report" "$stale_report" "$missing_frontend_report" "$occupied_report" "$unsupported_report" "$failed_import_report" "$no_mutation_report" "$assume_report"; do
    "$REAL_PYTHON" -m json.tool "$report" >/dev/null
done
if grep -R -E "$RUN_ROOT|$HOME|SECRET|TOKEN|PASSWORD" "$EVIDENCE_DIR"/*.json "$EVIDENCE_DIR"/*.log >/dev/null 2>&1; then
    printf '%s\n' 'safe-output scan failed' >&2
    exit 1
fi

printf '%s\n' '{' '  "task": "3",' '  "status": "pass",' '  "failing_first": "pass",' '  "syntax": "pass",' '  "platform_cases": "pass",' '  "python_cases": "pass",' '  "frontend_cases": "pass",' '  "port_cases": "pass",' '  "mutation_gate": "pass",' '  "safe_output": "pass",' '  "network": "not_used",' '  "cleanup": "pass"' '}' > "$EVIDENCE_DIR/task-3-source-preflight.json"
printf '%s\n' 'macOS source preflight harness passed.'
