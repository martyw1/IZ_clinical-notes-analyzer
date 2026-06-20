from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response
from pydantic import TypeAdapter, ValidationError
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_user, require_roles
from app.api.auth_user_routes import router as auth_user_router
from app.api.timeliness_routes import router as timeliness_router
from app.api.workflow_routes import router as workflow_router
from app.core.audit_template import AUDIT_TEMPLATE, AUDIT_TEMPLATE_BY_KEY, audit_sections
from app.core.config import settings
from app.db.session import get_db
from app.models.models import (
    AppSetting,
    AuditItemResponse,
    AuditLog,
    Chart,
    ComplianceStatus,
    EmrEndpointProfile,
    LevelOfCareHistory,
    NoteSetStatus,
    NoteSetUploadMode,
    PatientNoteDocument,
    PatientNoteSet,
    Role,
    TreatmentPlanClient,
    TreatmentPlanRecord,
    User,
    WorkflowState,
    WorkflowTransition,
)
from app.schemas.schemas import (
    AppSettingsOut,
    AppSettingsUpdate,
    AuditLogOut,
    AuditTemplateSectionOut,
    ChartCreate,
    ChartDetailOut,
    ChartSummaryOut,
    ChartUpdate,
    EmrConnectionProfileOut,
    EmrEndpointProfileCreate,
    EmrEndpointProfileOut,
    EmrEndpointProfileUpdate,
    PatientIdDetectionOut,
    PatientNoteDocumentUploadInput,
    PatientNoteSetDetailOut,
    PatientNoteSetSummaryOut,
    ReadinessOut,
    ReviewSourceDiscoveryOut,
    TreatmentPlanChecklistOut,
    TransitionInput,
    UiEventInput,
)
from app.services.audit import log_event
from app.services.alleva_treatment_plan_sync import run_alleva_treatment_plan_sync
from app.services.api_monitor import run_periodic_api_check
from app.services.app_settings import app_settings_public_payload, get_or_create_app_settings, touch_app_settings
from app.services.evaluation import apply_report_to_chart, generate_evaluation_report
from app.services.patient_notes import (
    display_name_for_patient_name_status,
    detect_patient_id_from_uploads,
    extract_upload_metadata_from_uploads,
    remove_stored_paths,
    resolve_storage_path,
    sanitize_filename,
    store_upload_file,
)
from app.services.runtime_checks import readiness_payload
from app.services.review_source_discovery import discovery_payload as review_source_discovery_payload
from app.services.secure_storage import encrypt_text_secret, read_secure_file
from app.services.treatment_plan_checklist import load_treatment_plan_checklist
from app.services.timezone import format_local_timestamp, localize_datetime, normalize_timezone_name
from app.services.timeliness import (
    get_client as get_timeliness_client,
    sync_from_note_set,
)

router = APIRouter(prefix='/api')
router.include_router(auth_user_router)
router.include_router(timeliness_router)
router.include_router(workflow_router)
NOTE_SET_ROLES = (Role.admin, Role.counselor, Role.manager)
REVIEW_ROLES = (Role.admin, Role.manager)
DEFAULT_ALLEVA_API_BASE_URL = 'https://api.allevasoft.com'
DEFAULT_ALLEVA_OPENAPI_URL = 'https://api.allevasoft.com/swagger/v1/swagger.json'
DEFAULT_ALLEVA_TOKEN_URL = 'https://authorization.allevasoft.com/connect/token'
ALLEVA_REST_ADAPTER_KEY = 'alleva-rest-api'
ALLEVA_SUPPORTED_EXPORT_FORMATS = ['PDF', 'DOCX', 'TXT', 'CSV', 'RTF', 'JPG', 'PNG', 'ZIP']
ALLEVA_API_STANDARDS = ['Alleva REST API', 'OpenAPI operation discovery', 'HL7/API readiness']
ALLEVA_REQUIRED_VENDOR_INPUTS = [
    'R3/Alleva live-sync approval',
    'Alleva REST API base URL and OpenAPI URL',
    'OAuth token URL, API client ID, and encrypted API client secret',
    'Validated active-client, treatment-plan, treatment-review, pagination, status, and date/signature endpoint mapping',
]
ALLEVA_DOCUMENT_MANAGER_SECTIONS = [
    {
        'key': 'custom_forms',
        'label': 'Custom Forms',
        'source_description': 'Client-specific forms that can be filled, signed, completed, canceled, and viewed in Alleva Document Manager.',
    },
    {
        'key': 'uploaded_documents',
        'label': 'Uploaded Documents',
        'source_description': 'Client-specific documents uploaded into Alleva that are not native Alleva forms.',
    },
    {
        'key': 'portal_documents',
        'label': 'Portal Documents',
        'source_description': 'Forms completed through the Alleva Client/Family Portal and stored in the client chart.',
    },
    {
        'key': 'labs',
        'label': 'Labs',
        'source_description': 'Lab orders, requisitions, and results when the client environment has a lab integration.',
    },
    {
        'key': 'medications',
        'label': 'Medications',
        'source_description': 'Medication-management or ePrescribe documents when exported or exposed by the client environment.',
    },
    {
        'key': 'notes',
        'label': 'Notes',
        'source_description': 'Progress notes, clinical notes, and session documentation exported from the chart.',
    },
    {
        'key': 'other',
        'label': 'Other',
        'source_description': 'Other Alleva chart material approved by the client for review import.',
    },
]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _validate_emr_enablement(settings_row: AppSetting) -> None:
    if not settings_row.emr_api_enabled:
        return
    missing_fields = []
    if not settings_row.alleva_api_base_url.strip():
        missing_fields.append('Alleva REST API base URL')
    if not settings_row.api_oauth_token_url.strip():
        missing_fields.append('OAuth token URL')
    if not settings_row.api_client_id.strip():
        missing_fields.append('API client ID')
    if not settings_row.api_client_secret:
        missing_fields.append('API client secret')
    if missing_fields:
        raise HTTPException(status_code=400, detail=f'Missing required API setting(s): {", ".join(missing_fields)}')

def _validate_periodic_api_check(settings_row: AppSetting) -> None:
    if not settings_row.emr_periodic_check_enabled:
        return
    missing_fields = []
    if not settings_row.alleva_api_base_url.strip():
        missing_fields.append('REST API base URL')
    if not settings_row.api_oauth_token_url.strip():
        missing_fields.append('OAuth token URL')
    if not settings_row.api_client_id.strip():
        missing_fields.append('API client ID')
    if not settings_row.api_client_secret:
        missing_fields.append('API client secret')
    if missing_fields:
        raise HTTPException(status_code=400, detail=f'Missing required periodic API check field(s): {", ".join(missing_fields)}')


def _validate_alleva_treatment_plan_sync(settings_row: AppSetting) -> None:
    if not (settings_row.alleva_treatment_plan_sync_enabled or settings_row.alleva_treatment_plan_sync_on_startup):
        return
    missing_fields = []
    if not settings_row.alleva_api_base_url.strip():
        missing_fields.append('Alleva REST API base URL')
    if not settings_row.api_oauth_token_url.strip():
        missing_fields.append('Alleva OAuth token URL')
    if not settings_row.api_client_id.strip():
        missing_fields.append('Alleva API client ID')
    if not settings_row.api_client_secret:
        missing_fields.append('Alleva API client secret')
    if not settings_row.alleva_treatment_plan_sync_approved:
        missing_fields.append('R3/Alleva live treatment-plan sync approval')
    if not settings_row.alleva_treatment_plan_endpoint_mapping_validated:
        missing_fields.append('validated Alleva treatment-plan endpoint mapping')
    if missing_fields:
        raise HTTPException(status_code=400, detail=f'Missing required Alleva treatment-plan sync setting(s): {", ".join(missing_fields)}')


def _allowed_transition(role: Role, current: WorkflowState, target: WorkflowState) -> bool:
    allowed = {
        Role.admin: {
            WorkflowState.draft: [WorkflowState.awaiting_manager_review],
            WorkflowState.awaiting_manager_review: [WorkflowState.manager_approved, WorkflowState.manager_rejected],
            WorkflowState.manager_rejected: [WorkflowState.awaiting_manager_review],
        },
        Role.manager: {
            WorkflowState.awaiting_manager_review: [WorkflowState.manager_approved, WorkflowState.manager_rejected],
        },
    }
    return target in allowed.get(role, {}).get(current, [])


def _chart_stmt():
    return select(Chart).options(
        selectinload(Chart.audit_responses),
        selectinload(Chart.counselor),
        selectinload(Chart.source_note_set),
        selectinload(Chart.reviewed_by),
    )


def _note_set_stmt():
    return select(PatientNoteSet).options(
        selectinload(PatientNoteSet.documents),
        selectinload(PatientNoteSet.uploaded_by),
        selectinload(PatientNoteSet.review_charts),
    )


def _ensure_chart_access(chart: Chart | None, user: User) -> Chart:
    if not chart:
        raise HTTPException(status_code=404, detail='Chart not found')
    if user.role == Role.counselor and chart.counselor_id != user.id:
        raise HTTPException(status_code=403, detail='Cannot access this chart')
    return chart


def _find_chart(chart_id: int, user: User, db: Session) -> Chart:
    chart = db.execute(_chart_stmt().where(Chart.id == chart_id)).scalar_one_or_none()
    return _ensure_chart_access(chart, user)


def _ensure_note_set_access(note_set: PatientNoteSet | None, user: User) -> PatientNoteSet:
    if not note_set:
        raise HTTPException(status_code=404, detail='Patient note set not found')
    if user.role == Role.counselor and note_set.uploaded_by_id != user.id:
        raise HTTPException(status_code=403, detail='Cannot access this patient note set')
    return note_set


def _find_note_set(note_set_id: int, user: User, db: Session) -> PatientNoteSet:
    note_set = db.execute(_note_set_stmt().where(PatientNoteSet.id == note_set_id)).scalar_one_or_none()
    return _ensure_note_set_access(note_set, user)


def _timeliness_client_for_patient(patient_id: str, db: Session) -> TreatmentPlanClient | None:
    return (
        db.execute(
            select(TreatmentPlanClient)
            .options(
                selectinload(TreatmentPlanClient.level_of_care_history),
                selectinload(TreatmentPlanClient.treatment_plans),
                selectinload(TreatmentPlanClient.overrides),
            )
            .where(TreatmentPlanClient.patient_id == patient_id)
        )
        .scalars()
        .unique()
        .one_or_none()
    )


