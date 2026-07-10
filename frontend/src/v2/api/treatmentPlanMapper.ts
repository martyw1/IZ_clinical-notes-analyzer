import type { TreatmentPlanAggregate, TreatmentPlanStatus } from '../types/treatmentPlan'
import { statusOrder } from '../types/treatmentPlan'
import type { JsonRecord } from './json'
import { readBoolean, readNumber, readRecord, readRecordList, readString, readStringList } from './json'
import type { TreatmentPlanListData, TreatmentPlanListItem } from './types'

const extraStatuses = ['Approved', 'Compliant', 'Not Applicable'] as const

export function toTreatmentPlanStatus(value: string): TreatmentPlanStatus {
  for (const status of statusOrder) {
    if (status === value) return status
  }
  for (const status of extraStatuses) {
    if (status === value) return status
  }
  return 'Unable to Evaluate'
}

function toSourceMode(value: string): TreatmentPlanAggregate['sourceMode'] {
  switch (value) {
    case 'manual_upload':
      return 'manual_upload'
    case 'alleva_rest_api':
      return 'alleva_rest_api'
    case 'synthetic_fixture':
      return 'synthetic_fixture'
    default:
      return 'unavailable'
  }
}

export function mapTreatmentPlanList(payload: JsonRecord): TreatmentPlanListData {
  return {
    items: readRecordList(payload, 'items').map(mapTreatmentPlanListItem),
    statusOrder: readStringList(payload, 'status_order').map(toTreatmentPlanStatus),
  }
}

function mapTreatmentPlanListItem(record: JsonRecord): TreatmentPlanListItem {
  return {
    patientId: readString(record, 'patient_id'),
    patientDisplayLabel: readString(record, 'patient_display_label', 'Patient ID unavailable'),
    currentLevelOfCare: readString(record, 'current_level_of_care', 'Unknown'),
    admissionDate: readString(record, 'admission_date', 'Unknown'),
    nextDueDate: readString(record, 'next_due_date', 'Unknown'),
    status: toTreatmentPlanStatus(readString(record, 'status')),
    missingCriteriaCount: readNumber(record, 'missing_criteria_count'),
    returnedCriteriaCount: readNumber(record, 'returned_criteria_count'),
    sourceMode: readString(record, 'source_mode', 'unknown'),
    warnings: readStringList(record, 'warnings'),
  }
}

export function mapTreatmentPlanAggregate(record: JsonRecord): TreatmentPlanAggregate {
  const snapshot = readRecord(record, 'content_snapshot')
  const coverage = readRecord(record, 'evidence_coverage_summary')
  return {
    patientId: readString(record, 'patient_id'),
    patientDisplayLabel: readString(record, 'patient_display_label', 'Patient ID unavailable'),
    currentLevelOfCare: readString(record, 'current_level_of_care', 'Unknown'),
    admissionDate: readString(record, 'admission_date', 'Unknown'),
    dueDate: readString(record, 'date_clock_due_date', readString(record, 'source_due_date', 'Unknown')),
    status: toTreatmentPlanStatus(readString(record, 'overall_status')),
    sourceMode: toSourceMode(readString(record, 'source_mode')),
    reasonForAdmission: readString(snapshot, 'reason_for_admission', 'No reason-for-admission text returned.'),
    initialClientNeeds: readString(snapshot, 'initial_client_needs', 'No initial-needs text returned.'),
    familyEducationNeeds: readString(snapshot, 'family_education_needs', 'No family-education text returned.'),
    contentSectionsPresent: readStringList(record, 'content_sections_present'),
    contentSectionsMissing: readStringList(record, 'content_sections_missing'),
    dataQualityWarnings: readStringList(record, 'data_quality_warnings'),
    criteria: readRecordList(record, 'criteria_results').map(mapCriterion),
    managerReviews: readRecordList(record, 'manager_reviews').map((review) => mapManagerReview(review)),
    overrides: readRecordList(record, 'overrides').map((review) => mapManagerReview(review, 'override', 'Override')),
    sourceDocuments: readRecordList(record, 'source_documents').map(mapSourceDocument),
    problems: readRecordList(snapshot, 'problems').map(mapProblem),
    signatures: readRecordList(snapshot, 'signatures').map((signature) => ({
      signatureType: readString(signature, 'signature_type'),
      signerRoleOrType: readString(signature, 'signer_role_or_type'),
      signatureDatetime: readString(signature, 'signature_datetime'),
      hasSignatureData: readBoolean(signature, 'has_signature_data'),
      signatureDataOmittedReason: readString(signature, 'signature_data_omitted_reason', 'signature data omitted'),
    })),
    observedFields: readRecordList(snapshot, 'observed_fields').map((field) => ({
      fieldPath: readString(field, 'field_path'),
      valueType: readString(field, 'value_type'),
      state: readString(field, 'state'),
      sampleRedactedValue: readString(field, 'sample_redacted_value'),
      usedByChecklist: readBoolean(field, 'used_by_checklist'),
    })),
    evidenceCoverageSummary: {
      criteriaTotal: readNumber(coverage, 'criteria_total', 42),
      criteriaWithEvidence: readNumber(coverage, 'criteria_with_evidence'),
      criteriaMissingEvidence: readNumber(coverage, 'criteria_missing_evidence'),
      runtimeOnlyFields: readStringList(coverage, 'runtime_only_fields'),
    },
  }
}

