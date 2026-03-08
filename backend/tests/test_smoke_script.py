import json
import os
import stat
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SMOKE_SCRIPT = REPO_ROOT / 'scripts' / 'smoke.sh'


FAKE_CURL = """#!/usr/bin/env python3
import json
import os
import sys
from urllib.parse import urlparse


def find_arg(flag):
    for index, arg in enumerate(sys.argv[1:]):
        if arg == flag:
            return sys.argv[index + 2]
    return None


def has_flag(flag):
    return flag in sys.argv[1:]


def find_url():
    for arg in reversed(sys.argv[1:]):
        if arg.startswith('http://') or arg.startswith('https://'):
            return arg
    return ''


def fail(body, status=22):
    if has_flag('-f') or has_flag('--fail'):
        print(body, end='')
        raise SystemExit(status)
    print(body, end='')
    raise SystemExit(0)


state_path = os.environ['SMOKE_CURL_STATE']
with open(state_path, 'r', encoding='utf-8') as handle:
    state = json.load(handle)

method = find_arg('-X') or 'GET'
payload = find_arg('-d')
url = find_url()
path = urlparse(url).path or '/'

if method == 'GET' and path == '/':
    print('<html><body>ok</body></html>', end='')
elif method == 'GET' and path == '/api/health':
    print(json.dumps({'status': 'ok'}), end='')
elif method == 'POST' and path == '/api/auth/login':
    request = json.loads(payload or '{}')
    if request.get('username') != 'admin' or request.get('password') != state['current_password']:
        fail(json.dumps({'detail': 'Invalid credentials'}))

    print(
        json.dumps(
            {
                'access_token': 'smoke-token',
                'must_reset_password': state['requires_reset'],
            }
        ),
        end='',
    )
elif method == 'POST' and path == '/api/auth/reset-password':
    if f"Bearer {state['token']}" != find_arg('-H') and f"Authorization: Bearer {state['token']}" not in sys.argv[1:]:
        fail(json.dumps({'detail': 'Unauthorized'}))

    request = json.loads(payload or '{}')
    state['reset_calls'] += 1
    state['last_reset_password'] = request['new_password']
    state['current_password'] = request['new_password']
    state['requires_reset'] = False
    print(json.dumps({'status': 'ok'}), end='')
elif method == 'GET' and path == '/api/users/me':
    if f"Authorization: Bearer {state['token']}" not in sys.argv[1:]:
        fail(json.dumps({'detail': 'Unauthorized'}))

    print(
        json.dumps(
            {
                'id': 1,
                'username': 'admin',
                'role': 'admin',
                'must_reset_password': state['requires_reset'],
            }
        ),
        end='',
    )
elif method == 'GET' and path == '/api/charts':
    if f"Authorization: Bearer {state['token']}" not in sys.argv[1:]:
        fail(json.dumps({'detail': 'Unauthorized'}))

    print('[]', end='')
else:
    fail(json.dumps({'detail': f'Unhandled request {method} {path}'}))

with open(state_path, 'w', encoding='utf-8') as handle:
    json.dump(state, handle)
"""


def write_fake_curl(tmp_path: Path) -> Path:
    fake_curl = tmp_path / 'curl'
    fake_curl.write_text(FAKE_CURL, encoding='utf-8')
    fake_curl.chmod(fake_curl.stat().st_mode | stat.S_IEXEC)
    return fake_curl


def run_smoke(tmp_path: Path, state: dict[str, object], extra_env: dict[str, str] | None = None):
    write_fake_curl(tmp_path)
    state_path = tmp_path / 'curl-state.json'
    state_path.write_text(json.dumps(state), encoding='utf-8')

    env = os.environ.copy()
    env['BASE_URL'] = 'http://smoke.test'
    env['SMOKE_USERNAME'] = 'admin'
    env['SMOKE_PASSWORD'] = 'bootstrap-pass-1234'
    env['SMOKE_CURL_STATE'] = str(state_path)
    env['PATH'] = f"{tmp_path}:{env['PATH']}"
    if extra_env:
        env.update(extra_env)

    result = subprocess.run(
        ['bash', str(SMOKE_SCRIPT)],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    final_state = json.loads(state_path.read_text(encoding='utf-8'))
    return result, final_state


def test_smoke_does_not_reset_password_by_default(tmp_path: Path):
    result, final_state = run_smoke(
        tmp_path,
        {
            'current_password': 'bootstrap-pass-1234',
            'requires_reset': True,
            'reset_calls': 0,
            'last_reset_password': None,
            'token': 'smoke-token',
        },
    )

    assert result.returncode == 0, result.stderr or result.stdout
    assert final_state['reset_calls'] == 0
    assert 'without mutating credentials' in result.stdout
    assert 'skipping chart load in read-only mode' in result.stdout


def test_smoke_can_reset_password_when_explicitly_enabled(tmp_path: Path):
    result, final_state = run_smoke(
        tmp_path,
        {
            'current_password': 'bootstrap-pass-1234',
            'requires_reset': True,
            'reset_calls': 0,
            'last_reset_password': None,
            'token': 'smoke-token',
        },
        {
            'SMOKE_RESET_PASSWORD': 'true',
            'SMOKE_NEW_PASSWORD': 'replacement-pass-1234',
        },
    )

    assert result.returncode == 0, result.stderr or result.stdout
    assert final_state['reset_calls'] == 1
    assert final_state['last_reset_password'] == 'replacement-pass-1234'
    assert final_state['current_password'] == 'replacement-pass-1234'
    assert '[smoke] Loading charts' in result.stdout
