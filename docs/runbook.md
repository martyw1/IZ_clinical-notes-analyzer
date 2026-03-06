# Operations Runbook

## Health endpoints
- Backend direct: `GET /health`
- Backend API alias: `GET /api/health`
- Through frontend proxy: `GET /api/health`

## Database modes
- `USE_INTERNAL_POSTGRES=1` + `DATABASE_HOST_MODE=internal`: run app with internal Docker Postgres (`db` service profile `internal-db`).
- `USE_INTERNAL_POSTGRES=0` + `DATABASE_HOST_MODE=host`: app container connects to PostgreSQL on Docker host via `host.docker.internal`.
- `USE_INTERNAL_POSTGRES=0` + `DATABASE_HOST_MODE=external`: app container uses explicit remote DB host from `DATABASE_URL` without rewrite.

## Backup/restore
Use the app DB name consistently:
- Backup: `pg_dump -Fc iz_clinical_notes_analyzer > backup.dump`
- Restore: `pg_restore -d iz_clinical_notes_analyzer backup.dump`