def _ensure_all_responses(chart: Chart) -> None:
    existing = {response.item_key for response in chart.audit_responses}
    for template_item in AUDIT_TEMPLATE:
        if template_item['key'] in existing:
            continue
        chart.audit_responses.append(AuditItemResponse(item_key=template_item['key']))


def _status_counts(chart: Chart) -> dict[ComplianceStatus, int]:
    counts = {
        ComplianceStatus.pending: 0,
        ComplianceStatus.yes: 0,
        ComplianceStatus.no: 0,
        ComplianceStatus.na: 0,
    }
    for response in chart.audit_responses:
        counts[response.status] += 1
    return counts


def _latest_review_chart_id(note_set: PatientNoteSet) -> int | None:
    if not note_set.review_charts:
        return None
    latest_chart = max(
        note_set.review_charts,
        key=lambda chart: (chart.created_at or datetime.min.replace(tzinfo=timezone.utc), chart.id),
    )
    return latest_chart.id


def _note_set_summary(note_set: PatientNoteSet) -> dict[str, object]:
    return {
        'id': note_set.id,
        'patient_id': note_set.patient_id,
        'review_chart_id': _latest_review_chart_id(note_set),
        'version': note_set.version,
        'status': note_set.status,
        'upload_mode': note_set.upload_mode,
        'source_system': note_set.source_system,
        'primary_clinician': note_set.primary_clinician,
        'level_of_care': note_set.level_of_care,
        'admission_date': note_set.admission_date,
        'discharge_date': note_set.discharge_date,
        'upload_notes': note_set.upload_notes,
        'source_export_id': note_set.source_export_id,
        'source_patient_resource_id': note_set.source_patient_resource_id,
        'created_at': note_set.created_at,
        'file_count': len(note_set.documents),
    }


def _note_set_detail(note_set: PatientNoteSet) -> dict[str, object]:
    documents = sorted(note_set.documents, key=lambda document: (document.document_date, document.id))
    return {
        **_note_set_summary(note_set),
        'documents': [
            {
                'id': document.id,
                'document_label': document.document_label,
                'original_filename': document.original_filename,
                'content_type': document.content_type,
                'size_bytes': document.size_bytes,
                'sha256': document.sha256,
                'alleva_bucket': document.alleva_bucket,
                'document_type': document.document_type,
                'completion_status': document.completion_status,
                'client_signed': document.client_signed,
                'staff_signed': document.staff_signed,
                'document_date': document.document_date,
                'description': document.description,
                'source_document_id': document.source_document_id,
                'source_attachment_url': document.source_attachment_url,
                'source_author': document.source_author,
                'source_custodian': document.source_custodian,
                'source_security_label': document.source_security_label,
                'created_at': document.created_at,
            }
            for document in documents
        ],
    }


def _patient_id_detection_payload(patient_id: str | None, confidence: str, source_filename: str | None, source_kind: str | None, match_text: str | None, reason: str):
    return {
        'patient_id': patient_id,
        'confidence': confidence,
        'source_filename': source_filename,
        'source_kind': source_kind,
        'match_text': match_text,
        'reason': reason,
    }


def _settings_snapshot(settings_row: AppSetting) -> dict[str, object]:
    return {
        'organization_name': settings_row.organization_name,
        'access_intel_enabled': settings_row.access_intel_enabled,
        'access_geo_lookup_url': settings_row.access_geo_lookup_url,
        'access_reputation_url': settings_row.access_reputation_url,
        'access_reputation_api_key_configured': bool(settings_row.access_reputation_api_key),
        'access_lookup_timeout_seconds': settings_row.access_lookup_timeout_seconds,
        'llm_enabled': settings_row.llm_enabled,
        'llm_provider_name': settings_row.llm_provider_name,
        'llm_base_url': settings_row.llm_base_url,
        'llm_model': settings_row.llm_model,
        'llm_api_key_configured': bool(settings_row.llm_api_key),
        'llm_use_for_access_review': settings_row.llm_use_for_access_review,
        'llm_use_for_evaluation_gap_analysis': settings_row.llm_use_for_evaluation_gap_analysis,
        'llm_analysis_instructions': settings_row.llm_analysis_instructions,
        'emr_api_enabled': settings_row.emr_api_enabled,
        'emr_vendor_name': settings_row.emr_vendor_name,
        'api_client_id': settings_row.api_client_id,
        'api_client_secret_configured': bool(settings_row.api_client_secret),
        'api_oauth_token_url': settings_row.api_oauth_token_url,
        'api_token_auth_style': settings_row.api_token_auth_style,
        'emr_api_timeout_seconds': settings_row.emr_api_timeout_seconds,
        'emr_periodic_check_enabled': settings_row.emr_periodic_check_enabled,
        'emr_periodic_check_interval_minutes': settings_row.emr_periodic_check_interval_minutes,
        'emr_last_check_at': settings_row.emr_last_check_at,
        'emr_last_check_status': settings_row.emr_last_check_status,
        'emr_last_check_message': settings_row.emr_last_check_message,
        'emr_last_successful_check_at': settings_row.emr_last_successful_check_at,
        'emr_last_failure_at': settings_row.emr_last_failure_at,
        'alleva_api_base_url': settings_row.alleva_api_base_url,
        'alleva_openapi_url': settings_row.alleva_openapi_url,
        'alleva_api_version': settings_row.alleva_api_version,
        'alleva_treatment_plan_sync_enabled': settings_row.alleva_treatment_plan_sync_enabled,
        'alleva_treatment_plan_sync_on_startup': settings_row.alleva_treatment_plan_sync_on_startup,
        'alleva_treatment_plan_sync_approved': settings_row.alleva_treatment_plan_sync_approved,
        'alleva_treatment_plan_endpoint_mapping_validated': settings_row.alleva_treatment_plan_endpoint_mapping_validated,
        'alleva_treatment_plan_sync_limit': settings_row.alleva_treatment_plan_sync_limit,
        'alleva_treatment_plan_sync_last_at': settings_row.alleva_treatment_plan_sync_last_at,
        'alleva_treatment_plan_sync_last_status': settings_row.alleva_treatment_plan_sync_last_status,
        'alleva_treatment_plan_sync_last_message': settings_row.alleva_treatment_plan_sync_last_message,
        'alleva_treatment_plan_sync_last_success_at': settings_row.alleva_treatment_plan_sync_last_success_at,
        'alleva_treatment_plan_sync_last_failure_at': settings_row.alleva_treatment_plan_sync_last_failure_at,
        'facility_timezone': settings_row.facility_timezone,
        'treatment_plan_loc_change_window_days': settings_row.treatment_plan_loc_change_window_days,
        'treatment_plan_loc_change_window_validated': settings_row.treatment_plan_loc_change_window_validated,
        'updated_by_id': settings_row.updated_by_id,
    }


def _emr_profile_payload(profile: EmrEndpointProfile) -> dict[str, object]:
    return {
        'id': profile.id,
        'profile_key': profile.profile_key,
        'display_name': profile.display_name,
        'vendor_name': profile.vendor_name,
        'adapter_key': profile.adapter_key,
        'api_base_url': profile.api_base_url,
        'openapi_url': profile.openapi_url,
        'token_url': profile.token_url,
        'token_auth_style': profile.token_auth_style,
        'client_id': profile.client_id,
        'client_id_configured': bool(profile.client_id.strip()),
        'client_secret_configured': bool(profile.client_secret),
        'timeout_seconds': profile.timeout_seconds,
        'is_active': profile.is_active,
        'is_default': profile.is_default,
        'notes': profile.notes,
        'created_by_id': profile.created_by_id,
        'updated_by_id': profile.updated_by_id,
        'created_at': profile.created_at,
        'updated_at': profile.updated_at,
    }


def _emr_profile_snapshot(profile: EmrEndpointProfile) -> dict[str, object]:
    payload = _emr_profile_payload(profile)
    return {
        **payload,
        'client_secret_configured': bool(profile.client_secret),
    }


def _find_emr_endpoint_profile(profile_id: int, db: Session) -> EmrEndpointProfile:
    profile = db.execute(select(EmrEndpointProfile).where(EmrEndpointProfile.id == profile_id)).scalar_one_or_none()
    if profile is None:
        raise HTTPException(status_code=404, detail='EMR endpoint profile not found')
    return profile


def _api_connection_profile(settings_row: AppSetting) -> dict[str, object]:
    api_base_url = settings_row.alleva_api_base_url.strip()
    return {
        'adapter_key': ALLEVA_REST_ADAPTER_KEY,
        'enabled': settings_row.emr_api_enabled,
        'vendor_name': settings_row.emr_vendor_name,
        'live_import_status': 'readiness_only_pending_approval_and_endpoint_mapping',
        'api_base_url': api_base_url,
        'openapi_url': settings_row.alleva_openapi_url.strip(),
        'oauth_token_url_configured': bool(settings_row.api_oauth_token_url.strip()),
        'client_id_configured': bool(settings_row.api_client_id.strip()),
        'client_secret_configured': bool(settings_row.api_client_secret.strip()),
        'standards': ALLEVA_API_STANDARDS,
        'supported_export_formats': ALLEVA_SUPPORTED_EXPORT_FORMATS,
        'document_manager_sections': ALLEVA_DOCUMENT_MANAGER_SECTIONS,
        'required_vendor_inputs': ALLEVA_REQUIRED_VENDOR_INPUTS,
    }


def _ensure_default_emr_endpoint_profile(db: Session, settings_row: AppSetting, user: User | None = None) -> None:
    existing = db.execute(select(EmrEndpointProfile.id).limit(1)).scalar_one_or_none()
    if existing is not None:
        return
    now = _utc_now()
    profile = EmrEndpointProfile(
        profile_key='alleva-default',
        display_name='Alleva default REST API profile',
        vendor_name=settings_row.emr_vendor_name or 'Alleva REST API',
        adapter_key=ALLEVA_REST_ADAPTER_KEY,
        api_base_url=settings_row.alleva_api_base_url or DEFAULT_ALLEVA_API_BASE_URL,
        openapi_url=settings_row.alleva_openapi_url or DEFAULT_ALLEVA_OPENAPI_URL,
        token_url=settings_row.api_oauth_token_url,
        token_auth_style=settings_row.api_token_auth_style,
        client_id=settings_row.api_client_id,
        client_secret=settings_row.api_client_secret,
        timeout_seconds=settings_row.emr_api_timeout_seconds,
        is_active=True,
        is_default=True,
        notes='Seeded from current app settings. Live sync remains disabled until R3/Alleva approval and endpoint mapping validation.',
        created_by_id=user.id if user else None,
        updated_by_id=user.id if user else None,
        created_at=now,
        updated_at=now,
    )
    db.add(profile)
    db.flush()


