from __future__ import annotations

"""SMART-on-FHIR/FHIR R4 connector boundary.

The app can safely run without live EMR credentials today. This module defines
the standards-aligned profile, discovery check, and import plan that will become
the live importer once the client provides vendor registration details.
"""

from collections.abc import Mapping
from urllib.parse import quote, urljoin, urlparse

import httpx
from fastapi import HTTPException

from app.models.models import AllevaBucket, AppSetting, DocumentCompletionStatus

FHIR_STANDARDS = [
    'HL7 FHIR R4 Patient',
    'HL7 FHIR R4 DocumentReference',
    'HL7 FHIR R4 Binary',
    'HL7 FHIR R4 Provenance',
    'SMART App Launch OAuth2 discovery',
]
SUPPORTED_RESOURCES = ['Patient', 'DocumentReference', 'Binary', 'Provenance']
ALLEVA_ADAPTER_KEY = 'alleva-smart-fhir-document-manager'
ALLEVA_SUPPORTED_EXPORT_FORMATS = ['PDF', 'DOCX', 'TXT', 'CSV', 'RTF', 'JPG', 'PNG', 'ZIP']
ALLEVA_REQUIRED_VENDOR_INPUTS = [
    'Alleva-approved API or SMART-on-FHIR app registration',
    'FHIR base URL or Alleva API base URL for the client environment',
    'Client ID and secret or other Alleva-approved authentication details',
    'Confirmed read scopes for Patient, DocumentReference, Binary, and optional Provenance',
    'Vendor confirmation for attachment URL behavior, pagination, rate limits, and sandbox test patients',
]
ALLEVA_DOCUMENT_MANAGER_SECTIONS = [
    {
        'key': AllevaBucket.custom_forms.value,
        'label': 'Custom Forms',
        'source_description': 'Client-specific forms that can be filled, signed, completed, canceled, and viewed in Alleva Document Manager.',
    },
    {
        'key': AllevaBucket.uploaded_documents.value,
        'label': 'Uploaded Documents',
        'source_description': 'Client-specific documents uploaded into Alleva that are not native Alleva forms.',
    },
    {
        'key': AllevaBucket.portal_documents.value,
        'label': 'Portal Documents',
        'source_description': 'Forms completed through the Alleva Client/Family Portal and stored in the client chart.',
    },
    {
        'key': AllevaBucket.labs.value,
        'label': 'Labs',
        'source_description': 'Lab orders, requisitions, and results when the client environment has a lab integration.',
    },
    {
        'key': AllevaBucket.medications.value,
        'label': 'Medications',
        'source_description': 'Medication-management or ePrescribe documents when exported or exposed by the client environment.',
    },
    {
        'key': AllevaBucket.notes.value,
        'label': 'Notes',
        'source_description': 'Progress notes, clinical notes, and session documentation exported from the chart.',
    },
    {
        'key': AllevaBucket.other.value,
        'label': 'Other',
        'source_description': 'Other Alleva chart material approved by the client for review import.',
    },
]


def normalize_fhir_base_url(raw_url: str) -> str:
    """Validate and normalize the configured FHIR base URL."""
    parsed = urlparse(raw_url.strip())
    if parsed.scheme not in {'http', 'https'} or not parsed.netloc:
        raise HTTPException(status_code=400, detail='FHIR base URL must be an http(s) URL')
    return raw_url.strip().rstrip('/')


def smart_configuration_url(fhir_base_url: str) -> str:
    """Return the SMART discovery document URL for a FHIR base URL."""
    return urljoin(f'{normalize_fhir_base_url(fhir_base_url)}/', '.well-known/smart-configuration')


def emr_connection_profile(settings_row: AppSetting) -> dict[str, object]:
    """Build the non-secret EMR connector profile shown to admins."""
    base_url = settings_row.emr_fhir_base_url.strip()
    scopes = [scope for scope in settings_row.emr_smart_scopes.split() if scope]
    return {
        'adapter_key': ALLEVA_ADAPTER_KEY,
        'enabled': settings_row.emr_api_enabled,
        'vendor_name': settings_row.emr_vendor_name,
        'live_import_status': 'configured' if settings_row.emr_api_enabled and base_url else 'gated_until_vendor_registration',
        'fhir_base_url': base_url,
        'smart_discovery_url': smart_configuration_url(base_url) if base_url else None,
        'client_id_configured': bool(settings_row.emr_smart_client_id.strip()),
        'client_secret_configured': bool(settings_row.emr_smart_client_secret.strip()),
        'scopes': scopes,
        'supported_resources': SUPPORTED_RESOURCES,
        'standards': FHIR_STANDARDS,
        'supported_export_formats': ALLEVA_SUPPORTED_EXPORT_FORMATS,
        'document_manager_sections': ALLEVA_DOCUMENT_MANAGER_SECTIONS,
        'required_vendor_inputs': ALLEVA_REQUIRED_VENDOR_INPUTS,
    }


