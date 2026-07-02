export type TreatmentPlanContentItem = {
  kind: string
  label: string
  source_path: string
  text?: string
  text_present?: boolean
  redacted_text_sha256?: string
  metadata?: Record<string, unknown>
}

const SAFE_CONTENT_KINDS = new Set(['plan_field', 'problem', 'diagnosis', 'behavioral_definition', 'goal', 'objective', 'intervention'])
const SAFE_METADATA_KEYS = new Set([
  'code',
  'diagnosisCode',
  'icd10Code',
  'icdCode',
  'status',
  'severity',
  'onsetDate',
  'targetDate',
  'startDate',
  'dueDate',
  'frequency',
  'modality',
  'duration',
  'serviceType',
])
const SAFE_STATUSES = new Set([
  'active',
  'addressed',
  'complete',
  'completed',
  'current',
  'deferred',
  'discontinued',
  'inactive',
  'in progress',
  'met',
  'new',
  'not met',
  'ongoing',
  'open',
  'partial',
  'partially met',
  'planned',
  'resolved',
  'reviewed',
])
const SAFE_SEVERITIES = new Set(['low', 'mild', 'moderate', 'medium', 'high', 'severe', 'critical'])
const SAFE_MODALITIES = new Set([
  'case management',
  'family',
  'group',
  'group therapy',
  'individual',
  'individual therapy',
  'medication management',
  'peer support',
  'psychoeducation',
  'therapy',
])
const SAFE_SERVICES = new Set([...SAFE_MODALITIES, 'counseling', 'iop', 'iop-5', 'outpatient', 'php', 'residential', 'treatment planning'])
const SAFE_TITLE_WORDS = new Set([
  'abstinence',
  'active',
  'admission',
  'addiction',
  'alcohol',
  'anxiety',
  'assessment',
  'behavioral',
  'case',
  'client',
  'complete',
  'completed',
  'counseling',
  'coping',
  'created',
  'daily',
  'date',
  'definition',
  'definitions',
  'depression',
  'diagnosis',
  'discharge',
  'disorder',
  'education',
  'end',
  'family',
  'flag',
  'for',
  'goal',
  'goals',
  'group',
  'guardian',
  'individual',
  'intensive',
  'initial',
  'intervention',
  'interventions',
  'modified',
  'monthly',
  'needs',
  'objective',
  'objectives',
  'outpatient',
  'partial',
  'plan',
  'prevention',
  'program',
  'residential',
  'recovery',
  'relapse',
  'reason',
  'review',
  'service',
  'signature',
  'skills',
  'staff',
  'start',
  'substance',
  'therapy',
  'trauma',
  'treatment',
  'use',
  'weekly',
  'wiley',
])
const CODE_RE = /^[A-Z0-9][A-Z0-9.-]{1,39}$/i
const DATE_RE = /^\d{4}-\d{2}-\d{2}$/
const FREQUENCY_RE = /^(?:\d+\s*(?:x|times?)\s*(?:per\s*)?(?:day|week|month|year)|every\s+\d+\s*(?:days?|weeks?|months?)|(?:daily|weekly|biweekly|monthly|quarterly|annually|yearly|as needed|prn|once|twice))$/i
const DURATION_RE = /^(?:\d+\s*(?:minutes?|mins?|hours?|hrs?|days?|weeks?|months?)|ongoing|as needed|prn)$/i
const TITLE_CASE_PHRASE_RE = /\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3}\b/g
const UNSAFE_KEY_RE = /(name|client|patient|person|member|lead|author|custodian|address|phone|email|dob|birth|ssn|filename|secret|token|password|api[-_]?key)/i
const CANARY_RE = /(Jane Q Doe|John Public|Mary Patient|Forbidden Display Name|Alice Smith)/i
const REDACTED_TOKEN_RE = /\[redacted\]/i
const DIRECT_IDENTIFIER_LABEL_RE = /\b(?:name|client|patient|member|lead|address|phone|email|dob|birth|ssn|mrn|chart)\b\s*[:=]/i

function scalar(value: unknown, maxChars: number) {
  if (value == null || typeof value === 'object') return ''
  const text = String(value).replace(/\s+/g, ' ').trim().slice(0, maxChars)
  if (!text || CANARY_RE.test(text) || looksNameLike(text)) return ''
  return text
}

