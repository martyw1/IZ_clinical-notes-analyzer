# Large API Job Architecture

> Current source: `1.0.1` / build `2026.10.12.1` (`stable-local-desktop`); V2 is the internal architecture name. Dated beta results retain their original scope. See the [current documentation index](../current-documentation-state.md).

Large Alleva pulls use backend jobs instead of long browser requests.

`POST /api/v2/api-harness/jobs` returns a `job_id` immediately. The job writes incrementally under `%LOCALAPPDATA%\IZ Clinical Notes Analyzer\api-harness-runs\<job_id>`.

Required artifacts include run summary, progress JSON, redacted JSONL, flattened TSV/CSV, observed schema JSON, field frequency TSV, warning log, error log, and audit summary. Raw sensitive artifacts are off by default.

Browser endpoints expose compact job state, artifact metadata, and bounded previews only.


October 12 current boundary: [operator help](../operator-help-current.md), [rules contract](rules-contract.md), [runbook](../runbook.md) and [current validation](../validation/current-work-2026-10-12.md) govern current instructions. Clinical intervals are read-only in Settings; LOC timing remains unvalidated. Live Alleva use requires explicit external approval. Historical beta results do not qualify a new package.