def _make_only_default_profile(db: Session, profile: EmrEndpointProfile) -> None:
    if not profile.is_default:
        return
    for other in db.execute(select(EmrEndpointProfile).where(EmrEndpointProfile.id != profile.id)).scalars().all():
        other.is_default = False


def _chart_summary(chart: Chart) -> dict[str, object]:
    _ensure_all_responses(chart)
    counts = _status_counts(chart)
    return {
        'id': chart.id,
        'source_note_set_id': chart.source_note_set_id,
        'patient_id': chart.patient_id,
        'client_name': chart.client_name,
        'level_of_care': chart.level_of_care,
        'admission_date': chart.admission_date,
        'discharge_date': chart.discharge_date,
        'primary_clinician': chart.primary_clinician,
        'auditor_name': chart.auditor_name,
        'other_details': chart.other_details,
        'counselor_id': chart.counselor_id,
        'state': chart.state,
        'system_score': chart.system_score,
        'system_summary': chart.system_summary,
        'manager_comment': chart.manager_comment,
        'reviewed_by_id': chart.reviewed_by_id,
        'system_generated_at': chart.system_generated_at,
        'reviewed_at': chart.reviewed_at,
        'created_at': chart.created_at,
        'notes': chart.notes,
        'pending_items': counts[ComplianceStatus.pending],
        'passed_items': counts[ComplianceStatus.yes],
        'failed_items': counts[ComplianceStatus.no],
        'not_applicable_items': counts[ComplianceStatus.na],
    }


def _chart_detail(chart: Chart) -> dict[str, object]:
    summary = _chart_summary(chart)
    responses_by_key = {response.item_key: response for response in chart.audit_responses}
    checklist_items = []

    for template_item in AUDIT_TEMPLATE:
        response = responses_by_key.get(template_item['key'])
        checklist_items.append(
            {
                'item_key': template_item['key'],
                'step': template_item['step'],
                'section': template_item['section'],
                'label': template_item['label'],
                'timeframe': template_item['timeframe'],
                'instructions': template_item['instructions'],
                'evidence_hint': template_item['evidence_hint'],
                'policy_note': template_item['policy_note'],
                'status': response.status if response else ComplianceStatus.pending,
                'notes': response.notes if response else '',
                'evidence_location': response.evidence_location if response else '',
                'evidence_date': response.evidence_date if response else '',
                'expiration_date': response.expiration_date if response else '',
            }
        )

    return {**summary, 'checklist_items': checklist_items}


def _audit_log_payload(log: AuditLog, timezone_name: str) -> dict[str, object]:
    return {
        'event_id': log.event_id,
        'timestamp_utc': log.timestamp_utc,
        'timestamp_local': format_local_timestamp(log.timestamp_utc, timezone_name),
        'effective_timezone': normalize_timezone_name(timezone_name),
        'actor_username': log.actor_username,
        'actor_role': log.actor_role,
        'actor_type': log.actor_type,
        'source_ip': log.source_ip,
        'forwarded_for': log.forwarded_for,
        'source_host': log.source_host,
        'source_port': log.source_port,
        'request_id': log.request_id,
        'correlation_id': log.correlation_id,
        'session_id': log.session_id,
        'http_method': log.http_method,
        'request_path': log.request_path,
        'route_template': log.route_template,
        'query_string': log.query_string,
        'http_status_code': log.http_status_code,
        'event_category': log.event_category,
        'action': log.action,
        'target_entity': log.target_entity,
        'target_entity_type': log.target_entity_type,
        'target_entity_id': log.target_entity_id,
        'patient_id': log.patient_id,
        'message': log.message,
        'details': log.details,
        'before_state': log.before_state,
        'after_state': log.after_state,
        'diff_state': log.diff_state,
        'cef_extension': log.cef_extension,
        'cef_payload': log.cef_payload,
        'outcome_status': log.outcome_status,
        'severity': log.severity,
        'prev_hash': log.prev_hash,
        'hash': log.hash,
    }


def _normalized_chart_name(payload: ChartUpdate | ChartCreate) -> str:
    patient_id = payload.patient_id.strip()
    client_name = payload.client_name.strip()
    return client_name or patient_id


def _apply_chart_updates(chart: Chart, payload: ChartUpdate | ChartCreate) -> None:
    chart.patient_id = payload.patient_id.strip()
    chart.client_name = _normalized_chart_name(payload)
    chart.level_of_care = payload.level_of_care.strip()
    chart.admission_date = payload.admission_date.strip()
    chart.discharge_date = payload.discharge_date.strip()
    chart.primary_clinician = payload.primary_clinician.strip()
    chart.auditor_name = payload.auditor_name.strip()
    chart.other_details = payload.other_details.strip()
    chart.notes = payload.notes.strip()

    if not isinstance(payload, ChartUpdate):
        return

    existing = {response.item_key: response for response in chart.audit_responses}
    seen_keys: set[str] = set()
    for item in payload.checklist_items:
        if item.item_key not in AUDIT_TEMPLATE_BY_KEY:
            raise HTTPException(status_code=400, detail=f'Unknown checklist item: {item.item_key}')
        response = existing.get(item.item_key)
        if not response:
            response = AuditItemResponse(item_key=item.item_key)
            chart.audit_responses.append(response)
            existing[item.item_key] = response
        response.status = item.status
        response.notes = item.notes.strip()
        response.evidence_location = item.evidence_location.strip()
        response.evidence_date = item.evidence_date.strip()
        response.expiration_date = item.expiration_date.strip()
        response.updated_at = _utc_now()
        seen_keys.add(item.item_key)

    missing_keys = [template_item['key'] for template_item in AUDIT_TEMPLATE if template_item['key'] not in seen_keys]
    if missing_keys:
        raise HTTPException(status_code=400, detail=f'Missing checklist items: {", ".join(missing_keys)}')


def _sync_chart_display_name_to_timeliness(db: Session, chart: Chart) -> None:
    if not chart.patient_id.strip() or not chart.client_name.strip():
        return
    client = db.execute(select(TreatmentPlanClient).where(TreatmentPlanClient.patient_id == chart.patient_id)).scalar_one_or_none()
    if client is None:
        return
    client.permitted_name = chart.client_name.strip()
    client.updated_at = _utc_now()


def _parse_manifest(file_manifest: str, files: list[UploadFile]) -> list[PatientNoteDocumentUploadInput]:
    adapter = TypeAdapter(list[PatientNoteDocumentUploadInput])
    if file_manifest.strip():
        try:
            manifest = adapter.validate_json(file_manifest)
        except ValidationError as exc:
            raise HTTPException(status_code=400, detail=f'Invalid file manifest: {exc.errors()[0]["msg"]}') from exc
    else:
        manifest = []

    if not manifest:
        manifest = [PatientNoteDocumentUploadInput(client_file_name=file.filename or '') for file in files]

    if len(manifest) != len(files):
        raise HTTPException(status_code=400, detail='Uploaded file manifest must include exactly one entry per file')

    normalized: list[PatientNoteDocumentUploadInput] = []
    for metadata, upload in zip(manifest, files):
        expected_name = upload.filename or ''
        if metadata.client_file_name and metadata.client_file_name != expected_name:
            raise HTTPException(status_code=400, detail=f'File manifest mismatch for uploaded file {expected_name}')
        normalized.append(
            metadata.model_copy(
                update={
                    'client_file_name': expected_name,
                    'document_label': metadata.document_label.strip() or Path(expected_name or 'document').stem,
                    'document_type': metadata.document_type.strip() or 'clinical_note',
                    'description': metadata.description.strip(),
                    'document_date': metadata.document_date.strip(),
                    'source_document_id': metadata.source_document_id.strip(),
                    'source_attachment_url': metadata.source_attachment_url.strip(),
                    'source_author': metadata.source_author.strip(),
                    'source_custodian': metadata.source_custodian.strip(),
                    'source_security_label': metadata.source_security_label.strip(),
                }
            )
        )
    return normalized


def _validate_upload_batch(files: list[UploadFile]) -> None:
    if len(files) > settings.max_upload_file_count:
        raise HTTPException(status_code=413, detail=f'Upload includes too many files; maximum is {settings.max_upload_file_count}')
    total_size = 0
    for upload in files:
        # Validate names before any text inspection so detection endpoints reject
        # unsafe formats just as strictly as the final storage endpoint.
        sanitize_filename(upload.filename or '')
        size = getattr(upload, 'size', None)
        if isinstance(size, int) and size > 0:
            total_size += size
            if size > settings.max_upload_file_bytes:
                limit_mb = settings.max_upload_file_bytes // (1024 * 1024)
                raise HTTPException(status_code=413, detail=f'{upload.filename or "Uploaded file"} exceeds the {limit_mb}MB per-file limit')
    if total_size > settings.max_upload_total_bytes:
        limit_mb = settings.max_upload_total_bytes // (1024 * 1024)
        raise HTTPException(status_code=413, detail=f'Upload exceeds the {limit_mb}MB total binder limit')


@router.get('/settings', response_model=AppSettingsOut)
def get_app_settings(request: Request, user: User = Depends(require_roles(Role.admin)), db: Session = Depends(get_db)):
    settings_row = get_or_create_app_settings(db)
    log_event(
        db,
        request,
        'settings.read',
        actor=user,
        event_category='configuration',
        target_entity='app_settings',
        target_entity_type='app_setting',
        target_entity_id=str(settings_row.id),
        details=_settings_snapshot(settings_row),
        message='Application settings viewed.',
    )
    return app_settings_public_payload(settings_row)


UI_EVENT_CONTEXT_ALLOWLIST = {'button_text', 'button_type', 'disabled', 'blocked_reason', 'view', 'dialog', 'target'}


def _clean_ui_text(value: object, *, limit: int = 160) -> str:
    return ' '.join(str(value or '').split())[:limit]