function narrativeText(value: unknown, maxChars: number) {
  if (value == null || typeof value === 'object') return ''
  const text = String(value).replace(/\s+/g, ' ').trim().slice(0, maxChars)
  if (!text || CANARY_RE.test(text) || REDACTED_TOKEN_RE.test(text) || DIRECT_IDENTIFIER_LABEL_RE.test(text) || looksNameLike(text)) return ''
  return text
}

function looksNameLike(value: string) {
  for (const match of value.matchAll(TITLE_CASE_PHRASE_RE)) {
    const words = match[0].match(/[A-Z][a-z]+/g)?.map((word) => word.toLowerCase()) || []
    if (words.length && words.every((word) => SAFE_TITLE_WORDS.has(word))) continue
    return true
  }
  return false
}

function safeMetadataValue(key: string, value: unknown) {
  if (!SAFE_METADATA_KEYS.has(key) || UNSAFE_KEY_RE.test(key)) return ''
  const text = scalar(value, 120)
  if (!text) return ''
  if (['code', 'diagnosisCode', 'icd10Code', 'icdCode'].includes(key)) return CODE_RE.test(text) ? text.toUpperCase() : ''
  if (['onsetDate', 'targetDate', 'startDate', 'dueDate'].includes(key)) return DATE_RE.test(text.slice(0, 10)) ? text.slice(0, 10) : ''
  if (key === 'status') return SAFE_STATUSES.has(text.toLowerCase()) ? text : ''
  if (key === 'severity') return SAFE_SEVERITIES.has(text.toLowerCase()) ? text : ''
  if (key === 'frequency') return FREQUENCY_RE.test(text) ? text : ''
  if (key === 'duration') return DURATION_RE.test(text) ? text : ''
  if (key === 'modality') return SAFE_MODALITIES.has(text.toLowerCase()) ? text : ''
  if (key === 'serviceType') return SAFE_SERVICES.has(text.toLowerCase()) ? text : ''
  return ''
}

export function safeContentItems(items?: TreatmentPlanContentItem[] | null) {
  const counts: Record<string, number> = {}
  return (items || [])
    .map((item) => {
      const rawKind = scalar(item.kind, 40).toLowerCase()
      const kind = SAFE_CONTENT_KINDS.has(rawKind) ? rawKind : 'content'
      counts[kind] = (counts[kind] || 0) + 1
      const label = narrativeText(item.label, 120)
      const metadata: Record<string, string> = {}
      Object.entries(item.metadata || {}).forEach(([key, value]) => {
        const safeValue = safeMetadataValue(key, value)
        if (safeValue) metadata[key] = safeValue
      })
      return {
        kind,
        label: label || `${kind.replace(/_/g, ' ').replace(/\b\w/g, (character) => character.toUpperCase())} ${counts[kind]}`,
        source_path: scalar(item.source_path, 120),
        text: narrativeText(item.text, 2000),
        text_present: Boolean(item.text_present),
        metadata,
      }
    })
}

export type SafeTreatmentPlanContentItem = ReturnType<typeof safeContentItems>[number]

export type TreatmentPlanObjectiveNode = SafeTreatmentPlanContentItem & {
  interventions: SafeTreatmentPlanContentItem[]
}

export type TreatmentPlanGoalNode = SafeTreatmentPlanContentItem & {
  objectives: TreatmentPlanObjectiveNode[]
}

export type TreatmentPlanProblemNode = SafeTreatmentPlanContentItem & {
  behavioral_definitions: SafeTreatmentPlanContentItem[]
  diagnoses: SafeTreatmentPlanContentItem[]
  goals: TreatmentPlanGoalNode[]
}

export type TreatmentPlanContentTree = {
  plan_fields: SafeTreatmentPlanContentItem[]
  problems: TreatmentPlanProblemNode[]
  top_level_diagnoses: SafeTreatmentPlanContentItem[]
  top_level_behavioral_definitions: SafeTreatmentPlanContentItem[]
  top_level_goals: TreatmentPlanGoalNode[]
  top_level_objectives: TreatmentPlanObjectiveNode[]
  top_level_interventions: SafeTreatmentPlanContentItem[]
  unattached_items: SafeTreatmentPlanContentItem[]
}

