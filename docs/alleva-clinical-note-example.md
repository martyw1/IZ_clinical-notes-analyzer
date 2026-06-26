# Example clinical-note intake bundle for Alleva-style downloads

This is a synthetic example for development and testing only. It is based on the app's existing upload model, the R3 Recovery Services workflow discussion, and screenshots showing an Alleva-style **Document Manager** with tabs such as **Custom Forms**, **Uploaded Documents**, and **Portal Documents**. It is not official Alleva documentation and must not be treated as a confirmed vendor API contract.

## Intended app behavior

The app should support two equal intake paths:

1. **Manual upload**: a staff member downloads or exports clinical notes/documents from Alleva, then uploads them into this app for a patient.
2. **Direct API access**: an administrator configures API access, then an approved workflow searches by patient ID only, pulls available notes/documents, stores them as a patient note set, and runs the same completeness checks.

Both intake paths should land in the same internal structure:

```text
Patient Note Set
  Patient identity/context
  Source system metadata
  One or more clinical-note/document records
  Extracted text when available
  Source document IDs/references when available
  Completeness-check results
  Manager review state
```

## Alleva-style source buckets observed or expected

| Source bucket | Example use in this app | Example files/documents |
| --- | --- | --- |
| `custom_forms` | Treatment-plan and assessment forms completed inside the EMR | Intake Packet, Safety Plan, ASAM Placement, Notification of Discharge, GAD-7, PHQ-9, BARC-10 |
| `uploaded_documents` | Files uploaded into the EMR by staff | external PDFs, signed forms, outside records, scanned paperwork |
| `portal_documents` | Documents shared through or received from the portal | portal forms, signed patient-facing documents |
| `notes` | Progress notes and clinical narrative records | individual note, group note, case-management note, treatment-plan review note |
| `labs` | Lab results | UDS lab results, medication/lab reports |
| `medications` | Medication records | MAR, medication list, medication reconciliation |
| `other` | Anything that does not fit cleanly | miscellaneous chart artifacts |

## Example patient-note set metadata

```json
{
  "patient_id": "ALV-100245",
  "source_system": "Alleva",
  "source_export_id": "manual-export-2026-05-14-001",
  "source_patient_resource_id": "patient/ALV-100245",
  "upload_mode": "initial",
  "level_of_care": "IOP",
  "admission_date": "2026-04-15",
  "discharge_date": "",
  "primary_clinician": "M. Johnson, MS, LPC",
  "upload_notes": "Synthetic development bundle based on Document Manager custom forms, uploaded documents, portal documents, and notes."
}
```

## Example file manifest for manual upload

The browser-side upload workflow can send a manifest like this alongside the uploaded files.

```json
[
  {
    "client_file_name": "document-1.pdf",
    "document_label": "Document 1",
    "alleva_bucket": "custom_forms",
    "document_type": "intake_packet",
    "completion_status": "completed",
    "client_signed": true,
    "staff_signed": true,
    "document_date": "2026-04-15",
    "description": "Admission intake packet and baseline consent forms.",
    "source_document_id": "cf-100245-0001",
    "source_author": "",
    "source_custodian": "",
    "source_security_label": "clinical"
  },
  {
    "client_file_name": "document-2.pdf",
    "document_label": "Document 2",
    "alleva_bucket": "custom_forms",
    "document_type": "safety_plan",
    "completion_status": "completed",
    "client_signed": true,
    "staff_signed": true,
    "document_date": "2026-04-15",
    "description": "Client safety plan completed at admission.",
    "source_document_id": "cf-100245-0002",
    "source_author": "",
    "source_custodian": "",
    "source_security_label": "clinical"
  },
  {
    "client_file_name": "document-3.txt",
    "document_label": "Document 3",
    "alleva_bucket": "notes",
    "document_type": "individual_progress_note",
    "completion_status": "completed",
    "client_signed": false,
    "staff_signed": true,
    "document_date": "2026-04-22",
    "description": "Individual session progress note.",
    "source_document_id": "note-100245-0422",
    "source_author": "",
    "source_custodian": "",
    "source_security_label": "clinical"
  },
  {
    "client_file_name": "document-4.pdf",
    "document_label": "Document 4",
    "alleva_bucket": "labs",
    "document_type": "uds_lab_result",
    "completion_status": "completed",
    "client_signed": false,
    "staff_signed": false,
    "document_date": "2026-04-21",
    "description": "Urine drug screen lab result.",
    "source_document_id": "lab-100245-0421",
    "source_author": "",
    "source_custodian": "",
    "source_security_label": "clinical"
  }
]
```

