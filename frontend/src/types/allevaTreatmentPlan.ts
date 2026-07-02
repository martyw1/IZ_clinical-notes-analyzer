export type AllevaPatientStatusScope = 'active' | 'discharged' | 'other' | 'unknown'

export interface AllevaPatientStatus {
  readonly status_id: string
  readonly status_label: string
  readonly status_scope: AllevaPatientStatusScope
}

export interface AllevaPatientRecord extends AllevaPatientStatus {
  readonly patient_id: string
  readonly source_id: string
  readonly admission_date: string
  readonly planned_discharge_date: string
  readonly level_of_care: string
  readonly facility: string
  readonly primary_clinician: string
  readonly first_contact_date: string
}

export interface AllevaPatientPlanSyncWarning {
  readonly code: string
  readonly severity: 'low' | 'medium' | 'high'
  readonly source: '/clients' | '/treatment-plans' | '/treatment-reviews' | string
  readonly message: string
  readonly treatment_plan_id: string
}

export interface AllevaTreatmentReviewAvailability {
  readonly review_data_status: 'unavailable_via_rest_without_known_review_id'
  readonly next_review_due_source: 'unavailable'
  readonly message: string
}

export interface AllevaTreatmentPlanIntervention {
  readonly kind: 'intervention'
  readonly label: string
  readonly source_path: string
  readonly text_present: boolean
  readonly text?: string
  readonly redacted_text_sha256?: string
  readonly metadata?: Readonly<Record<string, string>>
}

export interface AllevaTreatmentPlanObjective {
  readonly kind: 'objective'
  readonly label: string
  readonly source_path: string
  readonly text_present: boolean
  readonly text?: string
  readonly redacted_text_sha256?: string
  readonly metadata?: Readonly<Record<string, string>>
  readonly interventions: readonly AllevaTreatmentPlanIntervention[]
}

export interface AllevaTreatmentPlanGoal {
  readonly kind: 'goal'
  readonly label: string
  readonly source_path: string
  readonly text_present: boolean
  readonly text?: string
  readonly redacted_text_sha256?: string
  readonly metadata?: Readonly<Record<string, string>>
  readonly objectives: readonly AllevaTreatmentPlanObjective[]
}

export interface AllevaTreatmentPlanDiagnosis {
  readonly kind: 'diagnosis'
  readonly label: string
  readonly source_path: string
  readonly text_present: boolean
  readonly text?: string
  readonly redacted_text_sha256?: string
  readonly metadata?: Readonly<Record<string, string>>
}

export interface AllevaTreatmentPlanBehavioralDefinition {
  readonly kind: 'behavioral_definition'
  readonly label: string
  readonly source_path: string
  readonly text_present: boolean
  readonly text?: string
  readonly redacted_text_sha256?: string
  readonly metadata?: Readonly<Record<string, string>>
}

export interface AllevaTreatmentPlanProblem {
  readonly kind: 'problem'
  readonly label: string
  readonly source_path: string
  readonly text_present: boolean
  readonly text?: string
  readonly redacted_text_sha256?: string
  readonly metadata?: Readonly<Record<string, string>>
  readonly diagnoses: readonly AllevaTreatmentPlanDiagnosis[]
  readonly behavioral_definitions: readonly AllevaTreatmentPlanBehavioralDefinition[]
  readonly goals: readonly AllevaTreatmentPlanGoal[]
}

export interface AllevaTreatmentPlanContentTree {
  readonly counts: Readonly<Record<string, number>>
  readonly plan_fields: readonly Readonly<Record<string, string | boolean | Readonly<Record<string, string>>>>[]
  readonly problems: readonly AllevaTreatmentPlanProblem[]
  readonly top_level_diagnoses: readonly AllevaTreatmentPlanDiagnosis[]
  readonly top_level_behavioral_definitions: readonly AllevaTreatmentPlanBehavioralDefinition[]
  readonly top_level_goals: readonly AllevaTreatmentPlanGoal[]
  readonly top_level_objectives: readonly AllevaTreatmentPlanObjective[]
  readonly top_level_interventions: readonly AllevaTreatmentPlanIntervention[]
  readonly unattached_items: readonly Readonly<Record<string, string | boolean | Readonly<Record<string, string>>>>[]
}

export interface AllevaTreatmentPlan {
  readonly treatment_plan_id: string
  readonly patient_id: string
  readonly raw_client_ref: string
  readonly extracted_patient_id: string
  readonly plan_client_id: string
  readonly join_validated: boolean
  readonly join_warning: string
  readonly endpoint_url: string
  readonly start_date: string
  readonly end_date: string
  readonly created_date: string
  readonly last_modified: string
  readonly is_active: boolean
  readonly is_complete: boolean
  readonly is_initial_tp: boolean
  readonly is_wiley: boolean
  readonly has_reason_for_admission: boolean
  readonly has_initial_client_needs: boolean
  readonly has_family_education_needs: boolean
  readonly plan_field_count: number
  readonly problem_count: number
  readonly diagnosis_count: number
  readonly active_diagnosis_count: number
  readonly behavioral_definition_count: number
  readonly goal_count: number
  readonly objective_count: number
  readonly intervention_count: number
  readonly content_tree: AllevaTreatmentPlanContentTree
  readonly content_value_status: string
  readonly missing_content_values: readonly string[]
  readonly warnings: readonly AllevaPatientPlanSyncWarning[]
}

export interface AllevaTreatmentPlanAggregate extends AllevaPatientStatus {
  readonly patient_id: string
  readonly patient: AllevaPatientRecord
  readonly total_plan_count: number
  readonly active_plan_count: number
  readonly has_multiple_active_plans: boolean
  readonly treatment_plan_ids: readonly string[]
  readonly active_treatment_plan_ids: readonly string[]
  readonly latest_created_active_plan_id: string
  readonly latest_created_active_plan: AllevaTreatmentPlan | null
  readonly treatment_plans: readonly AllevaTreatmentPlan[]
  readonly active_treatment_plans: readonly AllevaTreatmentPlan[]
  readonly review_data_status: AllevaTreatmentReviewAvailability['review_data_status']
  readonly next_review_due_source: AllevaTreatmentReviewAvailability['next_review_due_source']
  readonly review_availability: AllevaTreatmentReviewAvailability
  readonly warnings: readonly AllevaPatientPlanSyncWarning[]
}
