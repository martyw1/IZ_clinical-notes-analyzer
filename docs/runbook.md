# Operations Runbook

## Health endpoints
- Backend direct: `GET /health`
- Backend API alias: `GET /api/health`
- Through frontend proxy: `GET /api/health`

## Dedicated PostgreSQL runtime
- The app always runs against its own Docker-managed `postgres` service.
- Host-local backend runs connect through `DATABASE_HOST=127.0.0.1` and `DATABASE_PORT=$POSTGRES_PORT`.
- Backend containers automatically rewrite host-local Postgres URLs to the Compose `postgres` service.
- `scripts/startup-ubuntu-24.04.sh` and `scripts/startup-macos.sh` bring up the dedicated Postgres service first and create the application database if it is missing.

## Recovery
- If startup fails with a DB password mismatch after a previous initialization, restore the original `DATABASE_USER`/`DATABASE_PASSWORD` values in `.env`.
- On Ubuntu, `RESET_DEDICATED_DB_VOLUME_ON_AUTH_FAILURE=1 ./scripts/startup-ubuntu-24.04.sh` will recreate the dedicated Postgres volume. This is destructive.

## Backup/restore
Use the app DB name consistently:
- Backup: `pg_dump -Fc iz_clinical_notes_analyzer > backup.dump`
- Restore: `pg_restore -d iz_clinical_notes_analyzer backup.dump`
