# Full Treatment-Plan Content Model

> Release reference: the current app is `2.0.0-beta.3` / build `2026.09.03.1` (`beta-local-desktop-v2`). See the [current documentation index](../current-documentation-state.md).

V2 models treatment-plan content as a normalized snapshot with plan ID, patient ID, source mode, source paths, reason for admission, initial client needs, family education needs, problems, diagnoses, behavioral definitions, goals, objectives, interventions, signature metadata, observed fields, evidence refs, content quality warnings, redaction status, and content hash.

The UI renders this through the selected-client detail viewer. It does not dump giant JSON into the page.
