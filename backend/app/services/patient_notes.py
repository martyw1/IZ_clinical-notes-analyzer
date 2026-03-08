from __future__ import annotations

import hashlib
import html
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path

from fastapi import HTTPException, UploadFile

try:
    from pypdf import PdfReader
except ImportError:  # pragma: no cover - exercised only in misconfigured runtime environments
    PdfReader = None

from app.core.config import settings

ALLOWED_EXTENSIONS = {'.csv', '.doc', '.docx', '.jpeg', '.jpg', '.pdf', '.png', '.rtf', '.txt', '.zip'}
MAX_FILE_BYTES = 50 * 1024 * 1024
CHUNK_SIZE = 1024 * 1024
SAFE_NAME_PATTERN = re.compile(r'[^A-Za-z0-9._-]+')


@dataclass(frozen=True)
class StoredUpload:
    storage_path: str
    sha256: str
    size_bytes: int
    content_type: str


@dataclass(frozen=True)
class ExtractedText:
    text: str
    status: str


def uploads_root() -> Path:
    root = settings.upload_dir_path.resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _safe_component(value: str, *, fallback: str) -> str:
    candidate = SAFE_NAME_PATTERN.sub('_', value.strip()).strip('._')
    return candidate or fallback


def sanitize_patient_id(patient_id: str) -> str:
    return _safe_component(patient_id, fallback='patient')


def sanitize_filename(filename: str) -> str:
    basename = Path(filename or '').name
    if not basename:
        basename = 'document'
    stem = _safe_component(Path(basename).stem, fallback='document')
    suffix = SAFE_NAME_PATTERN.sub('', Path(basename).suffix.lower())
    if suffix and suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f'Unsupported file type: {suffix}')
    if not suffix:
        raise HTTPException(status_code=400, detail='File extension is required for uploaded clinical notes')
    return f'{stem}{suffix}'


async def store_upload_file(upload: UploadFile, *, patient_id: str, note_set_id: int, document_id: int) -> StoredUpload:
    safe_patient_id = sanitize_patient_id(patient_id)
    safe_filename = sanitize_filename(upload.filename or '')

    relative_path = Path('patient-notes') / safe_patient_id / f'note-set-{note_set_id}' / f'{document_id}-{safe_filename}'
    final_path = uploads_root() / relative_path
    temp_path = final_path.with_suffix(final_path.suffix + '.tmp')
    final_path.parent.mkdir(parents=True, exist_ok=True)

    digest = hashlib.sha256()
    size_bytes = 0

    try:
        with temp_path.open('wb') as handle:
            while True:
                chunk = await upload.read(CHUNK_SIZE)
                if not chunk:
                    break
                size_bytes += len(chunk)
                if size_bytes > MAX_FILE_BYTES:
                    raise HTTPException(status_code=413, detail='Uploaded file exceeds the 50MB per-file limit')
                digest.update(chunk)
                handle.write(chunk)
        temp_path.replace(final_path)
    except Exception:
        if temp_path.exists():
            temp_path.unlink()
        raise
    finally:
        await upload.close()

    return StoredUpload(
        storage_path=str(relative_path),
        sha256=digest.hexdigest(),
        size_bytes=size_bytes,
        content_type=upload.content_type or 'application/octet-stream',
    )


def resolve_storage_path(storage_path: str) -> Path:
    root = uploads_root()
    candidate = (root / storage_path).resolve()
    if not str(candidate).startswith(str(root)):
        raise HTTPException(status_code=400, detail='Invalid stored file path')
    return candidate


def remove_stored_paths(storage_paths: list[str]) -> None:
    for storage_path in storage_paths:
        try:
            path = resolve_storage_path(storage_path)
        except HTTPException:
            continue
        if path.exists():
            path.unlink()


def _decode_bytes(raw: bytes) -> str:
    for encoding in ('utf-8', 'utf-16', 'latin-1'):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode('utf-8', errors='ignore')


def _strip_rtf(raw_text: str) -> str:
    without_controls = re.sub(r'\\[a-z]+\d* ?', ' ', raw_text)
    without_hex = re.sub(r"\\'[0-9a-fA-F]{2}", ' ', without_controls)
    without_braces = without_hex.replace('{', ' ').replace('}', ' ')
    return re.sub(r'\s+', ' ', without_braces).strip()


def _extract_docx_text(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        document_xml = archive.read('word/document.xml')
    text = _decode_bytes(document_xml)
    text = re.sub(r'</w:p>', '\n', text)
    text = re.sub(r'<[^>]+>', ' ', text)
    return re.sub(r'\s+', ' ', html.unescape(text)).strip()


def _extract_pdf_text(path: Path) -> str:
    if PdfReader is None:
        raise RuntimeError('pypdf is not installed')
    reader = PdfReader(str(path))
    pages = [page.extract_text() or '' for page in reader.pages]
    return '\n'.join(page for page in pages if page).strip()


def extract_text_from_storage(storage_path: str) -> ExtractedText:
    path = resolve_storage_path(storage_path)
    suffix = path.suffix.lower()

    try:
        if suffix in {'.txt', '.csv'}:
            return ExtractedText(text=_decode_bytes(path.read_bytes()).strip(), status='extracted')
        if suffix == '.rtf':
            return ExtractedText(text=_strip_rtf(_decode_bytes(path.read_bytes())), status='extracted')
        if suffix == '.docx':
            return ExtractedText(text=_extract_docx_text(path), status='extracted')
        if suffix == '.pdf':
            return ExtractedText(text=_extract_pdf_text(path), status='extracted')
        if suffix in {'.doc', '.jpg', '.jpeg', '.png', '.zip'}:
            return ExtractedText(text='', status='unsupported')
    except Exception:
        return ExtractedText(text='', status='failed')

    return ExtractedText(text='', status='unsupported')
