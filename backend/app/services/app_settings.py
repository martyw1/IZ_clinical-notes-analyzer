from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.models import AppSetting, User
from app.services.timezone import effective_timezone_label, normalize_timezone_name


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def get_or_create_app_settings(db: Session) -> AppSetting:
    settings_row = db.execute(select(AppSetting).order_by(AppSetting.id.asc())).scalars().first()
    if settings_row is not None:
        if settings_row.treatment_plan_loc_change_window_days is None:
            settings_row.treatment_plan_loc_change_window_days = 7
            db.commit()
            db.refresh(settings_row)
        return settings_row

    settings_row = AppSetting(treatment_plan_loc_change_window_days=7)
    db.add(settings_row)
    db.commit()
    db.refresh(settings_row)
    return settings_row


def app_settings_public_payload(settings_row: AppSetting) -> dict[str, object]:
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
        'alleva_treatment_plan_detail_fetch_enabled': settings_row.alleva_treatment_plan_detail_fetch_enabled,
        'alleva_treatment_plan_patient_name_import_enabled': settings_row.alleva_treatment_plan_patient_name_import_enabled,
        'alleva_treatment_plan_name_join_fallback_enabled': settings_row.alleva_treatment_plan_name_join_fallback_enabled,
        'alleva_treatment_plan_detail_fetch_limit': settings_row.alleva_treatment_plan_detail_fetch_limit,
        'alleva_treatment_plan_sync_last_at': settings_row.alleva_treatment_plan_sync_last_at,
        'alleva_treatment_plan_sync_last_status': settings_row.alleva_treatment_plan_sync_last_status,
        'alleva_treatment_plan_sync_last_message': settings_row.alleva_treatment_plan_sync_last_message,
        'alleva_treatment_plan_sync_last_success_at': settings_row.alleva_treatment_plan_sync_last_success_at,
        'alleva_treatment_plan_sync_last_failure_at': settings_row.alleva_treatment_plan_sync_last_failure_at,
        'facility_timezone': settings_row.facility_timezone,
        'effective_timezone': normalize_timezone_name(settings_row.facility_timezone),
        'effective_timezone_label': effective_timezone_label(settings_row.facility_timezone),
        'treatment_plan_loc_change_window_days': settings_row.treatment_plan_loc_change_window_days,
        'treatment_plan_loc_change_window_validated': settings_row.treatment_plan_loc_change_window_validated,
        'updated_by_id': settings_row.updated_by_id,
        'updated_at': settings_row.updated_at,
    }


def touch_app_settings(settings_row: AppSetting, *, actor: User | None = None) -> None:
    settings_row.updated_at = _utc_now()
    settings_row.updated_by_id = actor.id if actor is not None else None