def _sanitized_ui_context(context: dict[str, object]) -> dict[str, object]:
    sanitized: dict[str, object] = {}
    for key, value in (context or {}).items():
        key_text = _clean_ui_text(key, limit=40)
        if key_text not in UI_EVENT_CONTEXT_ALLOWLIST:
            continue
        if isinstance(value, bool):
            sanitized[key_text] = value
        elif isinstance(value, int | float):
            sanitized[key_text] = value
        else:
            sanitized[key_text] = _clean_ui_text(value, limit=160)
    return sanitized


@router.patch('/settings', response_model=AppSettingsOut)
def update_app_settings(
    payload: AppSettingsUpdate,
    request: Request,
    user: User = Depends(require_roles(Role.admin)),
    db: Session = Depends(get_db),
):
    settings_row = get_or_create_app_settings(db)
    before_state = _settings_snapshot(settings_row)

    if payload.organization_name is not None:
        settings_row.organization_name = payload.organization_name.strip() or settings_row.organization_name
    if payload.access_intel_enabled is not None:
        settings_row.access_intel_enabled = payload.access_intel_enabled
    if payload.access_geo_lookup_url is not None:
        settings_row.access_geo_lookup_url = payload.access_geo_lookup_url.strip() or settings_row.access_geo_lookup_url
    if payload.access_reputation_url is not None:
        settings_row.access_reputation_url = payload.access_reputation_url.strip() or settings_row.access_reputation_url
    if payload.access_lookup_timeout_seconds is not None:
        settings_row.access_lookup_timeout_seconds = payload.access_lookup_timeout_seconds
    if payload.access_reputation_api_key is not None:
        candidate_key = payload.access_reputation_api_key.strip()
        if candidate_key:
            settings_row.access_reputation_api_key = encrypt_text_secret(candidate_key)
    if payload.clear_access_reputation_api_key:
        settings_row.access_reputation_api_key = ''
    if payload.llm_enabled is not None:
        settings_row.llm_enabled = payload.llm_enabled
    if payload.llm_provider_name is not None:
        settings_row.llm_provider_name = payload.llm_provider_name.strip() or settings_row.llm_provider_name
    if payload.llm_base_url is not None:
        settings_row.llm_base_url = payload.llm_base_url.strip() or settings_row.llm_base_url
    if payload.llm_model is not None:
        settings_row.llm_model = payload.llm_model.strip() or settings_row.llm_model
    if payload.llm_api_key is not None:
        candidate_key = payload.llm_api_key.strip()
        if candidate_key:
            settings_row.llm_api_key = encrypt_text_secret(candidate_key)
    if payload.clear_llm_api_key:
        settings_row.llm_api_key = ''
    if payload.llm_use_for_access_review is not None:
        settings_row.llm_use_for_access_review = payload.llm_use_for_access_review
    if payload.llm_use_for_evaluation_gap_analysis is not None:
        settings_row.llm_use_for_evaluation_gap_analysis = payload.llm_use_for_evaluation_gap_analysis
    if payload.llm_analysis_instructions is not None:
        settings_row.llm_analysis_instructions = payload.llm_analysis_instructions.strip()
    if payload.emr_api_enabled is not None:
        settings_row.emr_api_enabled = payload.emr_api_enabled
    if payload.emr_vendor_name is not None:
        settings_row.emr_vendor_name = payload.emr_vendor_name.strip() or settings_row.emr_vendor_name
    if payload.api_client_id is not None:
        settings_row.api_client_id = payload.api_client_id.strip()
    if payload.api_client_secret is not None:
        candidate_secret = payload.api_client_secret.strip()
        if candidate_secret:
            settings_row.api_client_secret = encrypt_text_secret(candidate_secret)
    if payload.clear_api_client_secret:
        settings_row.api_client_secret = ''
    if payload.api_oauth_token_url is not None:
        settings_row.api_oauth_token_url = payload.api_oauth_token_url.strip()
    if payload.api_token_auth_style is not None:
        settings_row.api_token_auth_style = payload.api_token_auth_style
    if payload.emr_api_timeout_seconds is not None:
        settings_row.emr_api_timeout_seconds = payload.emr_api_timeout_seconds
    if payload.emr_periodic_check_enabled is not None:
        settings_row.emr_periodic_check_enabled = payload.emr_periodic_check_enabled
    if payload.emr_periodic_check_interval_minutes is not None:
        settings_row.emr_periodic_check_interval_minutes = payload.emr_periodic_check_interval_minutes
    if payload.alleva_api_base_url is not None:
        settings_row.alleva_api_base_url = payload.alleva_api_base_url.strip() or 'https://api.allevasoft.com'
    if payload.alleva_openapi_url is not None:
        settings_row.alleva_openapi_url = payload.alleva_openapi_url.strip() or 'https://api.allevasoft.com/swagger/v1/swagger.json'
    if payload.alleva_api_version is not None:
        settings_row.alleva_api_version = payload.alleva_api_version.strip() or '1.0'
    if payload.alleva_treatment_plan_sync_enabled is not None:
        settings_row.alleva_treatment_plan_sync_enabled = payload.alleva_treatment_plan_sync_enabled
    if payload.alleva_treatment_plan_sync_on_startup is not None:
        settings_row.alleva_treatment_plan_sync_on_startup = payload.alleva_treatment_plan_sync_on_startup
    if payload.alleva_treatment_plan_sync_approved is not None:
        settings_row.alleva_treatment_plan_sync_approved = payload.alleva_treatment_plan_sync_approved
    if payload.alleva_treatment_plan_endpoint_mapping_validated is not None:
        settings_row.alleva_treatment_plan_endpoint_mapping_validated = payload.alleva_treatment_plan_endpoint_mapping_validated
    if payload.alleva_treatment_plan_sync_limit is not None:
        settings_row.alleva_treatment_plan_sync_limit = payload.alleva_treatment_plan_sync_limit
    if payload.facility_timezone is not None:
        try:
            settings_row.facility_timezone = normalize_timezone_name(payload.facility_timezone)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    if payload.treatment_plan_loc_change_window_days is not None:
        settings_row.treatment_plan_loc_change_window_days = payload.treatment_plan_loc_change_window_days
    if payload.treatment_plan_loc_change_window_validated is not None:
        settings_row.treatment_plan_loc_change_window_validated = payload.treatment_plan_loc_change_window_validated
    _validate_emr_enablement(settings_row)
    _validate_periodic_api_check(settings_row)
    _validate_alleva_treatment_plan_sync(settings_row)

    touch_app_settings(settings_row, actor=user)
    db.commit()
    db.refresh(settings_row)

    after_state = _settings_snapshot(settings_row)
    log_event(
        db,
        request,
        'settings.update',
        actor=user,
        event_category='configuration',
        target_entity='app_settings',
        target_entity_type='app_setting',
        target_entity_id=str(settings_row.id),
        details=after_state,
        before_state=before_state,
        after_state=after_state,
        diff_state={key: {'before': before_state.get(key), 'after': after_state.get(key)} for key in sorted(set(before_state) | set(after_state)) if before_state.get(key) != after_state.get(key)},
        message='Application settings updated.',
    )
    return app_settings_public_payload(settings_row)


@router.post('/ui-events', status_code=204)
def record_ui_event(payload: UiEventInput, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    action_name = _clean_ui_text(payload.action_name)
    result = _clean_ui_text(payload.result or 'clicked', limit=40) or 'clicked'
    screen = _clean_ui_text(payload.screen, limit=80)
    log_event(
        db,
        request,
        'ui.button.click' if result == 'clicked' else 'ui.button.event',
        actor=user,
        event_category='ui_interaction',
        target_entity=action_name,
        target_entity_type='ui_button',
        details={
            'screen': screen,
            'action_name': action_name,
            'result': result,
            'context': _sanitized_ui_context(payload.context),
        },
        message=f'UI button event recorded: {screen or "unknown screen"} / {action_name}.',
    )
    return Response(status_code=204)


@router.get('/system/readiness', response_model=ReadinessOut)
def get_system_readiness(request: Request, user: User = Depends(require_roles(Role.admin)), db: Session = Depends(get_db)):
    payload = readiness_payload()
    log_event(
        db,
        request,
        'system.readiness.read',
        actor=user,
        event_category='system',
        target_entity='runtime_readiness',
        target_entity_type='runtime_check',
        details={'status': payload['status'], 'failed': payload['failed'], 'warnings': payload['warnings']},
        message='Runtime readiness checks viewed.',
    )
    return payload


@router.get('/emr/profile', response_model=EmrConnectionProfileOut)
def get_emr_profile(request: Request, user: User = Depends(require_roles(Role.admin)), db: Session = Depends(get_db)):
    settings_row = get_or_create_app_settings(db)
    profile = _api_connection_profile(settings_row)
    log_event(
        db,
        request,
        'emr.profile.read',
        actor=user,
        event_category='configuration',
        target_entity='emr_connection_profile',
        target_entity_type='emr_connection',
        details=profile,
        message='EMR connection profile viewed.',
    )
    return profile


@router.get('/emr/profiles', response_model=list[EmrEndpointProfileOut])
def list_emr_endpoint_profiles(request: Request, user: User = Depends(require_roles(Role.admin)), db: Session = Depends(get_db)):
    settings_row = get_or_create_app_settings(db)
    seeded = db.execute(select(EmrEndpointProfile.id).limit(1)).scalar_one_or_none() is None
    _ensure_default_emr_endpoint_profile(db, settings_row, user)
    if seeded:
        db.commit()
    profiles = list(db.execute(select(EmrEndpointProfile).order_by(EmrEndpointProfile.is_default.desc(), EmrEndpointProfile.display_name.asc())).scalars().all())
    log_event(
        db,
        request,
        'emr.endpoint_profile.list.read',
        actor=user,
        event_category='configuration',
        target_entity='emr_endpoint_profiles',
        target_entity_type='emr_endpoint_profile',
        details={'count': len(profiles), 'seeded_default': seeded},
        message='EMR endpoint profile list viewed.',
    )
    return [_emr_profile_payload(profile) for profile in profiles]


@router.post('/emr/profiles', response_model=EmrEndpointProfileOut)
def create_emr_endpoint_profile(
    payload: EmrEndpointProfileCreate,
    request: Request,
    user: User = Depends(require_roles(Role.admin)),
    db: Session = Depends(get_db),
):
    profile_key = payload.profile_key.strip().lower()
    existing = db.execute(select(EmrEndpointProfile).where(EmrEndpointProfile.profile_key == profile_key)).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=409, detail='An EMR endpoint profile with this key already exists')
    now = _utc_now()
    profile = EmrEndpointProfile(
        profile_key=profile_key,
        display_name=payload.display_name.strip(),
        vendor_name=payload.vendor_name.strip() or 'Alleva REST API',
        adapter_key=payload.adapter_key.strip() or ALLEVA_REST_ADAPTER_KEY,
        api_base_url=payload.api_base_url.strip() or DEFAULT_ALLEVA_API_BASE_URL,
        openapi_url=payload.openapi_url.strip() or DEFAULT_ALLEVA_OPENAPI_URL,
        token_url=payload.token_url.strip() or DEFAULT_ALLEVA_TOKEN_URL,
        token_auth_style=payload.token_auth_style,
        client_id=payload.client_id.strip(),
        client_secret=encrypt_text_secret(payload.client_secret.strip()) if payload.client_secret and payload.client_secret.strip() else '',
        timeout_seconds=payload.timeout_seconds,
        is_active=payload.is_active,
        is_default=payload.is_default,
        notes=payload.notes.strip(),
        created_by_id=user.id,
        updated_by_id=user.id,
        created_at=now,
        updated_at=now,
    )
    db.add(profile)
    db.flush()
    _make_only_default_profile(db, profile)
    db.commit()
    db.refresh(profile)
    log_event(
        db,
        request,
        'emr.endpoint_profile.create',
        actor=user,
        event_category='configuration',
        target_entity=f'emr_endpoint_profile:{profile.id}',
        target_entity_type='emr_endpoint_profile',
        target_entity_id=str(profile.id),
        details={'profile_key': profile.profile_key, 'client_secret_configured': bool(profile.client_secret)},
        after_state=_emr_profile_snapshot(profile),
        message=f'EMR endpoint profile {profile.profile_key} created.',
    )
    return _emr_profile_payload(profile)


