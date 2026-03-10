from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.models import AppSetting, User


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def get_or_create_app_settings(db: Session) -> AppSetting:
    settings_row = db.execute(select(AppSetting).order_by(AppSetting.id.asc())).scalars().first()
    if settings_row is not None:
        return settings_row

    settings_row = AppSetting()
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
        'updated_by_id': settings_row.updated_by_id,
        'updated_at': settings_row.updated_at,
    }


def touch_app_settings(settings_row: AppSetting, *, actor: User | None = None) -> None:
    settings_row.updated_at = _utc_now()
    settings_row.updated_by_id = actor.id if actor is not None else None