function mapManagerReview(record: JsonRecord, actionFallback = 'comment', statusFallback = 'Comment') {
  return {
    criterionId: readString(record, 'criterion_id'),
    action: readString(record, 'action', actionFallback),
    managerStatus: readString(record, 'manager_status', statusFallback),
    comment: readString(record, 'comment'),
    overrideReason: readString(record, 'override_reason'),
    actorUsername: readString(record, 'actor_username', 'unknown'),
    actorRole: readString(record, 'actor_role'),
    createdAt: readString(record, 'created_at'),
  }
}

function mapSourceDocument(record: JsonRecord) {
  return {
    sourceFileId: readString(record, 'source_file_id'),
    sourceKind: readString(record, 'source_kind'),
    sourceFormat: readString(record, 'source_format'),
    contentType: readString(record, 'content_type'),
    sizeBytes: readNumber(record, 'size_bytes'),
    sha256: readString(record, 'sha256'),
    redactionStatus: readString(record, 'redaction_status'),
    createdAt: readString(record, 'created_at'),
    downloadUrl: readString(record, 'download_url'),
  }
}

function mapCriterion(record: JsonRecord) {
  const evidence = readRecordList(record, 'evidence_refs')[0]
  const sourcePath = readStringList(record, 'source_json_paths')[0] ?? ''
  return {
    criterionId: readString(record, 'criterion_id'),
    title: readString(record, 'criterion_title', 'Untitled criterion'),
    status: toTreatmentPlanStatus(readString(record, 'result_status')),
    severity: toSeverity(readString(record, 'severity')),
    finding: readString(record, 'finding_message'),
    sourcePath,
    safePreview: evidence ? readString(evidence, 'safe_preview') : '',
    managerActionOptions: readStringList(record, 'manager_action_options'),
  }
}

function mapProblem(record: JsonRecord) {
  return {
    problemNumber: readString(record, 'problem_number'),
    description: readString(record, 'problem_description'),
    diagnoses: readRecordList(record, 'diagnoses').map((diagnosis) =>
      [readString(diagnosis, 'icd10_code'), readString(diagnosis, 'diagnosis_description')].filter(Boolean).join(' '),
    ),
    behavioralDefinitions: readRecordList(record, 'behavioral_definitions').map((definition) =>
      readString(definition, 'behavioral_definition', readString(definition, 'description')),
    ),
    goals: readRecordList(record, 'goals').map((goal) => ({
      goalNumber: readString(goal, 'goal_number'),
      description: readString(goal, 'goal_description'),
      objectives: readRecordList(goal, 'objectives').map((objective) => ({
        objectiveNumber: readString(objective, 'objective_number'),
        description: readString(objective, 'objective_description'),
        interventions: readRecordList(objective, 'interventions').map((intervention) =>
          readString(intervention, 'intervention_description'),
        ),
      })),
    })),
  }
}

function toSeverity(value: string): 'info' | 'medium' | 'high' {
  switch (value) {
    case 'high':
      return 'high'
    case 'medium':
      return 'medium'
    default:
      return 'info'
  }
}