## Example extracted clinical-note text

A TXT, CSV, PDF text extraction, or API payload may normalize into a text block like this for rule checks.

```text
Source System: Alleva
Source Bucket: Notes
Document Type: Individual Progress Note
Patient ID: ALV-100245
Date of Service: 2026-04-22
Level of Care: IOP
Clinician: M. Johnson, MS, LPC
Location: R3 Recovery Services
Service Type: Individual Therapy
Duration: 53 minutes
Status: Completed
Staff Signature: Signed by M. Johnson, MS, LPC on 2026-04-22 16:42
Client Signature: Not required for this note type

Presenting / Data:
Client arrived on time and participated appropriately. Client reported moderate cravings during the prior weekend after exposure to a high-risk social setting. Client denied current suicidal ideation, homicidal ideation, or intent to self-harm. Client reported using the written safety plan and contacting a sober support before cravings escalated.

Assessment:
Client remains appropriate for IOP level of care. Client demonstrates improved insight into relapse triggers and is using coping strategies with partial effectiveness. Continued monitoring of attendance, UDS results, and treatment-plan objective progress is indicated.

Intervention:
Clinician reviewed relapse-prevention plan, reinforced use of sober supports, and practiced refusal skills. Clinician reviewed treatment-plan goal TP-1: maintain abstinence and improve recovery-support engagement.

Plan:
Client will attend scheduled groups this week, complete assigned recovery-support homework, and bring an updated meeting schedule to next session. Clinician will review UDS results and update treatment-plan progress at the next treatment-plan review interval.
```

## Example CSV-style export row

Some exports may arrive as tabular data. The app should preserve the source row and normalize key fields.

```csv
patient_id,document_date,bucket,document_type,title,status,client_signed,staff_signed,source_document_id
ALV-100245,2026-04-22,notes,individual_progress_note,Document 3,completed,false,true,note-100245-0422
```

## Example REST API readiness planning output

Until the live API contract is confirmed, API lookup should produce a clear REST/OpenAPI plan rather than pretending to import data.

```json
{
  "query_mode": "patient_id",
  "patient_id": "ALV-100245",
  "planned_requests": [
    {
      "step": "resolve_client",
      "purpose": "Find the client record for the supplied ID.",
      "method": "GET",
      "url": "/clients?identifier=ALV-100245"
    },
    {
      "step": "list_documents",
      "purpose": "List clinical notes, custom forms, uploaded documents, portal documents, labs, and medication documents.",
      "method": "GET",
      "url": "/clients/ALV-100245/documents"
    },
    {
      "step": "download_attachments",
      "purpose": "Download PDF, TXT, CSV, image, or other supported attachment payloads.",
      "method": "GET",
      "url": "/documents/{document-id}/download"
    },
    {
      "step": "create_note_set",
      "purpose": "Store the downloaded documents as an encrypted patient note set and run completeness checks.",
      "method": "INTERNAL",
      "url": "/api/patient-note-sets/upload"
    }
  ]
}
```

## Completeness check focus for Treatment Plan Tracking

The first rules profile should pay special attention to whether the note set contains enough evidence for:

- admission/intake documents
- emergency contact and releases
- UDS labs
- medication list or MAR
- biopsychosocial assessment
- medical history and physical
- Columbia/SAFE-T/other suicide-risk documentation where required
- treatment plan and treatment-plan updates
- progress notes aligned to treatment-plan goals
- signatures and completion status
- discharge planning/discharge plan when applicable

## Guardrails

- Do not use real PHI in development examples.
- Do not assume Alleva endpoint names until confirmed through official vendor/client documentation or tested OpenAPI definitions.
- Keep manual upload and API lookup as separate intake methods but converge them into the same review workflow.
- Preserve source metadata so the manager can trace each completeness finding back to a source document.
