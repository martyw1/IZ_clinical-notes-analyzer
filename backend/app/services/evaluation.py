from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone

from app.core.audit_template import AUDIT_TEMPLATE
from app.models.models import (
    AppSetting,
    AuditItemResponse,
    Chart,
    ComplianceStatus,
    DocumentCompletionStatus,
    PatientNoteDocument,
    PatientNoteSet,
    WorkflowState,
)
from app.services.llm_assist import call_llm_json
from app.services.patient_notes import extract_text_from_storage

DATE_FORMATS = ('%m/%d/%Y', '%m-%d-%Y', '%Y-%m-%d')
DATE_PATTERN = re.compile(r'\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b')


@dataclass(frozen=True)
class EvaluationDocument:
    document: PatientNoteDocument
    normalized_label: str
    normalized_description: str
    normalized_text: str
    extracted_status: str
    parsed_date: datetime | None


@dataclass(frozen=True)
class EvaluatedItem:
    item_key: str
    status: ComplianceStatus
    notes: str
    evidence_location: str
    evidence_date: str
    expiration_date: str


@dataclass(frozen=True)
class EvaluationReport:
    summary: str
    system_score: int
    state: WorkflowState
    items: list[EvaluatedItem]


def _parse_date(value: str) -> datetime | None:
    raw = (value or '').strip()
    if not raw:
        return None
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return None


def _normalize_text(value: str) -> str:
    return re.sub(r'\s+', ' ', value or '').strip().lower()


def _bucket_label(document: PatientNoteDocument) -> str:
    return document.alleva_bucket.value.replace('_', ' ')


def _document_location(document: PatientNoteDocument) -> str:
    return f'{document.document_label} ({_bucket_label(document)})'


def _document_is_complete(document: PatientNoteDocument, *, require_signatures: bool = True) -> bool:
    is_complete = document.completion_status == DocumentCompletionStatus.completed
    if not require_signatures:
        return is_complete
    return is_complete and document.client_signed and document.staff_signed


def _text_contains(document: EvaluationDocument, patterns: list[str]) -> bool:
    haystack = ' '.join([document.normalized_label, document.normalized_description, document.normalized_text])
    return any(pattern in haystack for pattern in patterns)


def _find_matching_documents(documents: list[EvaluationDocument], patterns: list[str]) -> list[EvaluationDocument]:
    return [document for document in documents if _text_contains(document, patterns)]


def _format_date(value: datetime | None, fallback: str = '') -> str:
    if value is None:
        return fallback
    return value.strftime('%m/%d/%Y')


def _extract_expiration(text: str) -> str:
    matches = DATE_PATTERN.findall(text)
    if len(matches) >= 2:
        return matches[-1]
    return ''


def _build_evaluation_documents(note_set: PatientNoteSet) -> list[EvaluationDocument]:
    evaluation_documents: list[EvaluationDocument] = []
    for document in note_set.documents:
        extracted = extract_text_from_storage(document.storage_path)
        evaluation_documents.append(
            EvaluationDocument(
                document=document,
                normalized_label=_normalize_text(document.document_label),
                normalized_description=_normalize_text(document.description),
                normalized_text=_normalize_text(extracted.text),
                extracted_status=extracted.status,
                parsed_date=_parse_date(document.document_date),
            )
        )
    return evaluation_documents


def _build_item(
    item_key: str,
    status: ComplianceStatus,
    notes: str,
    evidence_location: str = '',
    evidence_date: str = '',
    expiration_date: str = '',
) -> EvaluatedItem:
    return EvaluatedItem(
        item_key=item_key,
        status=status,
        notes=notes,
        evidence_location=evidence_location,
        evidence_date=evidence_date,
        expiration_date=expiration_date,
    )


