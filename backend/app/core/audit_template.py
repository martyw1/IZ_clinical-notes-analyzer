from __future__ import annotations

from collections import OrderedDict
from typing import TypedDict


class AuditTemplateItem(TypedDict):
    key: str
    step: int
    section: str
    label: str
    timeframe: str
    instructions: str
    evidence_hint: str
    policy_note: str | None


AUDIT_TEMPLATE: list[AuditTemplateItem] = [
    {
        'key': 'client_overview_episode_metadata',
        'step': 1,
        'section': 'Header Verification',
        'label': 'Client overview episode metadata',
        'timeframe': 'Audit setup',
        'instructions': 'Confirm client name, original admission date, original discharge date, and every level of care shown for the episode in Client Overview.',
        'evidence_hint': 'Record the tab or panel where the episode dates and levels of care were verified.',
        'policy_note': 'If level of care changes during treatment, keep the episode-level admission and discharge dates and note all levels of care used.',
    },
    {
        'key': 'client_overview_primary_clinician',
        'step': 2,
        'section': 'Header Verification',
        'label': 'Primary clinician assignment',
        'timeframe': 'Audit setup',
        'instructions': 'Confirm the primary clinician field is populated correctly in Client Overview before continuing the audit.',
        'evidence_hint': 'Capture where the clinician assignment was verified and note any mismatch.',
        'policy_note': 'The timing expectation for when a primary clinician must be assigned still needs an explicit SOP definition.',
    },
    {
        'key': 'intake_packet_initial',
        'step': 3,
        'section': 'Other / Admission Packet',
        'label': 'Intake Packet (Initial)',
        'timeframe': 'Completed at admission',
        'instructions': 'Confirm the intake packet exists in Document Manager, shows Completed status, and includes both client and staff signatures.',
        'evidence_hint': 'Record the form name, status, and client/staff signature dates.',
        'policy_note': 'Define exactly what “at admission” means operationally so every auditor grades timing the same way.',
    },
    {
        'key': 'client_rights_in_house',
        'step': 4,
        'section': 'Other / Admission Packet',
        'label': 'Client Rights in House (Initial)',
        'timeframe': 'Completed at admission',
        'instructions': 'Confirm the Client Rights in House form exists, is completed, and carries the required signatures.',
        'evidence_hint': 'Capture the document location and the completion or signature date.',
        'policy_note': 'Use the same admission timing rule applied to the rest of the initial packet.',
    },
    {
        'key': 'attendance_policy_consent',
        'step': 5,
        'section': 'Other / Admission Packet',
        'label': 'Attendance Policy Consent',
        'timeframe': 'Completed at admission',
        'instructions': 'Verify that exactly one Accept or Decline option is selected and the form is fully signed.',
        'evidence_hint': 'Note the selected option and whether both signatures are present.',
        'policy_note': None,
    },
    {
        'key': 'assurance_of_freedom_of_choice',
        'step': 6,
        'section': 'Other / Admission Packet',
        'label': 'Assurance of Freedom of Choice',
        'timeframe': 'Completed at admission',
        'instructions': 'Verify that exactly one Accept or Decline option is selected and the form is fully signed.',
        'evidence_hint': 'Record the document name, selected option, and the signature evidence.',
        'policy_note': None,
    },
    {
        'key': 'release_pattern_review',
        'step': 7,
        'section': 'Other / Admission Packet',
        'label': 'Release and consent completeness pattern',
        'timeframe': 'During intake packet review',
        'instructions': 'Across release and consent forms, verify that any Accept or Decline prompt has exactly one selection, “Other” has an explanation when checked, and physician fields are completed unless “No PCP” is explicitly checked.',
        'evidence_hint': 'List the form or page reviewed and the specific field pattern that passed or failed.',
        'policy_note': 'This is a repeated pattern across multiple forms and should be treated as one governing rule.',
    },
    {
        'key': 'emergency_contact_release',
        'step': 8,
        'section': 'Other / Admission Packet',
        'label': 'Emergency contact release / ROI',
        'timeframe': 'Completed at admission and re-signed at 1 year',
        'instructions': 'Confirm the emergency contact ROI exists, is complete, has client and staff signatures, includes appropriate disclosure selections, is still active, and was renewed when required.',
        'evidence_hint': 'Document where the ROI was found, the signature date, and the expiration or renewal date.',
        'policy_note': 'The one-year renewal rule needs a defined anchor date: signature date, effective date, or admission date.',
    },
    {
        'key': 'uds_labs',
        'step': 9,
        'section': 'Other / Admission Packet',
        'label': 'UDS / lab screening cadence',
        'timeframe': 'Roughly once per week at random',
        'instructions': 'Review the Lab tab dates and confirm the chart shows approximately weekly random testing evidence across the episode.',
        'evidence_hint': 'Record the lab dates reviewed and any gap that appears out of tolerance.',
        'policy_note': 'The allowed weekly tolerance window still needs an explicit rule for max gap and grace period.',
    },
    {
        'key': 'medication_list_accuracy',
        'step': 10,
        'section': 'Medication Review',
        'label': 'Medication list accuracy and classification',
        'timeframe': 'At time of audit',
        'instructions': 'If medications are listed, confirm the list is complete and each medication is marked as Home rather than Prescribed.',
        'evidence_hint': 'Record the medication reviewed and the medication type shown in the chart.',
        'policy_note': None,
    },
    {
        'key': 'medication_no_meds_evidence',
        'step': 11,
        'section': 'Medication Review',
        'label': 'No-meds compensating evidence',
        'timeframe': 'Only if the medication list is empty',
        'instructions': 'If no medications are listed, find explicit documentation elsewhere that medication reconciliation was completed and the client had no meds.',
        'evidence_hint': 'Record the alternate note location that proves “no meds” rather than missing documentation.',
        'policy_note': 'This is a compensating control because the EMR does not clearly distinguish “no meds” from “not documented.”',
    },
    {
        'key': 'biopsychosocial_assessment',
        'step': 12,
        'section': 'Biopsychosocial',
        'label': 'Biopsychosocial Assessment',
        'timeframe': 'Completed at admission and signed',
        'instructions': 'Confirm the biopsychosocial assessment is present, completed at admission, and signed.',
        'evidence_hint': 'Record the assessment location and the completion or signature date.',
        'policy_note': 'Use the same explicit admission-timing rule applied elsewhere in the audit.',
    },
    {
        'key': 'medical_history_physical',
        'step': 13,
        'section': 'Biopsychosocial',
        'label': 'Medical History and Physical',
        'timeframe': 'Within last 12 months or referral within 30 days',
        'instructions': 'Confirm there is either an H&P within the last 12 months or a referral within 30 days, including evidence found in biopsychosocial or case management notes when needed.',
        'evidence_hint': 'Record the H&P or referral source and the date used to satisfy the rule.',
        'policy_note': 'The “within 30 days” rule still needs an explicit anchor date, most likely admission.',
    },
    {
        'key': 'cssrs',
        'step': 14,
        'section': 'Biopsychosocial',
        'label': 'Columbia Suicide Severity Rating Scale',
        'timeframe': 'At the bottom of the biopsychosocial assessment',
        'instructions': 'Confirm the Columbia Suicide Severity Rating Scale is present in the chart package.',
        'evidence_hint': 'Record the assessment location and the date reviewed.',
        'policy_note': 'Decide whether the audit is presence-only or also requires documented follow-up for elevated risk findings.',
    },
    {
        'key': 'barc',
        'step': 15,
        'section': 'Biopsychosocial',
        'label': 'BARC',
        'timeframe': 'At admission',
        'instructions': 'Confirm the BARC instrument is present as part of the required biopsychosocial package.',
        'evidence_hint': 'Record the location and date of the instrument.',
        'policy_note': 'Decide whether high-severity findings require a documented clinical response.',
    },
    {
        'key': 'asam',
        'step': 16,
        'section': 'Biopsychosocial',
        'label': 'ASAM',
        'timeframe': 'At admission',
        'instructions': 'Confirm the ASAM assessment is present in the chart package.',
        'evidence_hint': 'Record the location and date of the ASAM evidence.',
        'policy_note': 'Decide whether elevated severity requires follow-up documentation in addition to instrument presence.',
    },
    {
        'key': 'gad',
        'step': 17,
        'section': 'Biopsychosocial',
        'label': 'GAD',
        'timeframe': 'At admission',
        'instructions': 'Confirm the GAD scale is present in the chart package.',
        'evidence_hint': 'Record the location and date of the GAD evidence.',
        'policy_note': 'Decide whether clinically significant scores require follow-up documentation.',
    },
    {
        'key': 'phq9',
        'step': 18,
        'section': 'Biopsychosocial',
        'label': 'PHQ-9',
        'timeframe': 'At admission',
        'instructions': 'Confirm the PHQ-9 is present in the chart package.',
        'evidence_hint': 'Record the location and date of the PHQ-9 evidence.',
        'policy_note': 'Decide whether clinically significant scores require follow-up documentation.',
    },
]

AUDIT_TEMPLATE_BY_KEY = OrderedDict((item['key'], item) for item in AUDIT_TEMPLATE)


def audit_sections() -> list[dict[str, object]]:
    sections: OrderedDict[str, list[AuditTemplateItem]] = OrderedDict()
    for item in AUDIT_TEMPLATE:
        sections.setdefault(item['section'], []).append(item)
    return [{'section': section, 'items': items} for section, items in sections.items()]
