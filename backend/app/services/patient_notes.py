from __future__ import annotations

import hashlib
import html
import io
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
DETECTION_MAX_FILE_BYTES = 8 * 1024 * 1024
SAFE_NAME_PATTERN = re.compile(r'[^A-Za-z0-9._-]+')
PATIENT_ID_LABEL_PATTERNS = (
    re.compile(r'\b(?:patient|client)\s*(?:id|identifier|number|no\.?|#)\s*[:#-]?\s*([A-Za-z0-9][A-Za-z0-9._/-]{2,31})', re.IGNORECASE),
    re.compile(r'\b(?:mrn|medical\s+record\s+number)\s*[:#-]?\s*([A-Za-z0-9][A-Za-z0-9._/-]{2,31})', re.IGNORECASE),
)
PATIENT_ID_TOKEN_PATTERNS = (
    re.compile(r'\b(PAT[-_ ]?[A-Za-z0-9]{2,24})\b', re.IGNORECASE),
    re.compile(r'\b(?:patient|client|mrn)[-_ ]?(?:id|number|no)?[-_ ]([A-Za-z0-9][A-Za-z0-9._-]{2,31})\b', re.IGNORECASE),
)
CONFIDENCE_RANK = {'none': 0, 'low': 1, 'medium': 2, 'high': 3}


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


@dataclass(frozen=True)
class PatientIdDetection:
    patient_id: str | None
    confidence: str
    source_filename: str | None
    source_kind: str | None
    match_text: str | None
    reason: str


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
    return _extract_docx_text_from_bytes(path.read_bytes())


def _extract_docx_text_from_bytes(raw: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        document_xml = archive.read('word/document.xml')
    text = _decode_bytes(document_xml)
    text = re.sub(r'</w:p>', '\n', text)
    text = re.sub(r'<[^>]+>', ' ', text)
    return re.sub(r'\s+', ' ', html.unescape(text)).strip()


def _extract_pdf_text(path: Path) -> str:
    return _extract_pdf_text_from_bytes(path.read_bytes())


def _extract_pdf_text_from_bytes(raw: bytes) -> str:
    if PdfReader is None:
        raise RuntimeError('pypdf is not installed')
    reader = PdfReader(io.BytesIO(raw))
    pages = [page.extract_text() or '' for page in reader.pages]
    return '\n'.join(page for page in pages if page).strip()


def _extract_text_from_bytes(raw: bytes, suffix: str) -> ExtractedText:
    try:
        if suffix in {'.txt', '.csv'}:
            return ExtractedText(text=_decode_bytes(raw).strip(), status='extracted')
        if suffix == '.rtf':
            return ExtractedText(text=_strip_rtf(_decode_bytes(raw)), status='extracted')
        if suffix == '.docx':
            return ExtractedText(text=_extract_docx_text_from_bytes(raw), status='extracted')
        if suffix == '.pdf':
            return ExtractedText(text=_extract_pdf_text_from_bytes(raw), status='extracted')
        if suffix in {'.doc', '.jpg', '.jpeg', '.png', '.zip'}:
            return ExtractedText(text='', status='unsupported')
    except Exception:
        return ExtractedText(text='', status='failed')

    return ExtractedText(text='', status='unsupported')


def extract_text_from_storage(storage_path: str) -> ExtractedText:
    path = resolve_storage_path(storage_path)
    return _extract_text_from_bytes(path.read_bytes(), path.suffix.lower())


def _normalize_detected_patient_id(value: str, *, allow_numeric: bool) -> str | None:
    candidate = value.strip().strip('.,;:()[]{}<>"\'')
    candidate = re.sub(r'\s+', '-', candidate)
    candidate = candidate.strip('-_/')
    if len(candidate) < 3 or len(candidate) > 32:
        return None
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._/-]{2,31}', candidate):
        return None
    if re.fullmatch(r'\d{1,2}[-/]\d{1,2}[-/]\d{2,4}', candidate):
        return None
    if not allow_numeric and not re.search(r'[A-Za-z]', candidate):
        return None
    return candidate


