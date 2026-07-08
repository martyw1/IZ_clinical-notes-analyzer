import type { CriterionResult } from '../types/treatmentPlan'

type EvidencePanelProps = {
  readonly criterion: CriterionResult
}

export function EvidencePanel({ criterion }: EvidencePanelProps) {
  return (
    <section className='evidence-panel' id={`evidence-${criterion.criterionId}`}>
      <h3>{criterion.title}</h3>
      <p>{criterion.finding}</p>
      <dl>
        <div>
          <dt>Source path</dt>
          <dd>{criterion.sourcePath}</dd>
        </div>
        <div>
          <dt>Safe preview</dt>
          <dd>{criterion.safePreview}</dd>
        </div>
      </dl>
    </section>
  )
}
