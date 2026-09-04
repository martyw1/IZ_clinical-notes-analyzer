import type { CriterionResult } from '../types/treatmentPlan'

type EvidencePanelProps = {
  readonly criterion: CriterionResult
}

export function EvidencePanel({ criterion }: EvidencePanelProps) {
  const finding = displayEvidenceValue(criterion.finding)
  const sourcePath = displayEvidenceValue(criterion.sourcePath)
  const safePreview = displayEvidenceValue(criterion.safePreview)

  return (
    <section className='evidence-panel' id={`evidence-${criterion.criterionId}`}>
      <h3>{criterion.title}</h3>
      <p className='evidence-finding'>
        <strong>Finding</strong>
        <span>{finding}</span>
      </p>
      <dl>
        <div>
          <dt>Source path</dt>
          <dd>{sourcePath}</dd>
        </div>
        <div>
          <dt>Safe preview</dt>
          <dd>{safePreview}</dd>
        </div>
      </dl>
    </section>
  )
}

function displayEvidenceValue(value: string): string {
  return value.trim() || 'Not supplied'
}