def _evaluate_note_set(note_set: PatientNoteSet, documents: list[EvaluationDocument]) -> list[EvaluatedItem]:
    admission_date = _parse_date(note_set.admission_date)
    discharge_date = _parse_date(note_set.discharge_date)
    all_text = ' '.join(document.normalized_text for document in documents if document.normalized_text)

    items: list[EvaluatedItem] = []

    metadata_ready = bool(note_set.patient_id and note_set.admission_date and note_set.level_of_care)
    items.append(
        _build_item(
            'client_overview_episode_metadata',
            ComplianceStatus.yes if metadata_ready else ComplianceStatus.no,
            'Episode header fields are populated from the uploaded binder.' if metadata_ready else 'Missing patient ID, admission date, or level of care in the uploaded note set.',
            'System-generated from upload header',
            note_set.admission_date,
        )
    )

    clinician_ready = bool(note_set.primary_clinician.strip())
    items.append(
        _build_item(
            'client_overview_primary_clinician',
            ComplianceStatus.yes if clinician_ready else ComplianceStatus.no,
            'Primary clinician supplied with uploaded binder.' if clinician_ready else 'Primary clinician is missing from the uploaded note set.',
            'Upload header',
        )
    )

    def evaluate_required_document(item_key: str, patterns: list[str], requires_signatures: bool = True, extra_note: str = '') -> EvaluatedItem:
        matches = _find_matching_documents(documents, patterns)
        if not matches:
            return _build_item(item_key, ComplianceStatus.no, f'Missing required document matching {", ".join(patterns)}.')
        document = matches[0]
        if _document_is_complete(document.document, require_signatures=requires_signatures):
            note = f'Found {document.document.document_label}.'
            if extra_note:
                note = f'{note} {extra_note}'
            return _build_item(
                item_key,
                ComplianceStatus.yes,
                note,
                _document_location(document.document),
                document.document.document_date,
                _extract_expiration(document.normalized_text),
            )
        return _build_item(
            item_key,
            ComplianceStatus.no,
            f'{document.document.document_label} is present but incomplete or missing signatures.',
            _document_location(document.document),
            document.document.document_date,
        )

    items.append(evaluate_required_document('intake_packet_initial', ['intake packet']))
    items.append(evaluate_required_document('client_rights_in_house', ['client rights']))
    items.append(evaluate_required_document('attendance_policy_consent', ['attendance policy'], extra_note='Accept/Decline validation is inferred from completed status and signatures.'))
    items.append(evaluate_required_document('assurance_of_freedom_of_choice', ['freedom of choice'], extra_note='Accept/Decline validation is inferred from completed status and signatures.'))

    release_documents = [
        document
        for document in documents
        if _text_contains(
            document,
            ['release', 'consent', 'roi', 'attendance policy', 'freedom of choice', 'client rights', 'emergency contact'],
        )
    ]
    if not release_documents:
        items.append(_build_item('release_pattern_review', ComplianceStatus.no, 'No release or consent documents were found in the uploaded binder.'))
    elif any(document.document.completion_status != DocumentCompletionStatus.completed for document in release_documents):
        items.append(
            _build_item(
                'release_pattern_review',
                ComplianceStatus.no,
                'At least one release or consent document is marked incomplete.',
                ', '.join(_document_location(document.document) for document in release_documents[:3]),
            )
        )
    elif any(document.extracted_status == 'unsupported' for document in release_documents):
        items.append(
            _build_item(
                'release_pattern_review',
                ComplianceStatus.pending,
                'Release documents were found, but at least one file is not machine-readable enough to validate accept/decline and other-field rules automatically.',
                ', '.join(_document_location(document.document) for document in release_documents[:3]),
            )
        )
    else:
        items.append(
            _build_item(
                'release_pattern_review',
                ComplianceStatus.yes,
                'Release documents are present and machine-readable; no obvious completeness pattern failures were detected automatically.',
                ', '.join(_document_location(document.document) for document in release_documents[:3]),
            )
        )

    emergency_contact_documents = _find_matching_documents(documents, ['emergency contact', 'contacts', 'roi'])
    if not emergency_contact_documents:
        items.append(_build_item('emergency_contact_release', ComplianceStatus.no, 'Emergency contact ROI was not found in the uploaded binder.'))
    else:
        document = emergency_contact_documents[0]
        expiration = _extract_expiration(document.normalized_text)
        status = ComplianceStatus.yes if _document_is_complete(document.document) and expiration else ComplianceStatus.pending
        note = 'Emergency contact ROI found with signatures and machine-readable dates.' if status == ComplianceStatus.yes else 'Emergency contact ROI found, but automatic expiration validation could not be fully confirmed.'
        items.append(
            _build_item(
                'emergency_contact_release',
                status,
                note,
                _document_location(document.document),
                document.document.document_date,
                expiration,
            )
        )

    lab_documents = [
        document
        for document in documents
        if document.document.alleva_bucket.value == 'labs' or _text_contains(document, ['lab', 'uds', 'urine drug', 'drug screen', 'breathalyzer'])
    ]
    lab_dates = sorted(document.parsed_date for document in lab_documents if document.parsed_date)
    if not lab_documents:
        items.append(_build_item('uds_labs', ComplianceStatus.no, 'No lab or UDS evidence was found in the uploaded binder.'))
    elif not lab_dates:
        items.append(
            _build_item(
                'uds_labs',
                ComplianceStatus.pending,
                'Lab documents were found, but they do not have parseable dates for weekly cadence validation.',
                ', '.join(_document_location(document.document) for document in lab_documents[:3]),
            )
        )
    else:
        boundaries = list(lab_dates)
        if admission_date:
            boundaries.insert(0, admission_date)
        if discharge_date:
            boundaries.append(discharge_date)
        max_gap = max((later - earlier).days for earlier, later in zip(boundaries, boundaries[1:])) if len(boundaries) > 1 else 0
        status = ComplianceStatus.yes if max_gap <= 10 else ComplianceStatus.no
        items.append(
            _build_item(
                'uds_labs',
                status,
                f'Lab dates were detected with a maximum gap of {max_gap} day(s).',
                ', '.join(_document_location(document.document) for document in lab_documents[:3]),
                _format_date(lab_dates[0]),
            )
        )

    medication_documents = [
        document
        for document in documents
        if document.document.alleva_bucket.value == 'medications' or _text_contains(document, ['medication', 'rx', 'home meds', 'prescribed'])
    ]
    no_meds_detected = any(phrase in all_text for phrase in ['no meds', 'no medications', 'not on any medications', 'med rec completed no meds'])
    if not medication_documents:
        items.append(
            _build_item(
                'medication_list_accuracy',
                ComplianceStatus.no if not no_meds_detected else ComplianceStatus.na,
                'No medication list document was found.' if not no_meds_detected else 'Medication list is empty; no-meds evidence is being used instead.',
            )
        )
    else:
        medication_text = ' '.join(document.normalized_text for document in medication_documents)
        if 'prescribed' in medication_text and 'home med' not in medication_text:
            items.append(
                _build_item(
                    'medication_list_accuracy',
                    ComplianceStatus.no,
                    'Medication evidence includes "prescribed" without confirming Home meds classification.',
                    ', '.join(_document_location(document.document) for document in medication_documents[:3]),
                )
            )
        else:
            items.append(
                _build_item(
                    'medication_list_accuracy',
                    ComplianceStatus.yes,
                    'Medication evidence was found and no classification conflict was detected automatically.',
                    ', '.join(_document_location(document.document) for document in medication_documents[:3]),
                )
            )

    if medication_documents:
        items.append(_build_item('medication_no_meds_evidence', ComplianceStatus.na, 'Medication documents exist, so no-meds compensating evidence is not required.'))
    else:
        items.append(
            _build_item(
                'medication_no_meds_evidence',
                ComplianceStatus.yes if no_meds_detected else ComplianceStatus.no,
                'Explicit no-meds statement detected in the uploaded binder.' if no_meds_detected else 'No explicit no-meds statement was detected outside the medication list.',
            )
        )

    items.append(evaluate_required_document('biopsychosocial_assessment', ['biopsychosocial']))

    hp_documents = _find_matching_documents(documents, ['history and physical', 'h&p', 'medical history', 'referral'])
    hp_status = ComplianceStatus.no
    hp_note = 'Neither a current H&P nor a timely referral was detected.'
    hp_location = ''
    hp_date = ''
    for document in hp_documents:
        if not document.parsed_date or not admission_date:
            continue
        days_delta = (admission_date - document.parsed_date).days
        if 0 <= days_delta <= 365:
            hp_status = ComplianceStatus.yes
            hp_note = 'H&P or medical history evidence falls within the prior 12 months.'
            hp_location = _document_location(document.document)
            hp_date = document.document.document_date
            break
        referral_delta = (document.parsed_date - admission_date).days
        if 'referral' in document.normalized_label and 0 <= referral_delta <= 30:
            hp_status = ComplianceStatus.yes
            hp_note = 'Referral evidence falls within 30 days of admission.'
            hp_location = _document_location(document.document)
            hp_date = document.document.document_date
            break
    items.append(_build_item('medical_history_physical', hp_status, hp_note, hp_location, hp_date))

    def evaluate_instrument(item_key: str, patterns: list[str], label: str) -> EvaluatedItem:
        matches = _find_matching_documents(documents, patterns)
        if not matches:
            return _build_item(item_key, ComplianceStatus.no, f'{label} was not detected in the uploaded binder.')
        document = matches[0]
        return _build_item(item_key, ComplianceStatus.yes, f'{label} detected automatically.', _document_location(document.document), document.document.document_date)

    items.append(evaluate_instrument('cssrs', ['columbia suicide', 'cssrs', 'columbia suicide severity'], 'Columbia Suicide Severity Rating Scale'))
    items.append(evaluate_instrument('barc', ['barc'], 'BARC'))
    items.append(evaluate_instrument('asam', ['asam'], 'ASAM'))
    items.append(evaluate_instrument('gad', ['gad', 'gad-7', 'generalized anxiety'], 'GAD'))
    items.append(evaluate_instrument('phq9', ['phq-9', 'phq9', 'patient health questionnaire'], 'PHQ-9'))

    keyed_items = {item.item_key: item for item in items}
    return [keyed_items[template['key']] for template in AUDIT_TEMPLATE]