const PROBLEM_PATH_RE = /^problems\[(\d+)\]$/
const PROBLEM_DIAGNOSIS_PATH_RE = /^problems\[(\d+)\]\.diagnoses\[(\d+)\]$/
const PROBLEM_DEFINITION_PATH_RE = /^problems\[(\d+)\]\.behavioralDefinitions\[(\d+)\]$/
const GOAL_PATH_RE = /^problems\[(\d+)\]\.goals\[(\d+)\]$/
const OBJECTIVE_PATH_RE = /^problems\[(\d+)\]\.goals\[(\d+)\]\.objectives\[(\d+)\]$/
const INTERVENTION_PATH_RE = /^problems\[(\d+)\]\.goals\[(\d+)\]\.objectives\[(\d+)\]\.interventions\[(\d+)\]$/
const TOP_LEVEL_DIAGNOSIS_PATH_RE = /^diagnoses\[(\d+)\]$/
const TOP_LEVEL_DEFINITION_PATH_RE = /^behavioralDefinitions\[(\d+)\]$/
const TOP_LEVEL_GOAL_PATH_RE = /^goals\[(\d+)\]$/
const TOP_LEVEL_OBJECTIVE_PATH_RE = /^objectives\[(\d+)\]$/
const TOP_LEVEL_INTERVENTION_PATH_RE = /^interventions\[(\d+)\]$/

function sortBySourcePath<T extends { source_path: string; label: string }>(items: T[]) {
  return [...items].sort((left, right) => `${left.source_path} ${left.label}`.localeCompare(`${right.source_path} ${right.label}`))
}

function placeholderItem(kind: string, index: string, sourcePath: string): SafeTreatmentPlanContentItem {
  return {
    kind,
    label: `${kind.replace(/_/g, ' ').replace(/\b\w/g, (character) => character.toUpperCase())} ${index}`,
    source_path: sourcePath,
    text: '',
    text_present: false,
    metadata: {},
  }
}

function ensureProblem(problems: Map<string, TreatmentPlanProblemNode>, problemIndex: string) {
  const problemPath = `problems[${problemIndex}]`
  const existing = problems.get(problemPath)
  if (existing) return existing
  const created = {
    ...placeholderItem('problem', problemIndex, problemPath),
    behavioral_definitions: [],
    diagnoses: [],
    goals: [],
  }
  problems.set(problemPath, created)
  return created
}

function ensureGoal(problem: TreatmentPlanProblemNode, goalIndex: string) {
  const goalPath = `${problem.source_path}.goals[${goalIndex}]`
  const existing = problem.goals.find((goal) => goal.source_path === goalPath)
  if (existing) return existing
  const created = { ...placeholderItem('goal', goalIndex, goalPath), objectives: [] }
  problem.goals.push(created)
  return created
}

function ensureObjective(goal: TreatmentPlanGoalNode, objectiveIndex: string) {
  const objectivePath = `${goal.source_path}.objectives[${objectiveIndex}]`
  const existing = goal.objectives.find((objective) => objective.source_path === objectivePath)
  if (existing) return existing
  const created = { ...placeholderItem('objective', objectiveIndex, objectivePath), interventions: [] }
  goal.objectives.push(created)
  return created
}

function replaceGoal(problem: TreatmentPlanProblemNode, node: TreatmentPlanGoalNode) {
  const index = problem.goals.findIndex((goal) => goal.source_path === node.source_path)
  if (index >= 0) {
    const existing = problem.goals[index]
    if (existing) {
      problem.goals[index] = { ...node, objectives: existing.objectives }
      return
    }
  }
  problem.goals.push(node)
}

function replaceObjective(goal: TreatmentPlanGoalNode, node: TreatmentPlanObjectiveNode) {
  const index = goal.objectives.findIndex((objective) => objective.source_path === node.source_path)
  if (index >= 0) {
    const existing = goal.objectives[index]
    if (existing) {
      goal.objectives[index] = { ...node, interventions: existing.interventions }
      return
    }
  }
  goal.objectives.push(node)
}

function pathGroup(match: RegExpMatchArray, index: number) {
  return match[index] || ''
}

