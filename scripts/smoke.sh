#!/usr/bin/env bash
set -euo pipefail

FRONTEND_PORT="${FRONTEND_PORT:-5173}"
BASE_URL="${BASE_URL:-http://localhost:${FRONTEND_PORT}}"
USERNAME="${SMOKE_USERNAME:-admin}"
PASSWORD="${SMOKE_PASSWORD:-r3}"

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || { echo "Missing required command: $1" >&2; exit 1; }
}

need_cmd curl
need_cmd python3

echo "[smoke] Checking frontend HTML at ${BASE_URL}/"
curl -fsS "${BASE_URL}/" >/dev/null

echo "[smoke] Checking API health via frontend proxy"
HEALTH_JSON="$(curl -fsS "${BASE_URL}/api/health")"
python3 -c 'import json,sys; data=json.loads(sys.argv[1]); assert data.get("status")=="ok", data' "$HEALTH_JSON"

echo "[smoke] Logging in via frontend proxy"
LOGIN_JSON="$(curl -fsS -X POST "${BASE_URL}/api/auth/login" -H 'Content-Type: application/json' -d "{\"username\":\"${USERNAME}\",\"password\":\"${PASSWORD}\"}")"
TOKEN="$(python3 -c 'import json,sys; data=json.loads(sys.argv[1]); tok=data.get("access_token"); assert tok, data; print(tok)' "$LOGIN_JSON")"
MUST_RESET="$(python3 -c 'import json,sys; data=json.loads(sys.argv[1]); print("true" if data.get("must_reset_password") else "false")' "$LOGIN_JSON")"

if [[ "$MUST_RESET" == "true" ]]; then
  NEW_PASSWORD="${SMOKE_NEW_PASSWORD:-r3temporarypass!}"
  echo "[smoke] Account requires password reset; resetting with test password"
  curl -fsS -X POST "${BASE_URL}/api/auth/reset-password" \
    -H 'Content-Type: application/json' \
    -H "Authorization: Bearer ${TOKEN}" \
    -d "{\"new_password\":\"${NEW_PASSWORD}\"}" >/dev/null

  LOGIN_JSON="$(curl -fsS -X POST "${BASE_URL}/api/auth/login" -H 'Content-Type: application/json' -d "{\"username\":\"${USERNAME}\",\"password\":\"${NEW_PASSWORD}\"}")"
  TOKEN="$(python3 -c 'import json,sys; data=json.loads(sys.argv[1]); tok=data.get("access_token"); assert tok, data; print(tok)' "$LOGIN_JSON")"
fi

echo "[smoke] Loading current user"
ME_JSON="$(curl -fsS "${BASE_URL}/api/users/me" -H "Authorization: Bearer ${TOKEN}")"
python3 -c 'import json,sys; data=json.loads(sys.argv[1]); assert data.get("username"), data; print("[smoke] Authenticated as", data["username"])' "$ME_JSON"

echo "[smoke] Loading charts"
curl -fsS "${BASE_URL}/api/charts" -H "Authorization: Bearer ${TOKEN}" >/dev/null

echo "[smoke] PASS"
