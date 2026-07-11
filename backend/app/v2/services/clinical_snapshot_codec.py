from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass
from typing import Annotated, Literal, assert_never

from cryptography.fernet import Fernet, InvalidToken
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from app.v2.domain.schemas import TreatmentPlanAggregate

type JsonPrimitive = str | int | float | bool | None
type JsonValue = JsonPrimitive | list[JsonValue] | dict[str, JsonValue]

CONTRACT = "izcna.clinical-snapshot.v1"
MAGIC = b"IZCNA1:"
TEXT_PREFIX = "enc:v1:"


class SnapshotModel(BaseModel):
    model_config = ConfigDict(frozen=True)


class PlanRecordSnapshot(SnapshotModel):
    contract: Literal["izcna.clinical-snapshot.v1"] = CONTRACT
    kind: Literal["plan_record"] = "plan_record"
    record: dict[str, JsonValue]


class ReviewRecordSnapshot(SnapshotModel):
    contract: Literal["izcna.clinical-snapshot.v1"] = CONTRACT
    kind: Literal["review_record"] = "review_record"
    record: dict[str, JsonValue]


class AggregateSnapshot(SnapshotModel):
    contract: Literal["izcna.clinical-snapshot.v1"] = CONTRACT
    kind: Literal["aggregate"] = "aggregate"
    aggregate: TreatmentPlanAggregate


type ClinicalSnapshot = Annotated[
    PlanRecordSnapshot | ReviewRecordSnapshot | AggregateSnapshot,
    Field(discriminator="kind"),
]
SNAPSHOT_ADAPTER = TypeAdapter(ClinicalSnapshot)


@dataclass(frozen=True, slots=True)
class SnapshotCodecError(Exception):
    reason: str

    def __str__(self) -> str:
        return f"clinical snapshot rejected: {self.reason}"


@dataclass(frozen=True, slots=True)
class ClinicalSnapshotCodec:
    encryption_secret: str

    def encode_plan(self, record: dict[str, JsonValue]) -> bytes:
        return self._encrypt(PlanRecordSnapshot(record=record))

    def encode_review(self, record: dict[str, JsonValue]) -> bytes:
        return self._encrypt(ReviewRecordSnapshot(record=record))

    def encode_aggregate(self, aggregate: TreatmentPlanAggregate) -> bytes:
        return self._encrypt(AggregateSnapshot(aggregate=aggregate))

    def decode_plan(self, stored: str | bytes) -> PlanRecordSnapshot | AggregateSnapshot:
        snapshot = self._decode(stored, "plan_record")
        match snapshot:
            case PlanRecordSnapshot() | AggregateSnapshot():
                return snapshot
            case ReviewRecordSnapshot():
                raise SnapshotCodecError("review snapshot found in plan-version storage")
            case unreachable:
                assert_never(unreachable)

    def decode_review(self, stored: str | bytes) -> ReviewRecordSnapshot:
        snapshot = self._decode(stored, "review_record")
        match snapshot:
            case ReviewRecordSnapshot():
                return snapshot
            case PlanRecordSnapshot() | AggregateSnapshot():
                raise SnapshotCodecError("plan snapshot found in review-version storage")
            case unreachable:
                assert_never(unreachable)

    def _encrypt(self, snapshot: ClinicalSnapshot) -> bytes:
        raw = SNAPSHOT_ADAPTER.dump_json(snapshot)
        return MAGIC + Fernet(_fernet_key(self.encryption_secret)).encrypt(raw)

    def _decode(self, stored: str | bytes, legacy_kind: Literal["plan_record", "review_record"]) -> ClinicalSnapshot:
        raw = _decrypt_payload(stored, self.encryption_secret)
        try:
            payload = json.loads(raw)
            if not isinstance(payload, dict):
                raise SnapshotCodecError("snapshot JSON root is not an object")
            if payload.get("contract") == CONTRACT:
                return SNAPSHOT_ADAPTER.validate_python(payload)
            return _legacy_snapshot(payload, legacy_kind)
        except (UnicodeDecodeError, json.JSONDecodeError, ValidationError) as exc:
            raise SnapshotCodecError("snapshot JSON does not match the typed contract") from exc


def _legacy_snapshot(
    payload: dict[str, JsonValue],
    legacy_kind: Literal["plan_record", "review_record"],
) -> ClinicalSnapshot:
    if "criteria_results" in payload and "content_snapshot" in payload:
        try:
            return AggregateSnapshot(aggregate=TreatmentPlanAggregate.model_validate(payload))
        except ValidationError as exc:
            raise SnapshotCodecError("legacy aggregate snapshot is malformed") from exc
    if legacy_kind == "plan_record":
        return PlanRecordSnapshot(record=payload)
    return ReviewRecordSnapshot(record=payload)


def _decrypt_payload(stored: str | bytes, secret: str) -> bytes:
    framed = stored.encode("utf-8") if isinstance(stored, str) else stored
    if framed.startswith(TEXT_PREFIX.encode("ascii")):
        try:
            framed = base64.urlsafe_b64decode(framed[len(TEXT_PREFIX) :])
        except ValueError as exc:
            raise SnapshotCodecError("text snapshot envelope is malformed") from exc
    if not framed.startswith(MAGIC):
        raise SnapshotCodecError("snapshot encryption envelope is missing")
    try:
        return Fernet(_fernet_key(secret)).decrypt(framed[len(MAGIC) :])
    except InvalidToken as exc:
        raise SnapshotCodecError("snapshot encryption token is invalid") from exc


def _fernet_key(secret: str) -> bytes:
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)