export function safeContentTree(items?: TreatmentPlanContentItem[] | null): TreatmentPlanContentTree {
  const problems = new Map<string, TreatmentPlanProblemNode>()
  const tree: TreatmentPlanContentTree = {
    plan_fields: [],
    problems: [],
    top_level_diagnoses: [],
    top_level_behavioral_definitions: [],
    top_level_goals: [],
    top_level_objectives: [],
    top_level_interventions: [],
    unattached_items: [],
  }

  safeContentItems(items).forEach((item) => {
    if (item.kind === 'plan_field') {
      tree.plan_fields.push(item)
      return
    }
    const problemMatch = item.source_path.match(PROBLEM_PATH_RE)
    if (item.kind === 'problem' && problemMatch) {
      problems.set(item.source_path, { ...item, behavioral_definitions: [], diagnoses: [], goals: [] })
      return
    }
    const definitionMatch = item.source_path.match(PROBLEM_DEFINITION_PATH_RE)
    if (item.kind === 'behavioral_definition' && definitionMatch) {
      ensureProblem(problems, pathGroup(definitionMatch, 1)).behavioral_definitions.push(item)
      return
    }
    const diagnosisMatch = item.source_path.match(PROBLEM_DIAGNOSIS_PATH_RE)
    if (item.kind === 'diagnosis' && diagnosisMatch) {
      ensureProblem(problems, pathGroup(diagnosisMatch, 1)).diagnoses.push(item)
      return
    }
    const goalMatch = item.source_path.match(GOAL_PATH_RE)
    if (item.kind === 'goal' && goalMatch) {
      replaceGoal(ensureProblem(problems, pathGroup(goalMatch, 1)), { ...item, objectives: [] })
      return
    }
    const objectiveMatch = item.source_path.match(OBJECTIVE_PATH_RE)
    if (item.kind === 'objective' && objectiveMatch) {
      const goal = ensureGoal(ensureProblem(problems, pathGroup(objectiveMatch, 1)), pathGroup(objectiveMatch, 2))
      replaceObjective(goal, { ...item, interventions: [] })
      return
    }
    const interventionMatch = item.source_path.match(INTERVENTION_PATH_RE)
    if (item.kind === 'intervention' && interventionMatch) {
      const goal = ensureGoal(ensureProblem(problems, pathGroup(interventionMatch, 1)), pathGroup(interventionMatch, 2))
      ensureObjective(goal, pathGroup(interventionMatch, 3)).interventions.push(item)
      return
    }
    if (item.kind === 'diagnosis' && TOP_LEVEL_DIAGNOSIS_PATH_RE.test(item.source_path)) tree.top_level_diagnoses.push(item)
    else if (item.kind === 'behavioral_definition' && TOP_LEVEL_DEFINITION_PATH_RE.test(item.source_path)) tree.top_level_behavioral_definitions.push(item)
    else if (item.kind === 'goal' && TOP_LEVEL_GOAL_PATH_RE.test(item.source_path)) tree.top_level_goals.push({ ...item, objectives: [] })
    else if (item.kind === 'objective' && TOP_LEVEL_OBJECTIVE_PATH_RE.test(item.source_path)) tree.top_level_objectives.push({ ...item, interventions: [] })
    else if (item.kind === 'intervention' && TOP_LEVEL_INTERVENTION_PATH_RE.test(item.source_path)) tree.top_level_interventions.push(item)
    else tree.unattached_items.push(item)
  })

  tree.plan_fields = sortBySourcePath(tree.plan_fields)
  tree.problems = sortBySourcePath([...problems.values()])
  return tree
}

export function contentItemMetadataSummary(item: ReturnType<typeof safeContentItems>[number]) {
  const entries = Object.entries(item.metadata || {})
  if (!entries.length) return item.text_present && !item.text ? 'Text value redacted or unavailable' : 'No metadata'
  return entries.map(([key, value]) => `${key}: ${value}`).join(' | ')
}

export function contentStatusLabel(status?: string | null) {
  if (status === 'structured') return 'Structured facts captured'
  if (status === 'counts_only') return 'Counts only'
  if (status === 'detail_empty') return 'Detail loaded, no content exposed'
  if (status === 'collection_only') return 'Collection only'
  if (status === 'manual') return 'Manual/test content'
  return 'Content status unknown'
}