def _detect_patient_id_in_text(text: str, *, source_filename: str) -> PatientIdDetection | None:
    sample = text[:200_000]

    for pattern in PATIENT_ID_LABEL_PATTERNS:
        match = pattern.search(sample)
        if not match:
            continue
        candidate = _normalize_detected_patient_id(match.group(1), allow_numeric=True)
        if candidate:
            return PatientIdDetection(
                patient_id=candidate,
                confidence='high',
                source_filename=source_filename,
                source_kind='text_label',
                match_text=match.group(0),
                reason=f'Detected patient ID from labeled content in {source_filename}.',
            )

    for pattern in PATIENT_ID_TOKEN_PATTERNS:
        match = pattern.search(sample)
        if not match:
            continue
        candidate = _normalize_detected_patient_id(match.group(1), allow_numeric=False)
        if candidate:
            return PatientIdDetection(
                patient_id=candidate,
                confidence='medium',
                source_filename=source_filename,
                source_kind='text_token',
                match_text=match.group(0),
                reason=f'Detected patient ID token in {source_filename}.',
            )

    return None


def _detect_patient_id_in_filename(filename: str) -> PatientIdDetection | None:
    sample = Path(filename).stem.replace('.', ' ')

    for pattern in PATIENT_ID_LABEL_PATTERNS:
        match = pattern.search(sample)
        if not match:
            continue
        candidate = _normalize_detected_patient_id(match.group(1), allow_numeric=True)
        if candidate:
            return PatientIdDetection(
                patient_id=candidate,
                confidence='medium',
                source_filename=filename,
                source_kind='filename_label',
                match_text=match.group(0),
                reason=f'Detected patient ID from the filename {filename}.',
            )

    for pattern in PATIENT_ID_TOKEN_PATTERNS:
        match = pattern.search(sample)
        if not match:
            continue
        candidate = _normalize_detected_patient_id(match.group(1), allow_numeric=False)
        if candidate:
            return PatientIdDetection(
                patient_id=candidate,
                confidence='low',
                source_filename=filename,
                source_kind='filename_token',
                match_text=match.group(0),
                reason=f'Detected patient ID token from the filename {filename}.',
            )

    return None


async def _detect_patient_id_for_upload(upload: UploadFile) -> PatientIdDetection | None:
    filename = upload.filename or 'uploaded-file'
    suffix = Path(filename).suffix.lower()
    filename_detection = _detect_patient_id_in_filename(filename)

    if suffix not in ALLOWED_EXTENSIONS:
        return filename_detection

    raw = await upload.read(DETECTION_MAX_FILE_BYTES + 1)
    await upload.seek(0)
    if len(raw) > DETECTION_MAX_FILE_BYTES:
        return filename_detection

    extracted = _extract_text_from_bytes(raw, suffix)
    if extracted.text:
        text_detection = _detect_patient_id_in_text(extracted.text, source_filename=filename)
        if text_detection:
            return text_detection

    return filename_detection


async def detect_patient_id_from_uploads(files: list[UploadFile]) -> PatientIdDetection:
    matches: list[PatientIdDetection] = []
    for upload in files:
        detected = await _detect_patient_id_for_upload(upload)
        if detected and detected.patient_id:
            matches.append(detected)

    if not matches:
        return PatientIdDetection(
            patient_id=None,
            confidence='none',
            source_filename=None,
            source_kind=None,
            match_text=None,
            reason='No patient ID could be detected from the selected files.',
        )

    unique_ids = {match.patient_id for match in matches if match.patient_id}
    if len(unique_ids) > 1:
        return PatientIdDetection(
            patient_id=None,
            confidence='none',
            source_filename=None,
            source_kind='conflict',
            match_text=', '.join(sorted(unique_ids)),
            reason='Conflicting patient IDs were detected across the selected files.',
        )

    best = max(matches, key=lambda match: CONFIDENCE_RANK.get(match.confidence, 0))
    if len(matches) > 1:
        return PatientIdDetection(
            patient_id=best.patient_id,
            confidence=best.confidence,
            source_filename=best.source_filename,
            source_kind=best.source_kind,
            match_text=best.match_text,
            reason=f'Detected patient ID from {len(matches)} matching files.',
        )
    return best
