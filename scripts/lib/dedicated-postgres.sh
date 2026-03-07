#!/usr/bin/env bash

startup_db_info() {
  if declare -F info >/dev/null 2>&1; then
    info "$@"
  else
    echo "[INFO] $*"
  fi
}

startup_db_warn() {
  if declare -F warn >/dev/null 2>&1; then
    warn "$@"
  else
    echo "[WARN] $*" >&2
  fi
}

startup_db_pass() {
  if declare -F pass >/dev/null 2>&1; then
    pass "$@"
  else
    echo "[PASS] $*"
  fi
}

startup_db_env_value() {
  local env_file="$1"
  local key="$2"

  [[ -f "$env_file" ]] || return 0
  awk -F= -v k="$key" '$1 == k { print substr($0, index($0, $2)) }' "$env_file" | tail -n1
}

startup_db_set_env_value() {
  local env_file="$1"
  local key="$2"
  local value="$3"
  local tmp_file

  tmp_file="$(mktemp "${TMPDIR:-/tmp}/startup-db.XXXXXX")"
  awk -v key="$key" -v value="$value" '
    BEGIN { updated = 0 }
    index($0, key "=") == 1 {
      print key "=" value
      updated = 1
      next
    }
    { print }
    END {
      if (!updated) {
        print key "=" value
      }
    }
  ' "$env_file" > "$tmp_file"
  mv "$tmp_file" "$env_file"
}

startup_db_is_port_busy() {
  python3 - "$1" <<'PY'
import socket
import sys

port = int(sys.argv[1])
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
try:
    sock.bind(("127.0.0.1", port))
except OSError:
    sys.exit(0)
else:
    sys.exit(1)
finally:
    sock.close()
PY
}

startup_db_pick_next_open_port() {
  local start="$1"
  local candidate

  for candidate in $(seq "$start" $((start + 40))); do
    if ! startup_db_is_port_busy "$candidate"; then
      echo "$candidate"
      return 0
    fi
  done
  return 1
}

startup_db_build_database_url() {
  python3 - "$1" "$2" "$3" "$4" "$5" <<'PY'
from urllib.parse import quote
import sys

user = quote(sys.argv[1], safe='')
password = quote(sys.argv[2], safe='')
host = sys.argv[3]
port = sys.argv[4]
database = quote(sys.argv[5], safe='')
print(f"postgresql+psycopg://{user}:{password}@{host}:{port}/{database}")
PY
}

startup_db_apply_env_defaults() {
  local env_file="$1"
  local postgres_port="$2"
  local database_name database_user database_password database_host database_url volume_name

  database_name="$(startup_db_env_value "$env_file" DATABASE_NAME)"
  database_name="${database_name:-$(startup_db_env_value "$env_file" POSTGRES_DB)}"
  database_name="${database_name:-iz_clinical_notes_analyzer}"

  database_user="$(startup_db_env_value "$env_file" DATABASE_USER)"
  database_user="${database_user:-$(startup_db_env_value "$env_file" POSTGRES_USER)}"
  database_user="${database_user:-iz_clinical_notes_app}"

  database_password="$(startup_db_env_value "$env_file" DATABASE_PASSWORD)"
  database_password="${database_password:-$(startup_db_env_value "$env_file" POSTGRES_PASSWORD)}"
  database_password="${database_password:-change-me-app}"

  database_host="$(startup_db_env_value "$env_file" DATABASE_HOST)"
  database_host="${database_host:-127.0.0.1}"

  volume_name="$(startup_db_env_value "$env_file" POSTGRES_VOLUME_NAME)"
  volume_name="${volume_name:-iz_clinical_notes_analyzer_postgres_data}"

  database_url="$(startup_db_build_database_url "$database_user" "$database_password" "$database_host" "$postgres_port" "$database_name")"

  startup_db_set_env_value "$env_file" POSTGRES_PORT "$postgres_port"
  startup_db_set_env_value "$env_file" POSTGRES_VOLUME_NAME "$volume_name"
  startup_db_set_env_value "$env_file" DATABASE_HOST "$database_host"
  startup_db_set_env_value "$env_file" DATABASE_PORT "$postgres_port"
  startup_db_set_env_value "$env_file" DATABASE_NAME "$database_name"
  startup_db_set_env_value "$env_file" DATABASE_USER "$database_user"
  startup_db_set_env_value "$env_file" DATABASE_PASSWORD "$database_password"
  startup_db_set_env_value "$env_file" POSTGRES_SERVICE_HOST "postgres"
  startup_db_set_env_value "$env_file" DATABASE_URL "$database_url"

  # Keep legacy variable names aligned for older local tooling.
  startup_db_set_env_value "$env_file" POSTGRES_DB "$database_name"
  startup_db_set_env_value "$env_file" POSTGRES_USER "$database_user"
  startup_db_set_env_value "$env_file" POSTGRES_PASSWORD "$database_password"
}

