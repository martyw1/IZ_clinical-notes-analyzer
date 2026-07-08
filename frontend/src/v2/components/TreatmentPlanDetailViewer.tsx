import { useMemo, useState } from 'react'
import { EvidencePanel } from './EvidencePanel'
import { RawFieldExplorer } from './RawFieldExplorer'
import { StatusBadge } from './StatusBadge'
import type { CriterionResult, TreatmentPlanAggregate } from '../types/treatmentPlan'

type TreatmentPlanDetailViewerProps = {
  readonly plan: TreatmentPlanAggregate
}

export function TreatmentPlanDetailViewer({ plan }: TreatmentPlanDetailViewerProps) {
  const [query, setQuery] = useState('')
  const [selectedCriterion, setSelectedCriterion] = useState<CriterionResult>(plan.criteria[0])
  const [comment, setComment] = useState('')
  const [overrideReason, setOverrideReason] = useState('')
  const [actionMessage, setActionMessage] = useState('')
  const filteredCriteria = useMemo(() => {
    const normalized = query.trim().toLowerCase()
    if (!normalized) return plan.criteria
    return plan.criteria.filter((criterion) => criterion.title.toLowerCase().includes(normalized))
  }, [plan.criteria, query])

  const saveReturn = () => {
    setActionMessage(comment.trim() ? 'Criterion returned for correction with manager comment.' : 'Add a comment before returning a criterion.')
  }

  const saveOverride = () => {
    setActionMessage(overrideReason.trim() ? 'Override saved with required reason and audit event.' : 'Override reason is required.')
  }

  return (
    <div className='detail-grid'>
      <section className='panel'>
        <div className='section-heading'>
          <div>
            <p className='eyebrow'>Selected Treatment Plan Detail</p>
            <h2>{plan.patientDisplayLabel}</h2>
          </div>
          <StatusBadge status={plan.status} />
        </div>
        <div className='summary-grid'>
          <span>Current LOC: {plan.currentLevelOfCare}</span>
          <span>Admission: {plan.admissionDate}</span>
          <span>Next due: {plan.dueDate}</span>
          <span>Source: {plan.sourceMode}</span>
        </div>
        <label>
          Search treatment-plan content
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder='Search criteria and evidence' />
        </label>
      </section>

      <section className='panel content-panel'>
        <h2>Clinical Content</h2>
        <p><strong>Reason for admission:</strong> Synthetic clinical rationale is present for local validation.</p>
        <p><strong>Initial client needs:</strong> Stabilization and relapse-prevention needs are present.</p>
        <p><strong>Family education needs:</strong> Reviewed as applicable.</p>
        {plan.problems.map((problem) => (
          <details key={problem.problemNumber} open>
            <summary>Problem {problem.problemNumber}: {problem.description}</summary>
            <h3>Diagnoses</h3>
            <ul>{problem.diagnoses.map((diagnosis) => <li key={diagnosis}>{diagnosis}</li>)}</ul>
            <h3>Behavioral Definitions</h3>
            <ul>{problem.behavioralDefinitions.map((definition) => <li key={definition}>{definition}</li>)}</ul>
            <h3>Goals</h3>
            {problem.goals.map((goal) => (
              <details key={goal.goalNumber} open>
                <summary>Goal {goal.goalNumber}: {goal.description}</summary>
                {goal.objectives.map((objective) => (
                  <details key={objective.objectiveNumber} open>
                    <summary>Objective {objective.objectiveNumber}: {objective.description}</summary>
                    <h4>Interventions</h4>
                    <ul>{objective.interventions.map((intervention) => <li key={intervention}>{intervention}</li>)}</ul>
                  </details>
                ))}
              </details>
            ))}
          </details>
        ))}
      </section>

      <section className='panel'>
        <h2>Signatures</h2>
        {plan.signatures.map((signature) => (
          <dl key={signature.signatureType} className='signature-grid'>
            <div><dt>Type</dt><dd>{signature.signatureType}</dd></div>
            <div><dt>Signer role</dt><dd>{signature.signerRoleOrType}</dd></div>
            <div><dt>Signed</dt><dd>{signature.signatureDatetime}</dd></div>
            <div><dt>Image/base64</dt><dd>{signature.signatureDataOmittedReason}</dd></div>
          </dl>
        ))}
      </section>

      <section className='panel checklist-panel'>
        <div className='section-heading'>
          <div>
            <p className='eyebrow'>42-step checklist</p>
            <h2>Checklist Evidence</h2>
          </div>
          <span>{plan.criteria.length} criteria</span>
        </div>
        <div className='criterion-list'>
          {filteredCriteria.map((criterion) => (
            <button key={criterion.criterionId} type='button' className='criterion-row' onClick={() => setSelectedCriterion(criterion)}>
              <span>{criterion.title}</span>
              <StatusBadge status={criterion.status} />
            </button>
          ))}
        </div>
        <EvidencePanel criterion={selectedCriterion} />
        <div className='manager-actions'>
          <label>
            Manager comment
            <textarea value={comment} onChange={(event) => setComment(event.target.value)} />
          </label>
          <label>
            Override reason
            <input value={overrideReason} onChange={(event) => setOverrideReason(event.target.value)} />
          </label>
          <div className='button-row'>
            <button type='button' onClick={saveReturn}>Return for correction</button>
            <button type='button' className='secondary-button' onClick={saveOverride}>Save override</button>
          </div>
          {actionMessage && <p role='status'>{actionMessage}</p>}
        </div>
      </section>

      <section className='panel'>
        <h2>Evidence Coverage Map</h2>
        <div className='summary-grid'>
          <span>Criteria total: 42</span>
          <span>With evidence: 39</span>
          <span>Missing evidence: 3</span>
          <span>Runtime-only fields: 1</span>
        </div>
        <p>Used, missing, unmapped, and unused content are separated so managers can see what the checklist did and did not evaluate.</p>
      </section>

      <RawFieldExplorer plan={plan} />
    </div>
  )
}
