from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from typing import Any
from urllib.parse import parse_qsl, urlencode

REDACTED = '[redacted]'

PII_CANARIES = (
    'Jane Q Doe',
    'John Public',
    'Mary Patient',
    '123 Main Street',
    '456 Oak Ave',
    '789 Pine Road',
    'Springfield',
    'Charlotte',
    '90210',
    '28117',
)

PATIENT_CONTEXT_KEYS = {
    'address',
    'client',
    'contact',
    'lead',
    'mailingaddress',
    'member',
    'patient',
    'person',
    'profile',
    'recipient',
    'responsibleparty',
}

SAFE_ID_KEYS = {
    'clientid',
    'correlationid',
    'documentid',
    'eventid',
    'id',
    'leadid',
    'mrn',
    'patientid',
    'requestid',
    'sessionid',
    'sourceid',
    'sourcedocumentid',
    'sourcepatientresourceid',
    'targetentityid',
    'uniqueid',
}

PATIENT_NAME_KEYS = {
    'clientfullname',
    'clientlabel',
    'clientname',
    'displayname',
    'familyname',
    'firstname',
    'fullname',
    'givenname',
    'lastname',
    'leadfullname',
    'name',
    'patientfullname',
    'patientlabel',
    'patientname',
    'permittedname',
    'preferred',
    'preferredname',
    'sourceauthor',
    'sourcecustodian',
}

PATIENT_ADDRESS_KEYS = {
    'address',
    'address1',
    'address2',
    'addressline',
    'addressline1',
    'addressline2',
    'city',
    'country',
    'county',
    'homeaddress',
    'mailingaddress',
    'postalcode',
    'state',
    'street',
    'street1',
    'street2',
    'zip',
    'zipcode',
}

PATIENT_CONTACT_KEYS = {
    'birthdate',
    'dateofbirth',
    'dob',
    'email',
    'emailaddress',
    'mobile',
    'mobilephone',
    'phone',
    'phonenumber',
    'ssn',
    'socialsecurity',
    'socialsecuritynumber',
}

FILENAME_KEYS = {
    'clientfilename',
    'filename',
    'originalfilename',
    'sourcefilename',
}

SECRET_KEYS = {
    'accesskey',
    'accesstoken',
    'apikey',
    'authorization',
    'bearer',
    'clientsecret',
    'password',
    'refreshtoken',
    'secret',
    'token',
}

DIRECT_IDENTIFIER_LABEL_RE = re.compile(
    r'(?im)\b(?:patient|client|member|lead|person)\s+'
    r'(?:name|address|home\s+address|mailing\s+address|street|city|state|zip|zipcode|postal\s+code|phone|email|dob|date\s+of\s+birth|ssn)\s*:',
)
ADDRESS_LABEL_RE = re.compile(
    r'(?im)\b(?:home\s+address|mailing\s+address|patient\s+address|client\s+address|street|city\s*/\s*state\s*/\s*zip)\s*:',
)
DIRECT_IDENTIFIER_LINE_RE = re.compile(
    r'(?im)^([ \t]*(?:patient|client|member|lead|person)\s+'
    r'(?:name|address|home\s+address|mailing\s+address|street|city|state|zip|zipcode|postal\s+code|phone|email|dob|date\s+of\s+birth|ssn)\s*:\s*).*$',
)
FREEFORM_ADDRESS_LINE_RE = re.compile(
    r'(?im)^([ \t]*(?:home\s+address|mailing\s+address|patient\s+address|client\s+address|street|city\s*/\s*state\s*/\s*zip)\s*:\s*).*$',
)
TOKEN_REDACTION_RE = re.compile(
    r'(?i)\b(api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|password|authorization|secret|token|bearer)'
    r'(["\']?\s*[:=]\s*["\']?)[^"\',\s}]+',
)
BEARER_RE = re.compile(r'(?i)(bearer\s+)[A-Za-z0-9._~+/\-=]+')


def _normalize_key(value: Any) -> str:
    return re.sub(r'[^a-z0-9]+', '', str(value or '').lower())


def _path_has_patient_context(path: Sequence[str]) -> bool:
    return any(_normalize_key(part) in PATIENT_CONTEXT_KEYS for part in path)


