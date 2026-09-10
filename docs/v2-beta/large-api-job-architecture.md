# Large API Job Architecture

> Release reference: the current app is `2.0.0-beta.3` / build `2026.09.03.1` (`beta-local-desktop-v2`). See the [current documentation index](../current-documentation-state.md).

Large Alleva pulls use backend jobs instead of long browser requests.

`POST /api/v2/api-harness/jobs` returns a `job_id` immediately. The job writes incrementally under `%LOCALAPPDATA%\IZ Clinical Notes Analyzer\api-harness-runs\<job_id>`.

Required artifacts include run summary, progress JSON, redacted JSONL, flattened TSV/CSV, observed schema JSON, field frequency TSV, warning log, error log, and audit summary. Raw sensitive artifacts are off by default.

Browser endpoints expose compact job state, artifact metadata, and bounded previews only.
