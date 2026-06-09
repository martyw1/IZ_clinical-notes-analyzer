from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.models import AppSetting, Chart, PatientNoteSet, TimelinessStatus, WorkflowState
from app.services.timeliness import evaluate_client, list_clients

REVIEW_STATUS_LABELS = {
    'not_reviewed': 'Not Reviewed',
    'ready_for_review': 'Ready for Review',
    'in_review': 'In Review',
    'needs_human_review': 'Needs Human Review',
    'passed': 'Passed',
    'failed': 'Failed',
    'missing_required_data': 'Missing Required Data',
    'error': 'Error',
    'finalized': 'Finalized',
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _status_counts(items: list[dict[str, Any]]) -> dict[str, int]:
    counts = {label: 0 for label in REVIEW_STATUS_LABELS.values()}
    for item in items:
        label = str(item.get('review_status') or '')
        counts[label] = counts.get(label, 0) + 1
    return counts


def _chart_status(chart: Chart | None) -> str:
    if chart is None:
        return REVIEW_STATUS_LABELS['ready_for_review']
    if chart.state == WorkflowState.awaiting_manager_review:
        return REVIEW_STATUS_LABELS['needs_human_review']
    if chart.state == WorkflowState.manager_approved:
        return REVIEW_STATUS_LABELS['finalized']
    if chart.state == WorkflowState.manager_rejected:
        return REVIEW_STATUS_LABELS['failed']
    if chart.state == WorkflowState.draft:
        return REVIEW_STATUS_LABELS['not_reviewed']
    return REVIEW_STATUS_LABELS['in_review']


def _timeliness_status(status: str) -> str:
    if status == TimelinessStatus.compliant.value:
        return REVIEW_STATUS_LABELS['passed']
    if status in {TimelinessStatus.overdue.value, TimelinessStatus.urgent.value}:
        return REVIEW_STATUS_LABELS['failed']
    if status == TimelinessStatus.missing_data.value:
        return REVIEW_STATUS_LABELS['missing_required_data']
    if status in {TimelinessStatus.due_soon.value, TimelinessStatus.needs_review.value}:
        return REVIEW_STATUS_LABELS['needs_human_review']
    return REVIEW_STATUS_LABELS['ready_for_review']


def _upload_items(note_sets: list[PatientNoteSet]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for note_set in note_sets:
        latest_chart = None
        if note_set.review_charts:
            latest_chart = max(note_set.review_charts, key=lambda chart: (chart.created_at, chart.id))
        items.append(
            {
                'source_type': 'upload',
                'source_item_id': f'note-set-{note_set.id}',
                'patient_id': note_set.patient_id,
                'display_name': f'Uploaded binder v{note_set.version}',
                'document_type': 'clinical_note_binder',
                'source_system_or_file': note_set.source_system,
                'review_status': _chart_status(latest_chart),
                'status_reason': 'Status is derived from the latest linked chart review.',
                'service_date': note_set.admission_date,
                'plan_date': '',
                'provider_staff': note_set.primary_clinician,
                'program_location': note_set.level_of_care,
                'last_changed_at': note_set.created_at.isoformat() if note_set.created_at else '',
                'review_chart_id': latest_chart.id if latest_chart else None,
            }
        )
    return items


def _api_items(db: Session, app_settings: AppSetting) -> list[dict[str, Any]]:
    clients = list_clients(db)
    items: list[dict[str, Any]] = []
    for client in clients:
        evaluation = evaluate_client(client, app_settings)
        items.append(
            {
                'source_type': 'api',
                'source_item_id': f'timeliness-client-{client.id}',
                'patient_id': client.patient_id,
                'display_name': client.permitted_name or client.patient_id,
                'document_type': 'treatment_plan',
                'source_system_or_file': app_settings.emr_vendor_name or 'Mock EMR/API source',
                'review_status': _timeliness_status(evaluation.status),
                'status_reason': evaluation.evidence_summary,
                'service_date': client.admission_date,
                'plan_date': evaluation.last_valid_review_date or '',
                'provider_staff': client.counselor_name,
                'program_location': client.current_level_of_care,
                'last_changed_at': client.updated_at.isoformat() if client.updated_at else '',
                'timeliness_client_id': client.id,
            }
        )

    if items:
        return items

    return [
        {
            'source_type': 'api',
            'source_item_id': 'mock-api-treatment-plan-001',
            'patient_id': 'SYNTH-API-001',
            'display_name': 'Synthetic API Treatment Plan',
            'document_type': 'treatment_plan',
            'source_system_or_file': app_settings.emr_vendor_name or 'Mock EMR/API source',
            'review_status': REVIEW_STATUS_LABELS['ready_for_review'],
            'status_reason': 'Synthetic mock item available because live EMR import is not approved.',
            'service_date': '2026-06-01',
            'plan_date': '2026-06-01',
            'provider_staff': 'Synthetic Provider',
            'program_location': 'IOP-5',
            'last_changed_at': _utc_now(),
            'timeliness_client_id': None,
        }
    ]


def discovery_payload(db: Session, app_settings: AppSetting, note_sets: list[PatientNoteSet]) -> dict[str, Any]:
    api_items = _api_items(db, app_settings)
    upload_items = _upload_items(note_sets)
    all_items = [*api_items, *upload_items]
    return {
        'checklist_id': 'treatment-plan-v1',
        'checklist_version': '1.0.0',
        'last_refreshed_at': _utc_now(),
        'live_import_enabled': False,
        'live_import_status': 'disabled_until_vendor_credentials_mapping_and_compliance_approval',
        'api_configured': bool(app_settings.emr_api_enabled and app_settings.emr_fhir_base_url and app_settings.emr_smart_client_id),
        'refresh_mode': 'mock_periodic_readiness',
        'status_counts': _status_counts(all_items),
        'items': all_items,
    }
