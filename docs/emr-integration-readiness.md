# Alleva REST / OpenAPI / HL7 Readiness

Date: 2026-06-19

Applies to: IZ Clinical Notes Analyzer Beta Version `1.4.5-beta.1` local Windows desktop runtime.

## Current vendor boundary

Alleva confirmed: "Unfortunately, we dont have any support for FHIR. Just HL7 at the moment."

The active app therefore treats Alleva integration as REST/OpenAPI/HL7-readiness only. FHIR/SMART-on-FHIR configuration, discovery, read scopes, import-plan generation, and validation requirements have been removed from active Alleva workflows. No FHIR endpoint is required for Alleva API readiness checks or Alleva REST treatment-plan sync.

## Active app behavior

- App settings collect the one active Alleva/API connection: Alleva REST API base URL, Alleva OpenAPI URL, OAuth token URL, API client ID, encrypted API client secret, token auth style, timeout, periodic-check interval, and gated treatment-plan sync controls.
- Stored API endpoint profiles are optional presets that save REST/OpenAPI endpoint options and encrypted client-secret state without returning secrets to the browser. Activating a profile copies it into the active connection.
- The direct API harness discovers Swagger/OpenAPI definitions and tests selected operations using API-key, no-auth, or OAuth client-credentials modes.
- Pasting the R3/Alleva client ID and client secret is expected for OAuth client credentials. The saved secret remains encrypted locally and write-only after save.
- Periodic API checks authenticate, pull/summarize OpenAPI definitions, and do not import live patient records.
- Alleva REST treatment-plan sync remains disabled by default and cannot run until R3/Alleva approval and endpoint mapping validation are recorded.

## Removed active workflows

The active app no longer exposes:

- FHIR base URL fields.
- SMART-on-FHIR discovery.
- SMART/FHIR read scopes.
- FHIR import-plan routes or UI.
- Patient document planning through FHIR resources.
- FHIR AuditEvent payloads in forensic log responses.

## Live sync gate

Before any live Alleva REST treatment-plan sync can be enabled, R3 must confirm:

- Official tenant credentials and approved auth style.
- Active-client, treatment-plan, treatment-review, pagination, status, date, and signature endpoint mapping.
- Rate limits, retry rules, filtering behavior, and production/sandbox boundaries.
- Attachment behavior if document material is later approved for import.
- Compliance approval for live patient data import.

Until that gate is complete, the app remains local-first and upload-first. Readiness checks and operation tests are safe configuration workflows only.
