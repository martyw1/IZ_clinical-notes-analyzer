from __future__ import annotations

import base64
import hashlib
import json
import sqlite3
from dataclasses import dataclass

from cryptography.fernet import Fernet, InvalidToken

from app.v2.migrations.backfill_types import BackfillError, JsonPrimitive, JsonValue, encrypt_bytes, fernet_key, iso_text

PATIENT_NAME_ALIASES = frozenset(
    {"patientname", "clientname", "fullname", "displayname", "patientdisplaylabel", "firstname", "lastname", "givenname", "surname"}
)


@dataclass(frozen=True, slots=True)
class ImportBackfill:
    connection: sqlite3.Connection
    patient_id: int
    source_system: str
    imported_at: str
    encryption_secret: str


@dataclass(frozen=True, slots=True)
class VersionBackfill:
    connection: sqlite3.Connection
    facility_id: int
    encryption_secret: str
    plan_versions_by_patient: dict[int, list[tuple[int, str]]]


def backfill_import(context: VersionBackfill, legacy: tuple[JsonPrimitive, ...]) -> None:
    canonical_client_id = str(legacy[1]).strip()
    if not canonical_client_id:
        raise BackfillError("canonical client identifier is empty")
    source_system = str(legacy[3] or "legacy_v2")
    imported_at = iso_text(legacy[7])
    context.connection.execute(
        "INSERT OR IGNORE INTO patients(facility_id,canonical_client_id,source_system,lifecycle_state,first_seen_at,last_seen_at) VALUES(?,?,?,?,?,?)",
        (context.facility_id, canonical_client_id, source_system, "active", imported_at, imported_at),
    )
    patient_id = int(
        context.connection.execute(
            "SELECT id FROM patients WHERE facility_id=? AND source_system=? AND canonical_client_id=?",
            (context.facility_id, source_system, canonical_client_id),
        ).fetchone()[0]
    )
    payload = _decoded_json(str(legacy[6]), context.encryption_secret)
    plans = _record_list(payload.get("treatment_plans"))
    if not plans:
        snapshot = payload.get("content_snapshot")
        if isinstance(snapshot, dict):
            plans = [snapshot]
    import_context = ImportBackfill(context.connection, patient_id, source_system, imported_at, context.encryption_secret)
    context.plan_versions_by_patient[patient_id] = _backfill_plans(import_context, legacy, plans)
    _backfill_reviews(import_context, legacy, payload)


