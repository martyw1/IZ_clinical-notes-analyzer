from __future__ import annotations

from dataclasses import dataclass
from typing import Final

SOURCE_KIND = "manual_treatment_plan_file"
SOURCE_DOWNLOAD_CONTENT_TYPES: Final = {
    "application/msword",
    "application/pdf",
    "application/rtf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/zip",
    "image/jpeg",
    "image/png",
    "text/plain",
    "text/csv",
    "text/tab-separated-values",
    "text/markdown",
}
SOURCE_EXTENSION_BY_FORMAT: Final = {
    "csv": "csv",
    "doc": "doc",
    "docx": "docx",
    "jpeg": "jpg",
    "pdf": "pdf",
    "png": "png",
    "rtf": "rtf",
    "markdown": "md",
    "text": "txt",
    "tsv": "tsv",
    "xlsx": "xlsx",
    "zip": "zip",
}


@dataclass(frozen=True, slots=True)
class ManualSourceFileArchiveInput:
    raw_bytes: bytes
    patient_id: str
    plan_id: str
    source_format: str
    content_type: str
    created_by_user_id: str
    plan_version_id: int | None = None
    patient_record_id: int | None = None


@dataclass(frozen=True, slots=True)
class ManualSourceFileDownload:
    raw_bytes: bytes
    media_type: str
    safe_filename: str
    source_format: str
    size_bytes: int


@dataclass(frozen=True, slots=True)
class ManualSourceFileDelete:
    source_file_id: str
    source_format: str
    size_bytes: int
    file_removed: bool


@dataclass(frozen=True, slots=True)
class StoredSourceDocument:
    document_id: str
    patient_id: str
    source_kind: str
    source_format: str
    content_type: str
    size_bytes: int
    sha256: str
    encrypted_relative_path: str
    created_at: str
    redaction_status: str = "encrypted_original_file"
