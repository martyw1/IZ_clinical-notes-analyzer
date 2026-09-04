from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class SeedModel(BaseModel):
    model_config = ConfigDict(frozen=True)


class UserRef(SeedModel):
    id: int
    username: str


class PlanRef(SeedModel):
    patient_id: str
    patient_record_id: int
    plan_id: str
    source_mode: str
    plan_version_id: int
    version_ordinal: int


class SeedFiles(SeedModel):
    aggregate: str
    binder: str


class FixtureContract(SeedModel):
    run_id: str
    physical_data_dir: str
    users: dict[str, UserRef]
    facilities: dict[str, int]
    patients: dict[str, int]
    plans: dict[str, PlanRef]
    files: SeedFiles
    schema_version: int
    integrity_ok: bool
    foreign_keys_ok: bool
    setup_surface: str = "offline synthetic fixture via real store and SQLite"
    live_import_enabled: bool = False


class OwnershipMarker(SeedModel):
    runId: str
    dataDir: str


class FailureFrame(SeedModel):
    file: str
    line: int
    function: str


class SeedFailure(SeedModel):
    error_type: str
    frames: tuple[FailureFrame, ...]
    values_omitted: bool = True