def is_direct_patient_identifier_key(key: Any, path: Sequence[str] = (), *, aggressive: bool = False) -> bool:
    normalized = _normalize_key(key)
    if not normalized or normalized in SAFE_ID_KEYS:
        return False
    if normalized in FILENAME_KEYS:
        return True
    if normalized in PATIENT_NAME_KEYS:
        return aggressive or normalized != 'name' or _path_has_patient_context(path)
    if normalized in PATIENT_CONTACT_KEYS:
        return aggressive or _path_has_patient_context(path)
    if normalized in PATIENT_ADDRESS_KEYS:
        if normalized in {'city', 'state', 'county', 'country'}:
            return aggressive or _path_has_patient_context(path)
        return True
    return False


def is_sensitive_key(key: Any) -> bool:
    normalized = _normalize_key(key)
    return any(part in normalized for part in SECRET_KEYS)


def text_has_direct_patient_identifier_label(value: str) -> bool:
    return bool(DIRECT_IDENTIFIER_LABEL_RE.search(value or '') or ADDRESS_LABEL_RE.search(value or ''))


def redacted_text(value: str) -> str:
    text = str(value)
    text = BEARER_RE.sub(rf'\1{REDACTED}', text)
    text = TOKEN_REDACTION_RE.sub(rf'\1\2{REDACTED}', text)
    text = DIRECT_IDENTIFIER_LINE_RE.sub(rf'\1{REDACTED}', text)
    text = FREEFORM_ADDRESS_LINE_RE.sub(rf'\1{REDACTED}', text)
    for canary in PII_CANARIES:
        text = re.sub(re.escape(canary), REDACTED, text, flags=re.IGNORECASE)
    return text


def sanitize_patient_payload(value: Any, *, aggressive: bool = True, omit_direct: bool = True, _path: tuple[str, ...] = ()) -> Any:
    """Recursively drop or redact patient direct identifiers from imported payloads."""
    if isinstance(value, Mapping):
        sanitized: dict[str, Any] = {}
        for raw_key, item in value.items():
            key = str(raw_key)
            child_path = (*_path, key)
            if is_sensitive_key(key) or is_direct_patient_identifier_key(key, _path, aggressive=aggressive):
                if not omit_direct:
                    sanitized[key] = REDACTED
                continue
            sanitized[key] = sanitize_patient_payload(item, aggressive=aggressive, omit_direct=omit_direct, _path=child_path)
        return sanitized
    if isinstance(value, list):
        return [sanitize_patient_payload(item, aggressive=aggressive, omit_direct=omit_direct, _path=_path) for item in value]
    if isinstance(value, tuple):
        return tuple(sanitize_patient_payload(item, aggressive=aggressive, omit_direct=omit_direct, _path=_path) for item in value)
    if isinstance(value, str):
        return redacted_text(value)
    return value


def redact_for_audit(value: Any) -> Any:
    return sanitize_patient_payload(value, aggressive=False, omit_direct=False)


def redact_query_string(value: str | None) -> str | None:
    if not value:
        return None
    redacted_pairs: list[tuple[str, str]] = []
    for key, item in parse_qsl(value, keep_blank_values=True):
        if is_sensitive_key(key) or is_direct_patient_identifier_key(key, (), aggressive=True):
            redacted_pairs.append((key, REDACTED))
        else:
            redacted_pairs.append((key, redacted_text(item)))
    return urlencode(redacted_pairs, doseq=True)


def find_pii_canaries(value: Any) -> list[str]:
    try:
        text = json.dumps(value, default=str, sort_keys=True)
    except TypeError:
        text = str(value)
    lowered = text.lower()
    return sorted({canary for canary in PII_CANARIES if canary.lower() in lowered})


def assert_no_pii_canaries(value: Any) -> None:
    found = find_pii_canaries(value)
    if found:
        raise AssertionError(f'PII canary value(s) found: {", ".join(found)}')


def generated_document_filename(document_id: int, original_filename: str) -> str:
    match = re.search(r'(\.[A-Za-z0-9]{1,12})$', str(original_filename or ''))
    extension = match.group(1).lower() if match else '.bin'
    return f'document-{document_id}{extension}'


def generated_document_label(document_id: int) -> str:
    return f'Document {document_id}'
