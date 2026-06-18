# EMR Integration Readiness

This app is business-ready for local Alleva EMR-export uploads today. Live EMR API import is intentionally behind a connector boundary until the client and Alleva provide registration details, approved scopes, credentials, endpoint mapping, pagination behavior, and attachment/signature behavior.

## Current Supported Path

1. Export PDF, DOCX, TXT, CSV, RTF, image, or ZIP documents from the EMR.
2. Upload the binder in the app under the patient ID or let the app detect the patient ID from readable file content.
3. The app encrypts source files at rest, records a SHA-256 digest, creates an immutable binder version, and generates the review chart.

Alleva-specific local import support is centered on the public Document Manager shape:

- Custom Forms: client-specific forms that can be filled, signed, completed, canceled, and viewed.
- Uploaded Documents: stored client documents that are not native Alleva forms.
- Portal Documents: forms completed through the Client/Family Portal and opened from the client chart.
- Labs, medications, and clinical notes are supported as source buckets when exported or exposed by the client environment.

The app now preserves source traceability fields for future export-package and live-FHIR import work: source export ID, FHIR Patient resource ID, DocumentReference ID, attachment URL, author, custodian, security label, and Provenance ID.

## SMART/FHIR Boundary

The app is stubbed around these primary standards and vendor patterns:

- SMART App Launch: app registration, `.well-known/smart-configuration`, OAuth authorization/token endpoints, launch context, and scopes.
- FHIR R4 `Patient`: resolve the EMR patient resource from a local identifier or MRN.
- FHIR R4 `DocumentReference`: list clinical notes, scanned paper, PDFs, Word documents, and related document metadata. The app maps these records into Alleva bucket metadata before import.
- FHIR R4 `Binary`: fetch document bytes when a `DocumentReference.content.attachment.url` points to a Binary or vendor document endpoint; verify local SHA-256 after fetch.
- Optional FHIR `Provenance`: capture source traceability when the EMR supports it.

## Implemented Stub Endpoints

- `GET /api/emr/profile`: shows the configured vendor label, FHIR base URL, SMART client metadata state, scopes, supported resources, and standards.
- `POST /api/emr/discover`: checks SMART discovery for a configured or submitted FHIR base URL.
- `GET /api/emr/import-plan?patient_id=...`: returns the planned `Patient`, `DocumentReference`, `Binary`, and `Provenance` request flow for a patient.

## Required Before Live API Import

- EMR vendor name and production/sandbox FHIR base URL.
- SMART registration approval, redirect URLs, client ID, and client secret or private-key auth details.
- Confirmed scopes for `Patient`, `DocumentReference`, `Binary`, and any required launch context.
- Vendor-specific pagination, retry, rate-limit, attachment URL, and Binary content behavior.
- Confirmation whether the Alleva tenant exposes SMART/FHIR, Alleva open API endpoints, HL7 feeds, SFTP exports, or a vendor-managed connector for Document Manager content.
- Written client approval for any external PHI movement, including optional LLM analysis.

The FHIR base URL must be a vendor/tenant-supplied root FHIR R4 endpoint, for example an endpoint ending in `/fhir/R4`. The public Alleva Swagger UI (`https://api.allevasoft.com/swagger/index.html`) and OpenAPI JSON (`https://api.allevasoft.com/swagger/v1/swagger.json` or `/swagger/v2/swagger.json`) are REST API documentation/definition URLs and belong in the OpenAPI/API harness fields. `https://api.allevasoft.com/advanced-form-elements` is a protected REST operation path and is not a FHIR base URL.

## Alleva REST Treatment-Plan Sync Boundary

Version `1.4.1` adds a separate Alleva REST treatment-plan sync path for the workflow R3 actually wants: Alleva supplies active-client and treatment-plan source data, then the IZ Clinical Notes Analyzer runs R3's deterministic timeliness/compliance logic locally.

This path does not require a FHIR base URL. It uses the Alleva REST API base URL and OpenAPI definition, with startup sync disabled by default. Startup/manual sync requires explicit R3/Alleva approval plus validated endpoint mapping for:

- active clients and discharged/inactive filtering
- treatment-plan records
- treatment-review records
- staff/creator signature date
- client signature date
- current level of care and admission date
- next review due date
- pagination/cursor/date range behavior

The current implementation can normalize approved REST payloads into `TreatmentPlanClient`, `LevelOfCareHistory`, and `TreatmentPlanRecord` rows and then immediately run the local R3 timeliness evaluator. If mapping or approval is missing, the app records a blocked sync status instead of importing live patient data.

## Current Alleva Boundary

Alleva publicly describes open/custom integrations and modern FHIR/HL7 integration patterns, but detailed tenant API specifications are not published in the open support material found during this review. The code therefore supports:

- Local Alleva export/import now.
- Read-only SMART/FHIR `Patient` + `DocumentReference` + `Binary` + optional `Provenance` planning now.
- Direct OpenAPI/Swagger discovery and bounded operation testing against approved non-PHI operations now.
- Gated Alleva REST treatment-plan sync only after vendor/client registration details, endpoint mapping, and approval are supplied.

The app must not be configured for write-back into Alleva until a separate signed scope, data-ownership rule, and validation plan exist.

## Primary References

- HL7 FHIR R4 DocumentReference: https://www.hl7.org/fhir/R4/documentreference.html
- HL7 FHIR R4 Binary: https://www.hl7.org/fhir/R4/binary.html
- SMART App Launch authorization and discovery: https://build.fhir.org/ig/HL7/smart-app-launch/app-launch.html
- SMART scopes and launch context: https://build.fhir.org/ig/HL7/smart-app-launch/scopes-and-launch-context.html
- Alleva Document Manager overview: https://support.helloalleva.com/document-manager
- Epic FHIR guidance: https://fhir.epic.com/Documentation?docId=developerguidelines&section=fn-g9
- Oracle Health Millennium DocumentReference: https://docs.oracle.com/en/industries/health/millennium-platform-apis/mfrap/op-documentreference-get.html
- Alleva integration overview: https://helloalleva.com/2026/04/21/ehr-integration/