def discover_smart_configuration(fhir_base_url: str, *, timeout_seconds: int = 10) -> dict[str, object]:
    """Fetch SMART discovery metadata from an EMR FHIR endpoint."""
    base_url = normalize_fhir_base_url(fhir_base_url)
    discovery_url = smart_configuration_url(base_url)
    try:
        with httpx.Client(timeout=timeout_seconds, follow_redirects=False) as client:
            response = client.get(discovery_url, headers={'Accept': 'application/json'})
            response.raise_for_status()
            payload = response.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f'SMART discovery failed: {exc}') from exc

    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail='SMART discovery did not return a JSON object')

    capabilities = payload.get('capabilities') if isinstance(payload.get('capabilities'), list) else []
    return {
        'status': 'ok',
        'fhir_base_url': base_url,
        'smart_configuration_url': discovery_url,
        'authorization_endpoint_configured': bool(payload.get('authorization_endpoint')),
        'token_endpoint_configured': bool(payload.get('token_endpoint')),
        'capabilities': [str(item) for item in capabilities],
        'message': 'SMART configuration was discovered. Register this local app with the EMR before enabling live import.',
    }


def build_document_reference_import_plan(patient_id: str, fhir_base_url: str) -> dict[str, object]:
    """Describe the FHIR requests needed to import a patient's documents."""
    base_url = normalize_fhir_base_url(fhir_base_url)
    encoded_patient_id = quote(patient_id.strip(), safe='')
    if not encoded_patient_id:
        raise HTTPException(status_code=400, detail='Patient ID is required for the EMR import plan')

    # The local patient_id is treated as a source identifier/MRN until a FHIR Patient.id is resolved.
    planned_requests = [
        {
            'step': '1',
            'purpose': 'Resolve the EMR Patient resource for this local patient ID or MRN.',
            'method': 'GET',
            'url': f'{base_url}/Patient?identifier={encoded_patient_id}',
        },
        {
            'step': '2',
            'purpose': 'List Alleva chart documents for the resolved Patient, including Document Manager forms, uploaded documents, portal documents, notes, and supported clinical attachments.',
            'method': 'GET',
            'url': f'{base_url}/DocumentReference?patient={{FHIR_PATIENT_ID}}&_sort=-date',
        },
        {
            'step': '3',
            'purpose': 'Fetch each DocumentReference content attachment. Attachment URLs may be FHIR Binary URLs or Alleva/vendor document endpoints, depending on the registered interface.',
            'method': 'GET',
            'url': '{DocumentReference.content.attachment.url}',
        },
        {
            'step': '4',
            'purpose': 'Optionally retrieve Provenance for audit traceability when the EMR supports it.',
            'method': 'GET',
            'url': f'{base_url}/Provenance?target=DocumentReference/{{DOCUMENT_REFERENCE_ID}}',
        },
    ]
    return {
        'patient_id': patient_id.strip(),
        'fhir_base_url': base_url,
        'source_identifier_note': 'Treat the local patient_id as an identifier/MRN until the EMR returns a FHIR Patient.id.',
        'planned_requests': planned_requests,
        'alleva_notes': [
            'Use Alleva Document Manager exports as the production path until Alleva/client registration details are available.',
            'Live import is read-only and should not write back to Alleva without a separate signed vendor/client scope.',
            'Map Alleva Document Manager sections to the app alleva_bucket field so reviewers can filter source material by Custom Forms, Uploaded Documents, Portal Documents, Labs, Medications, Notes, or Other.',
        ],
        'supported_export_formats': ALLEVA_SUPPORTED_EXPORT_FORMATS,
        'document_manager_sections': ALLEVA_DOCUMENT_MANAGER_SECTIONS,
        'attachment_handling': 'Prefer DocumentReference.content.attachment.url. If the URL is a FHIR Binary resource, fetch Binary.contentType and Binary.data; otherwise follow the Alleva-approved vendor attachment URL contract.',
        'document_mapping': {
            'PatientNoteSet.patient_id': 'Patient.identifier.value or locally entered patient ID',
            'PatientNoteDocument.alleva_bucket': 'Alleva Document Manager section or classified DocumentReference category/type',
            'PatientNoteDocument.document_label': 'DocumentReference.description or content.attachment.title',
            'PatientNoteDocument.content_type': 'DocumentReference.content.attachment.contentType or Binary.contentType',
            'PatientNoteDocument.document_date': 'DocumentReference.date or context.period',
            'PatientNoteDocument.sha256': 'Local SHA-256 of fetched document bytes after import',
        },
    }