startup_db_compose() {
  local root_dir="$1"
  shift
  (
    cd "$root_dir"
    docker compose "$@"
  )
}

startup_db_wait_for_postgres() {
  local root_dir="$1"
  local database_user="$2"
  local database_password="$3"
  local ready_attempts="${POSTGRES_READY_ATTEMPTS:-40}"
  local ready_sleep="${POSTGRES_READY_SLEEP_SECONDS:-2}"
  local attempt

  for attempt in $(seq 1 "$ready_attempts"); do
    if startup_db_compose "$root_dir" exec -T -e PGPASSWORD="$database_password" postgres \
      psql -U "$database_user" -d postgres -v ON_ERROR_STOP=1 -c 'SELECT 1' >/dev/null 2>&1; then
      startup_db_pass "Dedicated PostgreSQL is reachable (attempt ${attempt}/${ready_attempts})."
      return 0
    fi
    sleep "$ready_sleep"
  done

  startup_db_warn 'Dedicated PostgreSQL did not become ready in time.'
  startup_db_compose "$root_dir" logs --tail=200 postgres || true
  return 1
}

startup_db_ensure_database() {
  local root_dir="$1"
  local database_name="$2"
  local database_user="$3"
  local database_password="$4"
  local bootstrap_sql schema_sql

  bootstrap_sql="$(cat <<'SQL'
SELECT format('CREATE DATABASE %I OWNER %I', :'app_db_name', :'app_db_user')
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = :'app_db_name') \gexec
SELECT format('ALTER DATABASE %I OWNER TO %I', :'app_db_name', :'app_db_user') \gexec
SQL
)"

  printf '%s\n' "$bootstrap_sql" | startup_db_compose "$root_dir" exec -T -e PGPASSWORD="$database_password" postgres \
    psql -U "$database_user" -d postgres -v ON_ERROR_STOP=1 \
    -v app_db_name="$database_name" \
    -v app_db_user="$database_user" >/dev/null

  schema_sql="$(cat <<'SQL'
SELECT format('ALTER SCHEMA public OWNER TO %I', :'app_db_user') \gexec
SELECT format('GRANT ALL ON SCHEMA public TO %I', :'app_db_user') \gexec
SELECT format('ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO %I', :'app_db_user') \gexec
SELECT format('ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO %I', :'app_db_user') \gexec
SQL
)"

  printf '%s\n' "$schema_sql" | startup_db_compose "$root_dir" exec -T -e PGPASSWORD="$database_password" postgres \
    psql -U "$database_user" -d "$database_name" -v ON_ERROR_STOP=1 \
    -v app_db_user="$database_user" >/dev/null
}

startup_db_bootstrap() {
  local root_dir="$1"
  local env_file="$2"
  local database_name database_user database_password

  database_name="$(startup_db_env_value "$env_file" DATABASE_NAME)"
  database_user="$(startup_db_env_value "$env_file" DATABASE_USER)"
  database_password="$(startup_db_env_value "$env_file" DATABASE_PASSWORD)"

  startup_db_info 'Ensuring dedicated PostgreSQL service is running.'
  startup_db_compose "$root_dir" up -d postgres
  startup_db_wait_for_postgres "$root_dir" "$database_user" "$database_password"
  startup_db_info "Ensuring database \"${database_name}\" exists for user \"${database_user}\"."
  startup_db_ensure_database "$root_dir" "$database_name" "$database_user" "$database_password"
  startup_db_pass "Dedicated PostgreSQL database \"${database_name}\" is ready."
}