@router.patch('/emr/profiles/{profile_id}', response_model=EmrEndpointProfileOut)
def update_emr_endpoint_profile(
    profile_id: int,
    payload: EmrEndpointProfileUpdate,
    request: Request,
    user: User = Depends(require_roles(Role.admin)),
    db: Session = Depends(get_db),
):
    profile = _find_emr_endpoint_profile(profile_id, db)
    before = _emr_profile_snapshot(profile)
    if payload.display_name is not None:
        profile.display_name = payload.display_name.strip()
    if payload.vendor_name is not None:
        profile.vendor_name = payload.vendor_name.strip() or profile.vendor_name
    if payload.adapter_key is not None:
        profile.adapter_key = payload.adapter_key.strip() or profile.adapter_key
    if payload.api_base_url is not None:
        profile.api_base_url = payload.api_base_url.strip() or DEFAULT_ALLEVA_API_BASE_URL
    if payload.openapi_url is not None:
        profile.openapi_url = payload.openapi_url.strip() or DEFAULT_ALLEVA_OPENAPI_URL
    if payload.token_url is not None:
        profile.token_url = payload.token_url.strip() or DEFAULT_ALLEVA_TOKEN_URL
    if payload.token_auth_style is not None:
        profile.token_auth_style = payload.token_auth_style
    if payload.client_id is not None:
        profile.client_id = payload.client_id.strip()
    if payload.clear_client_secret:
        profile.client_secret = ''
    elif payload.client_secret and payload.client_secret.strip():
        profile.client_secret = encrypt_text_secret(payload.client_secret.strip())
    if payload.timeout_seconds is not None:
        profile.timeout_seconds = payload.timeout_seconds
    if payload.is_active is not None:
        profile.is_active = payload.is_active
    if payload.is_default is not None:
        profile.is_default = payload.is_default
    if payload.notes is not None:
        profile.notes = payload.notes.strip()
    profile.updated_by_id = user.id
    profile.updated_at = _utc_now()
    _make_only_default_profile(db, profile)
    db.commit()
    db.refresh(profile)
    after = _emr_profile_snapshot(profile)
    log_event(
        db,
        request,
        'emr.endpoint_profile.update',
        actor=user,
        event_category='configuration',
        target_entity=f'emr_endpoint_profile:{profile.id}',
        target_entity_type='emr_endpoint_profile',
        target_entity_id=str(profile.id),
        details={'profile_key': profile.profile_key, 'client_secret_configured': bool(profile.client_secret)},
        before_state=before,
        after_state=after,
        diff_state={key: {'before': before.get(key), 'after': after.get(key)} for key in sorted(set(before) | set(after)) if before.get(key) != after.get(key)},
        message=f'EMR endpoint profile {profile.profile_key} updated.',
    )
    return _emr_profile_payload(profile)


@router.post('/emr/profiles/{profile_id}/activate', response_model=AppSettingsOut)
def activate_emr_endpoint_profile(
    profile_id: int,
    request: Request,
    user: User = Depends(require_roles(Role.admin)),
    db: Session = Depends(get_db),
):
    profile = _find_emr_endpoint_profile(profile_id, db)
    if not profile.is_active:
        raise HTTPException(status_code=400, detail='Archived EMR endpoint profiles cannot be activated')
    settings_row = get_or_create_app_settings(db)
    before = _settings_snapshot(settings_row)
    settings_row.emr_vendor_name = profile.vendor_name
    settings_row.alleva_api_base_url = profile.api_base_url
    settings_row.alleva_openapi_url = profile.openapi_url
    settings_row.api_client_id = profile.client_id
    if profile.client_secret:
        settings_row.api_client_secret = profile.client_secret
    settings_row.api_oauth_token_url = profile.token_url
    settings_row.api_token_auth_style = profile.token_auth_style
    settings_row.emr_api_timeout_seconds = profile.timeout_seconds
    profile.is_default = True
    profile.updated_by_id = user.id
    profile.updated_at = _utc_now()
    _make_only_default_profile(db, profile)
    touch_app_settings(settings_row, actor=user)
    db.commit()
    db.refresh(settings_row)
    after = _settings_snapshot(settings_row)
    log_event(
        db,
        request,
        'emr.endpoint_profile.activate',
        actor=user,
        event_category='configuration',
        target_entity=f'emr_endpoint_profile:{profile.id}',
        target_entity_type='emr_endpoint_profile',
        target_entity_id=str(profile.id),
        details={'profile_key': profile.profile_key, 'client_secret_configured': bool(profile.client_secret)},
        before_state=before,
        after_state=after,
        diff_state={key: {'before': before.get(key), 'after': after.get(key)} for key in sorted(set(before) | set(after)) if before.get(key) != after.get(key)},
        message=f'EMR endpoint profile {profile.profile_key} activated for API testing.',
    )
    return app_settings_public_payload(settings_row)


@router.delete('/emr/profiles/{profile_id}')
def delete_emr_endpoint_profile(profile_id: int, request: Request, user: User = Depends(require_roles(Role.admin)), db: Session = Depends(get_db)):
    profile = _find_emr_endpoint_profile(profile_id, db)
    if profile.is_default:
        raise HTTPException(status_code=400, detail='The default EMR endpoint profile cannot be deleted; activate another profile first')
    before = _emr_profile_snapshot(profile)
    profile_key = profile.profile_key
    db.delete(profile)
    db.commit()
    log_event(
        db,
        request,
        'emr.endpoint_profile.delete',
        actor=user,
        event_category='configuration',
        target_entity=f'emr_endpoint_profile:{profile_id}',
        target_entity_type='emr_endpoint_profile',
        target_entity_id=str(profile_id),
        details={'profile_key': profile_key},
        before_state=before,
        message=f'EMR endpoint profile {profile_key} deleted.',
    )
    return {'status': 'deleted', 'profile_key': profile_key}


@router.get('/review-source-discovery', response_model=ReviewSourceDiscoveryOut)
def get_review_source_discovery(
    request: Request,
    user: User = Depends(require_roles(*NOTE_SET_ROLES)),
    db: Session = Depends(get_db),
):
    settings_row = get_or_create_app_settings(db)
    note_set_stmt = _note_set_stmt().where(PatientNoteSet.status == NoteSetStatus.active)
    if user.role == Role.counselor:
        note_set_stmt = note_set_stmt.where(PatientNoteSet.uploaded_by_id == user.id)
    note_sets = list(db.execute(note_set_stmt.order_by(PatientNoteSet.created_at.desc(), PatientNoteSet.id.desc())).scalars().unique().all())
    payload = review_source_discovery_payload(db, settings_row, note_sets)
    log_event(
        db,
        request,
        'review_source.discovery.read',
        actor=user,
        event_category='data_access',
        target_entity='review_source_discovery',
        target_entity_type='review_source_discovery',
        details={
            'item_count': len(payload['items']),
            'api_configured': payload['api_configured'],
            'live_import_status': payload['live_import_status'],
        },
        message='Review-source discovery queue viewed.',
    )
    return payload


@router.post('/review-source-discovery/run-daily-check', response_model=ReviewSourceDiscoveryOut)
def run_review_source_daily_check(
    request: Request,
    user: User = Depends(require_roles(Role.admin, Role.manager)),
    db: Session = Depends(get_db),
):
    settings_row = get_or_create_app_settings(db)
    note_set_stmt = _note_set_stmt().where(PatientNoteSet.status == NoteSetStatus.active)
    note_sets = list(db.execute(note_set_stmt.order_by(PatientNoteSet.created_at.desc(), PatientNoteSet.id.desc())).scalars().unique().all())
    api_check_result = run_periodic_api_check(db, settings_row)
    db.refresh(settings_row)
    payload = review_source_discovery_payload(db, settings_row, note_sets)
    if api_check_result is not None:
        payload['last_check_mode'] = 'manual_api_readiness_check'
        payload['plain_english_status'] = (
            f"Manual API readiness check used the active App settings connection and returned "
            f"{api_check_result.get('status', 'unknown')}: {api_check_result.get('message', 'No message returned.')}"
        )
        if api_check_result.get('status') == 'ok':
            payload['api_mode_label'] = 'Manual readiness check succeeded'
        elif api_check_result.get('status') in {'fail', 'skipped'}:
            payload['api_mode_label'] = 'Manual readiness check needs attention'
    log_event(
        db,
        request,
        'review_source.daily_check.run',
        actor=user,
        event_category='workflow',
        target_entity='review_source_daily_check',
        target_entity_type='review_source_discovery',
        details={
            'refresh_mode': payload['refresh_mode'],
            'changed_item_count': payload['changed_item_count'],
            'error_count': payload['error_count'],
            'live_import_enabled': payload['live_import_enabled'],
            'api_mode': payload['api_mode'],
            'api_check_status': api_check_result.get('status') if isinstance(api_check_result, dict) else '',
        },
        message='Manual API readiness/review-source check run in safe readiness/mock mode.',
    )
    return payload