def _coding_text(value: object) -> str:
    if not isinstance(value, Mapping):
        return ''
    coding = value.get('coding')
    if isinstance(coding, list):
        labels = [str(item.get('display') or item.get('code') or '') for item in coding if isinstance(item, Mapping)]
        if any(labels):
            return ' '.join(label for label in labels if label)
    return str(value.get('text') or '')


def _first_text(*values: object) -> str:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ''


def _date_part(value: object) -> str:
    if not isinstance(value, str):
        return ''
    return value[:10] if len(value) >= 10 else value


def classify_alleva_document_reference(document_reference: Mapping[str, object]) -> str:
    """Classify a FHIR DocumentReference into the closest Alleva document bucket."""
    searchable_values = [
        document_reference.get('description'),
        document_reference.get('status'),
        document_reference.get('docStatus'),
        _coding_text(document_reference.get('type')),
    ]
    categories = document_reference.get('category')
    if isinstance(categories, list):
        searchable_values.extend(_coding_text(category) for category in categories)
    content = document_reference.get('content')
    if isinstance(content, list):
        for item in content:
            if isinstance(item, Mapping):
                attachment = item.get('attachment')
                if isinstance(attachment, Mapping):
                    searchable_values.extend([attachment.get('title'), attachment.get('contentType')])

    haystack = ' '.join(str(value or '') for value in searchable_values).lower()
    if 'portal' in haystack:
        return AllevaBucket.portal_documents.value
    if 'lab' in haystack or 'result' in haystack or 'requisition' in haystack:
        return AllevaBucket.labs.value
    if 'medication' in haystack or 'eprescribe' in haystack or 'prescription' in haystack:
        return AllevaBucket.medications.value
    if 'progress note' in haystack or 'clinical note' in haystack or 'session note' in haystack:
        return AllevaBucket.notes.value
    if 'form' in haystack or 'consent' in haystack or 'rights' in haystack or 'intake' in haystack:
        return AllevaBucket.custom_forms.value
    if 'upload' in haystack or 'scan' in haystack or 'pdf' in haystack or 'word' in haystack:
        return AllevaBucket.uploaded_documents.value
    return AllevaBucket.uploaded_documents.value


def map_document_reference_to_patient_note_metadata(document_reference: Mapping[str, object]) -> dict[str, object]:
    """Map a FHIR DocumentReference into the app's Alleva upload metadata shape."""
    if document_reference.get('resourceType') != 'DocumentReference':
        raise HTTPException(status_code=400, detail='Expected a FHIR DocumentReference resource')
    content = document_reference.get('content')
    first_content = content[0] if isinstance(content, list) and content else {}
    attachment = first_content.get('attachment') if isinstance(first_content, Mapping) else {}
    if not isinstance(attachment, Mapping):
        raise HTTPException(status_code=400, detail='DocumentReference content attachment is required')

    type_text = _coding_text(document_reference.get('type'))
    label = _first_text(
        attachment.get('title'),
        document_reference.get('description'),
        type_text,
        f"DocumentReference {document_reference.get('id') or 'document'}",
    )
    period = document_reference.get('context')
    period_start = ''
    if isinstance(period, Mapping) and isinstance(period.get('period'), Mapping):
        period_start = _date_part(period['period'].get('start'))

    return {
        'client_file_name': label,
        'document_label': label,
        'alleva_bucket': classify_alleva_document_reference(document_reference),
        'document_type': type_text or 'clinical_document',
        'completion_status': DocumentCompletionStatus.completed.value,
        'client_signed': False,
        'staff_signed': False,
        'document_date': _first_text(_date_part(document_reference.get('date')), period_start, _date_part(attachment.get('creation'))),
        'description': _first_text(document_reference.get('description'), type_text, label),
        'content_type': _first_text(attachment.get('contentType'), 'application/octet-stream'),
        'source_attachment_url': _first_text(attachment.get('url')),
        'source_document_reference_id': _first_text(document_reference.get('id')),
    }
