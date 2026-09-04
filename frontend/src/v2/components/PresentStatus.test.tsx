import { render, screen } from '@testing-library/react'
import { expect, test, vi } from 'vitest'
import { mapTreatmentPlanAggregate } from '../api/treatmentPlanMapper'
import { TreatmentPlanDetailViewer } from './TreatmentPlanDetailViewer'

const present = ['confirm_admission_date', 'confirm_current_loc', 'confirm_loc_rule_mapping', 'confirm_staff_signature_status', 'initial_plan_exists', 'master_plan_exists', 'master_plan_required_signatures', 'latest_valid_review_identified']
const statuses = [...present.map((id) => [id, 'Present']), ...Array.from({ length: 19 }, (_, i) => [`review-${i}`, 'Needs Review']), ...Array.from({ length: 5 }, (_, i) => [`compliant-${i}`, 'Compliant']), ...Array.from({ length: 4 }, (_, i) => [`current-${i}`, 'Current/Compliant']), ...Array.from({ length: 6 }, (_, i) => [`na-${i}`, 'Not Applicable'])]
const payload = {
  patient_record_id: 31, plan_version_id: 91, source_mode: 'alleva_rest_api', treatment_plan_id: 'present-plan',
  content_snapshot: { plan_id: 'present-plan' }, overall_status: 'Needs Review',
  criteria_results: statuses.map(([id, status]) => ({ criterion_id: id, criterion_title: id, result_status: status })),
  evidence_coverage_summary: { criteria_total: 42, criteria_with_evidence: 14, criteria_missing_evidence: 0, criteria_conflicting: 0 },
}

test('preserves eight literal Present criteria without changing overall status', () => {
  const plan = mapTreatmentPlanAggregate(payload)
  expect(plan.criteria.filter((item) => item.status === 'Present').map((item) => item.criterionId)).toEqual(present)
  expect(plan.criteria.filter((item) => item.status === 'Unable to Evaluate')).toHaveLength(0)
  expect(plan.status).toBe('Needs Review')
})

test('renders full-fixture result counts independently of observed source support', () => {
  render(<TreatmentPlanDetailViewer plan={mapTreatmentPlanAggregate(payload)} canManage={false} onManagerAction={vi.fn()} onExportChecklistEvidence={vi.fn()} onDownloadSourceDocument={vi.fn()} onDeleteSourceDocument={vi.fn()} />)
  const counts = ['Checklist criteria total', 'Source support: observed evidence', 'Result status: Missing Data', 'Result status: Conflicting Evidence', 'Result status: Unable to Evaluate', 'Result status: Not Applicable'].map((label) => screen.getByText(label).nextElementSibling?.textContent)
  expect(counts).toEqual(['42', '14', '0', '0', '0', '6'])
  expect(screen.getByLabelText('Checklist criteria').querySelectorAll('.status-badge')).toHaveLength(42)
})