@router.post('/alleva/treatment-plan-sync/run')
def run_alleva_treatment_plan_sync_now(request: Request, user: User = Depends(require_roles(Role.admin)), db: Session = Depends(get_db)):
    settings_row = get_or_create_app_settings(db)
    result = run_alleva_treatment_plan_sync(db, settings_row, actor=user, startup=False)
    db.refresh(settings_row)
    log_event(
        db,
        request,
        'alleva.treatment_plan_sync.manual_run',
        actor=user,
        event_category='integration',
        target_entity='alleva_treatment_plan_sync',
        target_entity_type='integration_sync',
        details={'status': result.get('status'), 'upserted_client_count': result.get('upserted_client_count', 0)},
        outcome_status='success' if result.get('status') in {'ok', 'skipped'} else 'failure',
        severity='info' if result.get('status') in {'ok', 'skipped'} else 'warning',
        message='Manual Alleva REST treatment-plan sync requested.',
    )
    return {'sync_result': result, 'settings': app_settings_public_payload(settings_row)}


@router.get('/audit-template', response_model=list[AuditTemplateSectionOut])
def get_audit_template(request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    sections = audit_sections()
    log_event(
        db,
        request,
        'audit.template.read',
        actor=user,
        event_category='data_access',
        target_entity='audit_template',
        target_entity_type='template',
        details={'section_count': len(sections)},
        message='Audit checklist template viewed.',
    )
    return sections


@router.get('/treatment-plan-checklist', response_model=TreatmentPlanChecklistOut)
def get_treatment_plan_checklist(request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    checklist = load_treatment_plan_checklist()
    log_event(
        db,
        request,
        'treatment_plan_checklist.read',
        actor=user,
        event_category='data_access',
        target_entity=checklist['checklist_id'],
        target_entity_type='treatment_plan_checklist',
        target_entity_id=checklist['version'],
        details={'checklist_id': checklist['checklist_id'], 'version': checklist['version'], 'step_count': len(checklist['steps'])},
        message=f"Treatment Plan Checklist {checklist['version']} viewed by {user.username}.",
    )
    return checklist


@router.get('/charts', response_model=list[ChartSummaryOut])
def list_charts(
    request: Request,
    patient_id: str | None = Query(default=None),
    state: WorkflowState | None = Query(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    stmt = _chart_stmt()
    if user.role == Role.counselor:
        stmt = stmt.where(Chart.counselor_id == user.id)
    if patient_id and patient_id.strip():
        stmt = stmt.where(Chart.patient_id == patient_id.strip())
    if state:
        stmt = stmt.where(Chart.state == state)
    charts = list(db.execute(stmt.order_by(Chart.created_at.desc(), Chart.id.desc())).scalars().unique().all())
    log_event(
        db,
        request,
        'chart.list.read',
        actor=user,
        event_category='data_access',
        target_entity='chart_queue',
        target_entity_type='chart_queue',
        patient_id=patient_id.strip() if patient_id and patient_id.strip() else None,
        details={'count': len(charts), 'state': state.value if state else None},
        message=f'Chart queue viewed by {user.username}.',
    )
    return [_chart_summary(chart) for chart in charts]


@router.post('/charts', response_model=ChartDetailOut)
def create_chart(payload: ChartCreate, request: Request, user: User = Depends(require_roles(Role.admin)), db: Session = Depends(get_db)):
    chart = Chart(
        patient_id='',
        client_name='',
        level_of_care='',
        admission_date='',
        discharge_date='',
        primary_clinician='',
        auditor_name=payload.auditor_name.strip() or user.username,
        other_details='',
        counselor_id=user.id,
        notes='',
        state=WorkflowState.draft,
    )
    _apply_chart_updates(chart, payload)
    chart.auditor_name = chart.auditor_name or user.username
    _ensure_all_responses(chart)
    db.add(chart)
    db.commit()
    chart = _find_chart(chart.id, user, db)
    log_event(
        db,
        request,
        'chart.create',
        actor=user,
        event_category='workflow',
        target_entity=f'chart:{chart.id}',
        target_entity_type='chart',
        target_entity_id=str(chart.id),
        patient_id=chart.patient_id,
        details={'state': chart.state.value, 'patient_id': chart.patient_id},
        message=f'Manual chart audit {chart.id} created for patient {chart.patient_id or chart.id}.',
    )
    return _chart_detail(chart)


@router.get('/charts/{chart_id}', response_model=ChartDetailOut)
def get_chart(chart_id: int, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    chart = _find_chart(chart_id, user, db)
    log_event(
        db,
        request,
        'chart.read',
        actor=user,
        event_category='data_access',
        target_entity=f'chart:{chart.id}',
        target_entity_type='chart',
        target_entity_id=str(chart.id),
        patient_id=chart.patient_id,
        details={'state': chart.state.value},
        message=f'Chart audit {chart.id} viewed by {user.username}.',
    )
    return _chart_detail(chart)


@router.put('/charts/{chart_id}', response_model=ChartDetailOut)
def update_chart(chart_id: int, payload: ChartUpdate, request: Request, user: User = Depends(require_roles(*REVIEW_ROLES)), db: Session = Depends(get_db)):
    chart = _find_chart(chart_id, user, db)
    _apply_chart_updates(chart, payload)
    if chart.source_note_set_id:
        chart.state = WorkflowState.awaiting_manager_review
        chart.reviewed_by_id = None
        chart.reviewed_at = None
        chart.manager_comment = ''
    _sync_chart_display_name_to_timeliness(db, chart)
    db.commit()
    chart = _find_chart(chart_id, user, db)
    log_event(
        db,
        request,
        'chart.update',
        actor=user,
        event_category='workflow',
        target_entity=f'chart:{chart.id}',
        target_entity_type='chart',
        target_entity_id=str(chart.id),
        patient_id=chart.patient_id,
        details={'state': chart.state.value, 'patient_id': chart.patient_id},
        message=f'Chart audit {chart.id} updated by {user.username}.',
    )
    return _chart_detail(chart)


@router.post('/charts/{chart_id}/reanalyze', response_model=ChartDetailOut)
def reanalyze_chart(chart_id: int, request: Request, user: User = Depends(require_roles(*REVIEW_ROLES)), db: Session = Depends(get_db)):
    chart = _find_chart(chart_id, user, db)
    if chart.source_note_set_id is None:
        raise HTTPException(status_code=400, detail='This chart is not linked to an uploaded binder, so there is no source document set to re-run.')

    note_set = _find_note_set(chart.source_note_set_id, user, db)
    app_settings = get_or_create_app_settings(db)
    timeliness_client = sync_from_note_set(db, note_set)
    if chart.client_name.strip():
        timeliness_client.permitted_name = chart.client_name.strip()
    report = generate_evaluation_report(note_set, app_settings=app_settings)
    old_state = chart.state
    apply_report_to_chart(chart, report)
    chart.client_name = chart.client_name.strip() or note_set.patient_id
    chart.level_of_care = note_set.level_of_care
    chart.admission_date = note_set.admission_date
    chart.discharge_date = note_set.discharge_date
    chart.primary_clinician = note_set.primary_clinician
    chart.state = WorkflowState.awaiting_manager_review
    chart.reviewed_by_id = None
    chart.reviewed_at = None
    chart.manager_comment = ''
    db.add(
        WorkflowTransition(
            chart_id=chart.id,
            actor_id=user.id,
            from_state=old_state.value,
            to_state=WorkflowState.awaiting_manager_review.value,
            comment='Deterministic analysis re-run from the linked uploaded binder.',
        )
    )
    db.commit()
    chart = _find_chart(chart_id, user, db)
    log_event(
        db,
        request,
        'chart.reanalyze',
        actor=user,
        event_category='workflow',
        target_entity=f'chart:{chart.id}',
        target_entity_type='chart',
        target_entity_id=str(chart.id),
        patient_id=chart.patient_id,
        details={'source_note_set_id': note_set.id, 'system_score': chart.system_score, 'state': chart.state.value},
        message=f'Chart audit {chart.id} re-analyzed from linked uploaded binder.',
    )
    return _chart_detail(chart)


@router.post('/charts/{chart_id}/transition', response_model=ChartDetailOut)
def transition_chart(chart_id: int, payload: TransitionInput, request: Request, user: User = Depends(require_roles(*REVIEW_ROLES)), db: Session = Depends(get_db)):
    chart = _find_chart(chart_id, user, db)
    if not _allowed_transition(user.role, chart.state, payload.to_state):
        raise HTTPException(status_code=400, detail='Invalid transition for role/state')
    if payload.to_state == WorkflowState.manager_rejected and not payload.comment.strip():
        raise HTTPException(status_code=400, detail='Comment required when returning a chart to the counselor')

    old = chart.state
    chart.state = payload.to_state
    chart.manager_comment = payload.comment.strip()
    chart.reviewed_by_id = user.id
    chart.reviewed_at = _utc_now()

    if payload.to_state == WorkflowState.awaiting_manager_review:
        chart.manager_comment = ''
        chart.reviewed_by_id = None
        chart.reviewed_at = None

    db.add(
        WorkflowTransition(
            chart_id=chart.id,
            actor_id=user.id,
            from_state=old.value,
            to_state=payload.to_state.value,
            comment=payload.comment.strip(),
        )
    )
    db.commit()
    chart = _find_chart(chart_id, user, db)
    log_event(
        db,
        request,
        'chart.transition',
        actor=user,
        event_category='workflow',
        target_entity=f'chart:{chart.id}',
        target_entity_type='chart',
        target_entity_id=str(chart.id),
        patient_id=chart.patient_id,
        details={'from': old.value, 'to': payload.to_state.value, 'comment': payload.comment.strip()},
        message=f'Chart audit {chart.id} transitioned from {old.value} to {payload.to_state.value}.',
    )
    return _chart_detail(chart)


@router.get('/patient-note-sets', response_model=list[PatientNoteSetSummaryOut])
def list_patient_note_sets(
    request: Request,
    patient_id: str | None = Query(default=None),
    user: User = Depends(require_roles(*NOTE_SET_ROLES)),
    db: Session = Depends(get_db),
):
    stmt = _note_set_stmt().order_by(PatientNoteSet.created_at.desc(), PatientNoteSet.id.desc())
    if user.role == Role.counselor:
        stmt = stmt.where(PatientNoteSet.uploaded_by_id == user.id)
    if patient_id and patient_id.strip():
        stmt = stmt.where(PatientNoteSet.patient_id == patient_id.strip())
    note_sets = list(db.execute(stmt).scalars().unique().all())
    log_event(
        db,
        request,
        'patient_note_sets.list.read',
        actor=user,
        event_category='data_access',
        target_entity='patient_note_sets',
        target_entity_type='patient_note_set',
        patient_id=patient_id.strip() if patient_id and patient_id.strip() else None,
        details={'count': len(note_sets), 'patient_id': patient_id.strip() if patient_id and patient_id.strip() else None},
        message=f'Patient note set queue viewed by {user.username}.',
    )
    return [_note_set_summary(note_set) for note_set in note_sets]


@router.get('/patient-note-sets/{note_set_id}', response_model=PatientNoteSetDetailOut)
def get_patient_note_set(note_set_id: int, request: Request, user: User = Depends(require_roles(*NOTE_SET_ROLES)), db: Session = Depends(get_db)):
    note_set = _find_note_set(note_set_id, user, db)
    log_event(
        db,
        request,
        'patient_note_set.read',
        actor=user,
        event_category='data_access',
        target_entity=f'patient_note_set:{note_set.id}',
        target_entity_type='patient_note_set',
        target_entity_id=str(note_set.id),
        patient_id=note_set.patient_id,
        details={'version': note_set.version, 'document_count': len(note_set.documents)},
        message=f'Patient note set {note_set.id} viewed by {user.username}.',
    )
    return _note_set_detail(note_set)


@router.post('/patient-note-sets/detect-patient-id', response_model=PatientIdDetectionOut)
async def detect_patient_id_for_uploads(
    request: Request,
    files: list[UploadFile] = File(...),
    user: User = Depends(require_roles(*NOTE_SET_ROLES)),
):
    if not files:
        raise HTTPException(status_code=400, detail='At least one clinical note file is required')
    _validate_upload_batch(files)

    detection = await detect_patient_id_from_uploads(files)
    action = 'patient_note_set.patient_id.detected' if detection.patient_id else 'patient_note_set.patient_id.not_detected'
    log_event(
        request=request,
        actor=user,
        action=action,
        event_category='file_activity',
        target_entity='patient_note_set_upload',
        target_entity_type='patient_note_set',
        patient_id=detection.patient_id,
        details={
            'file_count': len(files),
            'confidence': detection.confidence,
            'source_kind': detection.source_kind,
            'matched': bool(detection.match_text),
            'result': 'detected' if detection.patient_id else 'not_detected',
        },
        outcome_status='success' if detection.patient_id else 'failure',
        severity='info' if detection.patient_id else 'warning',
        message='Patient ID detection completed for uploaded clinical notes.',
        http_status_code=200,
    )
    return _patient_id_detection_payload(
        detection.patient_id,
        detection.confidence,
        detection.source_filename,
        detection.source_kind,
        detection.match_text,
        detection.reason,
    )


@router.post('/patient-note-sets', response_model=PatientNoteSetDetailOut)
async def upload_patient_note_set(
    request: Request,
    patient_id: str = Form(''),
    client_name: str = Form(''),
    upload_mode: NoteSetUploadMode = Form(NoteSetUploadMode.initial),
    level_of_care: str = Form(''),
    admission_date: str = Form(''),
    discharge_date: str = Form(''),
    primary_clinician: str = Form(''),
    upload_notes: str = Form(''),
    file_manifest: str = Form(''),
    files: list[UploadFile] = File(...),
    user: User = Depends(require_roles(*NOTE_SET_ROLES)),
    db: Session = Depends(get_db),
):
    if not files:
        raise HTTPException(status_code=400, detail='At least one clinical note file is required')
    _validate_upload_batch(files)

    normalized_patient_id = patient_id.strip()
    detection = await detect_patient_id_from_uploads(files) if not normalized_patient_id else None
    if not normalized_patient_id and detection and detection.patient_id:
        normalized_patient_id = detection.patient_id
        log_event(
            request=request,
            actor=user,
            action='patient_note_set.upload.patient_id_autofilled',
            event_category='file_activity',
            target_entity='patient_note_set_upload',
            target_entity_type='patient_note_set',
            patient_id=normalized_patient_id,
            details={
                'confidence': detection.confidence,
                'source_kind': detection.source_kind,
                'matched': bool(detection.match_text),
            },
            message='Patient ID was auto-filled from uploaded clinical notes during upload.',
            http_status_code=200,
        )
    if not normalized_patient_id:
        reason = detection.reason if detection is not None else 'Patient ID is required.'
        log_event(
            request=request,
            actor=user,
            action='patient_note_set.upload.patient_id_missing',
            event_category='file_activity',
            target_entity='patient_note_set_upload',
            target_entity_type='patient_note_set',
            details={'reason': reason, 'file_count': len(files)},
            outcome_status='failure',
            severity='warning',
            message='Patient note upload was blocked because no patient ID was supplied or detected.',
            http_status_code=400,
        )
        raise HTTPException(status_code=400, detail=f'Patient ID is required and could not be detected automatically. {reason}')

    extracted_metadata = await extract_upload_metadata_from_uploads(files)
    app_settings = get_or_create_app_settings(db)
    effective_local_now = localize_datetime(_utc_now(), app_settings.facility_timezone)
    resolved_primary_clinician = primary_clinician.strip() or extracted_metadata.primary_clinician
    resolved_level_of_care = level_of_care.strip() or extracted_metadata.level_of_care
    resolved_admission_date = admission_date.strip() or extracted_metadata.admission_date
    resolved_client_name = client_name.strip() or display_name_for_patient_name_status(
        extracted_metadata.patient_name_status,
        effective_local_now,
        patient_id=normalized_patient_id,
    )
    client_name_status_detail = (
        'Operator supplied a permitted display name.'
        if client_name.strip()
        else extracted_metadata.patient_name_message
    )

    manifest = _parse_manifest(file_manifest, files)
    existing_active = db.execute(
        _note_set_stmt().where(PatientNoteSet.patient_id == normalized_patient_id, PatientNoteSet.status == NoteSetStatus.active)
    ).scalar_one_or_none()
    if existing_active is not None:
        _ensure_note_set_access(existing_active, user)

    if upload_mode == NoteSetUploadMode.initial and existing_active:
        raise HTTPException(status_code=409, detail='A patient note set already exists for this patient ID; use update mode instead')
    if upload_mode == NoteSetUploadMode.update and not existing_active:
        raise HTTPException(status_code=404, detail='No active patient note set exists for this patient ID; use initial upload instead')

    next_version = (existing_active.version + 1) if existing_active else 1
    note_set = PatientNoteSet(
        patient_id=normalized_patient_id,
        version=next_version,
        status=NoteSetStatus.active,
        upload_mode=upload_mode,
        source_system='Alleva EMR',
        primary_clinician=resolved_primary_clinician.strip(),
        level_of_care=resolved_level_of_care.strip(),
        admission_date=resolved_admission_date.strip(),
        discharge_date=discharge_date.strip(),
        upload_notes=upload_notes.strip(),
        replaced_note_set_id=existing_active.id if existing_active else None,
        uploaded_by_id=user.id,
    )

    created_documents: list[PatientNoteDocument] = []
    stored_paths: list[str] = []
    stored_total_bytes = 0
    try:
        if existing_active:
            existing_active.status = NoteSetStatus.superseded
        db.add(note_set)
        db.flush()

        for metadata in manifest:
            document = PatientNoteDocument(
                note_set_id=note_set.id,
                document_label=metadata.document_label,
                original_filename=metadata.client_file_name,
                storage_path='',
                content_type='application/octet-stream',
                size_bytes=0,
                sha256='',
                alleva_bucket=metadata.alleva_bucket,
                document_type=metadata.document_type,
                completion_status=metadata.completion_status,
                client_signed=metadata.client_signed,
                staff_signed=metadata.staff_signed,
                document_date=metadata.document_date,
                description=metadata.description,
                source_document_id=metadata.source_document_id,
                source_attachment_url=metadata.source_attachment_url,
                source_author=metadata.source_author,
                source_custodian=metadata.source_custodian,
                source_security_label=metadata.source_security_label,
            )
            db.add(document)
            created_documents.append(document)

        db.flush()

        for upload, document in zip(files, created_documents):
            stored = await store_upload_file(upload, patient_id=normalized_patient_id, note_set_id=note_set.id, document_id=document.id)
            stored_paths.append(stored.storage_path)
            stored_total_bytes += stored.size_bytes
            if stored_total_bytes > settings.max_upload_total_bytes:
                limit_mb = settings.max_upload_total_bytes // (1024 * 1024)
                raise HTTPException(status_code=413, detail=f'Upload exceeds the {limit_mb}MB total binder limit')
            document.storage_path = stored.storage_path
            document.content_type = stored.content_type
            document.size_bytes = stored.size_bytes
            document.sha256 = stored.sha256

        chart = Chart(
            source_note_set_id=note_set.id,
            patient_id=normalized_patient_id,
            client_name=resolved_client_name,
            level_of_care=note_set.level_of_care,
            admission_date=note_set.admission_date,
            discharge_date=note_set.discharge_date,
            primary_clinician=note_set.primary_clinician,
            auditor_name=user.full_name or user.username,
            other_details=f'Auto-generated from uploaded clinical note binder. Patient display name status: {extracted_metadata.patient_name_status}. {client_name_status_detail}',
            counselor_id=user.id,
            notes=note_set.upload_notes,
            state=WorkflowState.draft,
        )
        db.add(chart)
        db.flush()

        note_set.documents[:] = created_documents
        timeliness_client = sync_from_note_set(db, note_set)
        if resolved_client_name:
            timeliness_client.permitted_name = resolved_client_name
        report = generate_evaluation_report(note_set, app_settings=app_settings)
        apply_report_to_chart(chart, report)
        chart.notes = note_set.upload_notes
        db.add(
            WorkflowTransition(
                chart_id=chart.id,
                actor_id=user.id,
                from_state=WorkflowState.draft.value,
                to_state=chart.state.value,
                comment='System evaluation generated automatically from uploaded clinical notes.',
            )
        )

        db.commit()
    except Exception as exc:
        db.rollback()
        remove_stored_paths(stored_paths)
        log_event(
            db,
            request,
            'patient_note_set.upload.failed',
            actor=user,
            event_category='file_activity',
            target_entity='patient_note_set',
            target_entity_type='patient_note_set',
            patient_id=normalized_patient_id,
            details={'file_count': len(files), 'reason': exc.__class__.__name__},
            outcome_status='failure',
            severity='error',
            message='Patient note upload failed.',
            http_status_code=500 if not isinstance(exc, HTTPException) else exc.status_code,
        )
        if isinstance(exc, HTTPException):
            raise
        raise

    note_set = _find_note_set(note_set.id, user, db)
    review_chart_id = _latest_review_chart_id(note_set)
    review_chart = _find_chart(review_chart_id, user, db) if review_chart_id is not None else None

    log_event(
        db,
        request,
        'patient_note_set.uploaded',
        actor=user,
        event_category='file_activity',
        target_entity=f'patient_note_set:{note_set.id}',
        target_entity_type='patient_note_set',
        target_entity_id=str(note_set.id),
        patient_id=note_set.patient_id,
        details={
            'version': note_set.version,
            'file_count': len(note_set.documents),
            'upload_mode': note_set.upload_mode.value,
            'metadata_extracted': {
                'primary_clinician': bool(extracted_metadata.primary_clinician),
                'level_of_care': bool(extracted_metadata.level_of_care),
                'admission_date': bool(extracted_metadata.admission_date),
                'patient_name_status': extracted_metadata.patient_name_status,
            },
        },
        message=f'Patient note set {note_set.id} uploaded.',
    )
    for document in note_set.documents:
        log_event(
            db,
            request,
            'patient_note.document.uploaded',
            actor=user,
            event_category='file_activity',
            target_entity=f'patient_note_document:{document.id}',
            target_entity_type='patient_note_document',
            target_entity_id=str(document.id),
            patient_id=note_set.patient_id,
            details={
                'note_set_id': note_set.id,
                'sha256': document.sha256,
                'size_bytes': document.size_bytes,
                'alleva_bucket': document.alleva_bucket.value,
            },
            message=f'Clinical note document {document.id} stored.',
        )
    if review_chart is not None:
        log_event(
            db,
            request,
            'chart.system_evaluated',
            actor=user,
            event_category='workflow',
            target_entity=f'chart:{review_chart.id}',
            target_entity_type='chart',
            target_entity_id=str(review_chart.id),
            patient_id=review_chart.patient_id,
            details={
                'source_note_set_id': note_set.id,
                'system_score': review_chart.system_score,
                'state': review_chart.state.value,
                'failed_items': _chart_summary(review_chart)['failed_items'],
                'pending_items': _chart_summary(review_chart)['pending_items'],
            },
            message=f'Automated evaluation completed for chart {review_chart.id}.',
        )
    return _note_set_detail(note_set)


@router.delete('/patient-note-sets/{note_set_id}')
def delete_patient_note_set(
    note_set_id: int,
    request: Request,
    user: User = Depends(require_roles(*NOTE_SET_ROLES)),
    db: Session = Depends(get_db),
):
    note_set = _find_note_set(note_set_id, user, db)
    patient_id = note_set.patient_id
    storage_paths = [document.storage_path for document in note_set.documents if document.storage_path]
    deleted_chart_ids = [chart.id for chart in note_set.review_charts]
    deleted_document_count = len(note_set.documents)
    was_active = note_set.status == NoteSetStatus.active
    replacement_note_set = (
        db.execute(
            _note_set_stmt()
            .where(PatientNoteSet.patient_id == patient_id, PatientNoteSet.id != note_set.id)
            .order_by(PatientNoteSet.version.desc(), PatientNoteSet.id.desc())
        )
        .scalars()
        .unique()
        .first()
    )
    timeliness_client = _timeliness_client_for_patient(patient_id, db)
    timeliness_only_from_deleted_note_set = bool(
        timeliness_client
        and timeliness_client.source_note_set_id == note_set.id
        and all(item.source_note_set_id == note_set.id for item in timeliness_client.level_of_care_history)
        and all(item.source_note_set_id == note_set.id for item in timeliness_client.treatment_plans)
    )

    try:
        if timeliness_client is not None:
            if timeliness_only_from_deleted_note_set and not replacement_note_set:
                db.delete(timeliness_client)
            else:
                db.execute(delete(LevelOfCareHistory).where(LevelOfCareHistory.source_note_set_id == note_set.id))
                db.execute(delete(TreatmentPlanRecord).where(TreatmentPlanRecord.source_note_set_id == note_set.id))
                if timeliness_client.source_note_set_id == note_set.id:
                    timeliness_client.source_note_set_id = None
                    timeliness_client.source_evidence = ''
                    timeliness_client.last_imported_at = None
                    timeliness_client.updated_at = _utc_now()

        for chart in list(note_set.review_charts):
            db.execute(delete(WorkflowTransition).where(WorkflowTransition.chart_id == chart.id))
            db.delete(chart)

        if was_active and replacement_note_set is not None:
            replacement_note_set.status = NoteSetStatus.active
            sync_from_note_set(db, replacement_note_set)

        db.delete(note_set)
        db.flush()
        remove_stored_paths(storage_paths)
        reactivated_note_set_id = replacement_note_set.id if was_active and replacement_note_set else None
        db.commit()
    except Exception as exc:
        db.rollback()
        log_event(
            db,
            request,
            'patient_note_set.delete.failed',
            actor=user,
            event_category='file_activity',
            target_entity=f'patient_note_set:{note_set_id}',
            target_entity_type='patient_note_set',
            target_entity_id=str(note_set_id),
            patient_id=patient_id,
            details={'reason': exc.__class__.__name__},
            outcome_status='failure',
            severity='error',
            message=f'Patient note set {note_set_id} deletion failed.',
            http_status_code=500,
        )
        raise

    log_event(
        db,
        request,
        'patient_note_set.deleted',
        actor=user,
        event_category='file_activity',
        target_entity=f'patient_note_set:{note_set_id}',
        target_entity_type='patient_note_set',
        target_entity_id=str(note_set_id),
        patient_id=patient_id,
        details={
            'deleted_document_count': deleted_document_count,
            'deleted_chart_ids': deleted_chart_ids,
            'deleted_storage_file_count': len(storage_paths),
            'reactivated_note_set_id': reactivated_note_set_id,
        },
        message=f'Patient note set {note_set_id} and linked review data were deleted.',
    )
    return {
        'status': 'deleted',
        'deleted_note_set_id': note_set_id,
        'deleted_review_chart_ids': deleted_chart_ids,
        'deleted_document_count': deleted_document_count,
        'reactivated_note_set_id': reactivated_note_set_id,
    }


@router.get('/patient-note-sets/{note_set_id}/documents/{document_id}/download')
def download_patient_note_document(
    note_set_id: int,
    document_id: int,
    request: Request,
    user: User = Depends(require_roles(*NOTE_SET_ROLES)),
    db: Session = Depends(get_db),
):
    note_set = _find_note_set(note_set_id, user, db)
    document = next((item for item in note_set.documents if item.id == document_id), None)
    if not document:
        raise HTTPException(status_code=404, detail='Patient note document not found')

    file_path = resolve_storage_path(document.storage_path)
    decrypted_content = read_secure_file(file_path)

    log_event(
        db,
        request,
        'patient_note.document.download',
        actor=user,
        event_category='data_access',
        target_entity=f'patient_note_document:{document.id}',
        target_entity_type='patient_note_document',
        target_entity_id=str(document.id),
        patient_id=note_set.patient_id,
        details={'note_set_id': note_set.id, 'size_bytes': document.size_bytes, 'sha256': document.sha256},
        message=f'Clinical note document {document.id} downloaded by {user.username}.',
    )
    safe_download_name = (Path(document.original_filename).name or 'clinical-note').replace('"', '')
    return Response(
        content=decrypted_content,
        media_type=document.content_type,
        headers={'Content-Disposition': f'attachment; filename="{safe_download_name}"'},
    )


@router.get('/audit/logs', response_model=list[AuditLogOut])
def audit_logs(
    request: Request,
    limit: int = Query(default=200, ge=1, le=2000),
    action: str | None = Query(default=None),
    event_category: str | None = Query(default=None),
    patient_id: str | None = Query(default=None),
    actor_username: str | None = Query(default=None),
    request_id: str | None = Query(default=None),
    user: User = Depends(require_roles(Role.admin)),
    db: Session = Depends(get_db),
):
    stmt = select(AuditLog).order_by(AuditLog.id.desc()).limit(limit)
    if action and action.strip():
        stmt = stmt.where(AuditLog.action == action.strip())
    if event_category and event_category.strip():
        stmt = stmt.where(AuditLog.event_category == event_category.strip())
    if patient_id and patient_id.strip():
        stmt = stmt.where(AuditLog.patient_id == patient_id.strip())
    if actor_username and actor_username.strip():
        stmt = stmt.where(AuditLog.actor_username == actor_username.strip())
    if request_id and request_id.strip():
        stmt = stmt.where(AuditLog.request_id == request_id.strip())

    logs = list(db.execute(stmt).scalars().all())
    settings_row = get_or_create_app_settings(db)
    log_event(
        db,
        request,
        'audit.logs.read',
        actor=user,
        event_category='forensic_access',
        target_entity='audit_logs',
        target_entity_type='audit_log',
        details={
            'count': len(logs),
            'limit': limit,
            'action': action.strip() if action and action.strip() else None,
            'event_category': event_category.strip() if event_category and event_category.strip() else None,
            'patient_id': patient_id.strip() if patient_id and patient_id.strip() else None,
            'actor_username': actor_username.strip() if actor_username and actor_username.strip() else None,
            'request_id': request_id.strip() if request_id and request_id.strip() else None,
        },
        message='Forensic audit log list viewed.',
    )
    return [_audit_log_payload(log, settings_row.facility_timezone) for log in logs]