def _backfill_plans(
    context: ImportBackfill,
    legacy: tuple[JsonPrimitive, ...],
    plans: list[dict[str, JsonValue]],
) -> list[tuple[int, str]]:
    plan_links: list[tuple[int, str]] = []
    latest = context.connection.execute(
        "SELECT id,version_ordinal FROM treatment_plan_versions WHERE patient_id=? ORDER BY version_ordinal DESC,id DESC LIMIT 1",
        (context.patient_id,),
    ).fetchone()
    previous_plan_id = int(latest[0]) if latest else None
    first_ordinal = int(latest[1]) + 1 if latest else 1
    for ordinal, raw_plan in enumerate(plans, start=first_ordinal):
        plan = _scrub_record(raw_plan)
        source_record_id = _record_id(plan, str(legacy[2] or f"legacy-plan-{legacy[0]}"))
        canonical = _canonical_json(plan)
        content_sha256 = hashlib.sha256(canonical).hexdigest()
        evidence_sha256 = hashlib.sha256(f"{context.patient_id}:{context.source_system}:{source_record_id}:{content_sha256}".encode("utf-8")).hexdigest()
        cursor = context.connection.execute(
            """INSERT OR IGNORE INTO treatment_plan_versions(
                patient_id,source_system,source_record_id,version_ordinal,plan_date,signature_date,admission_date,
                source_next_review_due,normalized_snapshot_encrypted,content_sha256,evidence_sha256,imported_at,supersedes_version_id
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                context.patient_id, context.source_system, source_record_id, ordinal,
                _optional_text(plan.get("plan_date") or plan.get("planDate")),
                _optional_text(plan.get("signature_date") or plan.get("signatureDate")),
                _optional_text(legacy[4]), _optional_text(legacy[5]), encrypt_bytes(canonical, context.encryption_secret),
                content_sha256, evidence_sha256, context.imported_at, previous_plan_id,
            ),
        )
        if cursor.rowcount == 1:
            version_id = int(cursor.lastrowid)
        else:
            version_id = int(context.connection.execute(
                "SELECT id FROM treatment_plan_versions WHERE patient_id=? AND source_system=? AND source_record_id=? AND content_sha256=?",
                (context.patient_id, context.source_system, source_record_id, content_sha256),
            ).fetchone()[0])
        plan_links.append((version_id, source_record_id))
        previous_plan_id = version_id
        _backfill_diagnoses(context, plan, version_id)
    return plan_links


def _backfill_reviews(
    context: ImportBackfill,
    legacy: tuple[JsonPrimitive, ...],
    payload: dict[str, JsonValue],
) -> None:
    reviews = _record_list(payload.get("treatment_reviews") or payload.get("reviews"))
    latest = context.connection.execute(
        "SELECT id,version_ordinal FROM treatment_review_versions WHERE patient_id=? ORDER BY version_ordinal DESC,id DESC LIMIT 1",
        (context.patient_id,),
    ).fetchone()
    previous_review_id = int(latest[0]) if latest else None
    first_ordinal = int(latest[1]) + 1 if latest else 1
    for ordinal, raw_review in enumerate(reviews, start=first_ordinal):
        review = _scrub_record(raw_review)
        source_record_id = _record_id(review, f"legacy-review-{legacy[0]}-{ordinal}")
        canonical = _canonical_json(review)
        content_sha256 = hashlib.sha256(canonical).hexdigest()
        evidence_sha256 = hashlib.sha256(f"{context.patient_id}:{context.source_system}:{source_record_id}:{content_sha256}".encode("utf-8")).hexdigest()
        cursor = context.connection.execute(
            """INSERT OR IGNORE INTO treatment_review_versions(
                patient_id,source_system,source_record_id,version_ordinal,review_date,signature_date,
                normalized_snapshot_encrypted,content_sha256,evidence_sha256,imported_at,supersedes_version_id
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            (
                context.patient_id, context.source_system, source_record_id, ordinal,
                _optional_text(review.get("review_date") or review.get("reviewDate")),
                _optional_text(review.get("signature_date") or review.get("signatureDate")),
                encrypt_bytes(canonical, context.encryption_secret), content_sha256, evidence_sha256, context.imported_at, previous_review_id,
            ),
        )
        if cursor.rowcount == 1:
            previous_review_id = int(cursor.lastrowid)
        else:
            previous_review_id = int(context.connection.execute(
                "SELECT id FROM treatment_review_versions WHERE patient_id=? AND source_system=? AND source_record_id=? AND content_sha256=?",
                (context.patient_id, context.source_system, source_record_id, content_sha256),
            ).fetchone()[0])


def _backfill_diagnoses(
    context: ImportBackfill,
    plan: dict[str, JsonValue],
    version_id: int,
) -> None:
    for ordinal, raw_diagnosis in enumerate(_record_list(plan.get("diagnoses")), start=1):
        diagnosis = _scrub_record(raw_diagnosis)
        canonical = _canonical_json(diagnosis)
        content_sha256 = hashlib.sha256(canonical).hexdigest()
        context.connection.execute(
            "INSERT OR IGNORE INTO diagnosis_snapshots(plan_version_id,source_record_id,normalized_snapshot_encrypted,content_sha256,captured_at) VALUES(?,?,?,?,?)",
            (version_id, _record_id(diagnosis, f"diagnosis-{ordinal}"), encrypt_bytes(canonical, context.encryption_secret), content_sha256, context.imported_at),
        )


def _decoded_json(stored: str, secret: str) -> dict[str, JsonValue]:
    try:
        if stored.startswith("enc:v1:"):
            framed = base64.urlsafe_b64decode(stored[7:].encode("ascii"))
            if not framed.startswith(b"IZCNA1:"):
                raise BackfillError("legacy encrypted payload framing is invalid")
            stored_bytes = Fernet(fernet_key(secret)).decrypt(framed[7:])
        else:
            stored_bytes = stored.encode("utf-8")
        decoded = json.loads(stored_bytes)
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError, InvalidToken) as exc:
        raise BackfillError("legacy encrypted payload cannot be parsed") from exc
    if not isinstance(decoded, dict):
        raise BackfillError("legacy payload root is not an object")
    return decoded


def _canonical_json(value: dict[str, JsonValue]) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _record_list(value: JsonValue | None) -> list[dict[str, JsonValue]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _record_id(value: dict[str, JsonValue], fallback: str) -> str:
    for key in ("id", "plan_id", "planId", "review_id", "reviewId", "source_record_id"):
        candidate = value.get(key)
        if isinstance(candidate, (str, int)) and str(candidate).strip():
            return str(candidate).strip()
    return fallback


def _optional_text(value: JsonValue) -> str | None:
    if value is None or isinstance(value, (dict, list)):
        return None
    return str(value).strip() or None


def _scrub_record(value: dict[str, JsonValue]) -> dict[str, JsonValue]:
    return {
        key: _scrub_value(item)
        for key, item in value.items()
        if _normalized_key(key) not in PATIENT_NAME_ALIASES
    }


def _scrub_value(value: JsonValue) -> JsonValue:
    match value:
        case dict() as mapping:
            return _scrub_record(mapping)
        case list() as items:
            return [_scrub_value(item) for item in items]
        case None | bool() | int() | float() | str():
            return value


def _normalized_key(key: str) -> str:
    return "".join(character for character in key.casefold() if character.isalnum())