def _apply_llm_gap_analysis(
    note_set: PatientNoteSet,
    documents: list[EvaluationDocument],
    items: list[EvaluatedItem],
    app_settings: AppSetting | None,
) -> tuple[list[EvaluatedItem], str]:
    if (
        app_settings is None
        or not app_settings.llm_enabled
        or not app_settings.llm_use_for_evaluation_gap_analysis
        or not app_settings.llm_api_key.strip()
    ):
        return items, ''

    unresolved_items = [item for item in items if item.status == ComplianceStatus.pending]
    if not unresolved_items:
        return items, ''

    extracted_documents = [
        {
            'label': document.document.document_label,
            'date': document.document.document_date,
            'bucket': document.document.alleva_bucket.value,
            'text': document.normalized_text[:2500],
        }
        for document in documents
        if document.normalized_text
    ]
    payload = call_llm_json(
        app_settings,
        system_prompt=(
            'You are helping a clinical note audit application fill documentation-analysis gaps. '
            'Return strict JSON with keys "summary_addendum" and "item_updates". '
            'Each item update must include item_key and notes, and may include status, evidence_location, evidence_date, and expiration_date. '
            'Only reference evidence that is present in the supplied documents.'
        ),
        user_prompt=(
            f'Patient ID: {note_set.patient_id}\n'
            f'Admission date: {note_set.admission_date}\n'
            f'Primary clinician: {note_set.primary_clinician}\n'
            f'Unresolved items: {[{"item_key": item.item_key, "notes": item.notes} for item in unresolved_items]}\n'
            f'Documents: {extracted_documents}\n'
            f'Additional instructions: {app_settings.llm_analysis_instructions or "None"}'
        ),
        max_tokens=900,
        temperature=0,
    )
    if not payload:
        return items, ''

    updates = payload.get('item_updates')
    updates_by_key = {item.item_key: item for item in items}
    next_items: list[EvaluatedItem] = []
    for item in items:
        proposed = None
        if isinstance(updates, list):
            proposed = next((entry for entry in updates if isinstance(entry, dict) and entry.get('item_key') == item.item_key), None)
        if item.status != ComplianceStatus.pending or not isinstance(proposed, dict):
            next_items.append(item)
            continue

        proposed_status = proposed.get('status')
        next_status = item.status
        if proposed_status in {status.value for status in ComplianceStatus}:
            next_status = ComplianceStatus(proposed_status)

        llm_notes = str(proposed.get('notes') or '').strip()
        combined_notes = item.notes
        if llm_notes:
            combined_notes = f'{item.notes} LLM gap analysis: {llm_notes}'.strip()

        next_items.append(
            EvaluatedItem(
                item_key=item.item_key,
                status=next_status,
                notes=combined_notes,
                evidence_location=str(proposed.get('evidence_location') or item.evidence_location),
                evidence_date=str(proposed.get('evidence_date') or item.evidence_date),
                expiration_date=str(proposed.get('expiration_date') or item.expiration_date),
            )
        )

    summary_addendum = str(payload.get('summary_addendum') or '').strip()
    return next_items, summary_addendum


