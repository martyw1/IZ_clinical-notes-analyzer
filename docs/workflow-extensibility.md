# Workflow Extensibility

Date: 2026-06-17

## Purpose

Workflow profiles let admins and office managers define future clinical workflows without changing deterministic Treatment Plan Timeliness code. Profiles are versioned, audited, and managed from the dedicated Workflow profiles screen.

The current workflow profile system is for metadata, steps, transition rules, export status context, and future workflow planning. It does not replace the deterministic timeliness evaluator in `backend/app/services/timeliness.py`, but timeliness audit events and CSV/JSON exports now include the active workflow definition/version/checklist context.

## Seeded Default

Fresh local databases seed one published workflow profile:

```text
treatment_plan_timeliness
```

Display name:

```text
Treatment Plan Timeliness Tracker
```

The seeded profile contains synthetic, non-PHI step labels for active client scope, Initial Treatment Plan, Master Treatment Plan, ongoing review, LOC-change review, and manual override review.

## Data Model

Workflow definitions live in:

```text
backend/app/models/models.py
```

Tables:

- `workflow_definitions`
- `workflow_definition_versions`

Version statuses:

- `draft`
- `published`
- `archived`

Each version stores:

- JSON definition snapshot
- JSON transition rules
- version notes
- creator
- published/archived metadata when applicable

## API

Admins and office managers can read workflow profiles:

```text
GET /api/workflow-definitions
GET /api/workflow-definitions/{id}
```

Admin/manager mutation routes:

```text
POST /api/workflow-definitions
PATCH /api/workflow-definitions/{id}
POST /api/workflow-definitions/{id}/versions
PATCH /api/workflow-definitions/{id}/versions/{version_id}
POST /api/workflow-definitions/{id}/versions/{version_id}/publish
POST /api/workflow-definitions/{id}/archive
DELETE /api/workflow-definitions/{id}
```

Delete is allowed only for profiles that have never been published and have draft versions only. Published or archived workflow history must be archived, not hard-deleted.

## Validation Rules

The backend rejects invalid workflow version payloads before saving.

Definition snapshot:

- must be a JSON object
- `steps`, when provided, must be a list
- each step must have a non-empty `key`
- each step must have a non-empty `label`

Transition rules:

- must be a JSON array
- each transition must be an object
- each transition must have non-empty `from` and `to`
- each transition must have `roles` as a list of role names

## Audit Behavior

Workflow profile changes write forensic audit events for:

- create
- update metadata
- create version
- update draft version
- publish version
- archive profile
- delete unused draft-only profile
- startup seeding of the default Treatment Plan Timeliness profile

Audit records include before/after state where applicable. Do not include PHI, credentials, bearer tokens, API keys, encryption keys, or uploaded note text in workflow definitions or version notes.

## App UI

The `Workflow profiles` screen is available to admins and office managers for:

- viewing active/archived profiles
- viewing published/draft/archived versions
- creating a profile with an initial draft version
- creating draft versions
- editing draft versions in place
- loading a published or archived version as a new draft template
- publishing draft versions
- archiving profiles
- deleting unused draft-only profiles

App settings remains admin-only. Workflow profile changes are intentionally separate so office managers can adjust approved checklist workflow steps and transition logic without opening API/EMR, LLM, readiness, or forensic-log settings.

## Current Limits

- Historical Treatment Plan Timeliness dashboard evaluations are calculated deterministically and are not yet persisted as immutable workflow-version-bound evaluation records.
- Workflow profiles do not run arbitrary rules by themselves.
- Structured import templates remain future work.
- Actual Windows installer/repair/uninstall packaging remains future work.
