# Large API Job Architecture

Large Alleva pulls use backend jobs instead of long browser requests.

`POST /api/v2/api-harness/jobs` returns a `job_id` immediately. The job writes incrementally under `%LOCALAPPDATA%\IZ Clinical Notes Analyzer\api-harness-runs\<job_id>`.

Required artifacts include run summary, progress JSON, redacted JSONL, flattened TSV/CSV, observed schema JSON, field frequency TSV, warning log, error log, and audit summary. Raw sensitive artifacts are off by default.

Browser endpoints expose compact job state, artifact metadata, and bounded previews only.
