# Full Treatment-Plan Content Model

> Current source: `1.0.2` / build `2026.10.16.1` (`stable-local-desktop`); V2 is the internal architecture name. Dated beta results retain their original scope. See the [current documentation index](../current-documentation-state.md).

V2 models treatment-plan content as a normalized snapshot with plan ID, patient ID, source mode, source paths, reason for admission, initial client needs, family education needs, problems, diagnoses, behavioral definitions, goals, objectives, interventions, signature metadata, observed fields, evidence refs, content quality warnings, redaction status, and content hash.

The UI renders this through the selected-client detail viewer. It does not dump giant JSON into the page.


October 12 current boundary: [operator help](../operator-help-current.md), [rules contract](rules-contract.md), [runbook](../runbook.md) and [current validation](../validation/current-work-2026-10-12.md) govern current instructions. Clinical intervals are read-only in Settings; LOC timing remains unvalidated. Live Alleva use requires explicit external approval. Historical beta results do not qualify a new package.
