# SRE Runbook

## Health checks
- Backend: `GET /health`
- Database: `pg_isready`

## Logging
- Application-level forensic logs persisted in `audit_logs` table.
- Include actor, IP, request ID, action, status, and hash chain references.

## Backup/Restore
- Backup: `pg_dump -Fc chartreview > backup.dump`
- Restore: `pg_restore -d chartreview backup.dump`

## Incident response
1. Validate service health endpoint.
2. Review recent `audit_logs` with severity `warning/error`.
3. Roll back deployment to previous image if required.
4. File post-incident report with root cause and corrective actions.