def generate_evaluation_report(note_set: PatientNoteSet, *, app_settings: AppSetting | None = None) -> EvaluationReport:
    documents = _build_evaluation_documents(note_set)
    items = _evaluate_note_set(note_set, documents)
    items, llm_summary_addendum = _apply_llm_gap_analysis(note_set, documents, items, app_settings)
    total = len(items) or 1
    passed = sum(1 for item in items if item.status == ComplianceStatus.yes)
    not_applicable = sum(1 for item in items if item.status == ComplianceStatus.na)
    failed = sum(1 for item in items if item.status == ComplianceStatus.no)
    pending = sum(1 for item in items if item.status == ComplianceStatus.pending)
    score = round(((passed + not_applicable) / total) * 100)
    summary = (
        f'System evaluation completed for patient {note_set.patient_id}. '
        f'{passed} item(s) passed, {failed} item(s) failed, {pending} item(s) need manual confirmation, '
        f'and the automated readiness score is {score}%.'
    )
    if llm_summary_addendum:
        summary = f'{summary} LLM gap analysis: {llm_summary_addendum}'
    return EvaluationReport(
        summary=summary,
        system_score=score,
        state=WorkflowState.awaiting_manager_review,
        items=items,
    )


def apply_report_to_chart(chart: Chart, report: EvaluationReport) -> None:
    chart.system_score = report.system_score
    chart.system_summary = report.summary
    chart.state = report.state
    chart.system_generated_at = datetime.now(timezone.utc)
    chart.manager_comment = ''
    existing = {response.item_key: response for response in chart.audit_responses}

    for evaluated_item in report.items:
        response = existing.get(evaluated_item.item_key)
        if not response:
            response = AuditItemResponse(item_key=evaluated_item.item_key)
            chart.audit_responses.append(response)
            existing[evaluated_item.item_key] = response
        response.status = evaluated_item.status
        response.notes = evaluated_item.notes
        response.evidence_location = evaluated_item.evidence_location
        response.evidence_date = evaluated_item.evidence_date
        response.expiration_date = evaluated_item.expiration_date
