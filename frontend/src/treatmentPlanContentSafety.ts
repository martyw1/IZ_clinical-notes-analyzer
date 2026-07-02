export type TreatmentPlanContentItem = {
  kind: string
  label: string
  source_path: string
  text?: string
  text_present?: boolean
  redacted_text_sha256?: string
  metadata?: Record<string, unknown>
}

const SAFE_CONTENT_KINDS = new Set(['problem', 'diagnosis', 'goal', 'objective', 'intervention'])
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
  'complete',
  'completed',
  'counseling',
  'coping',
  'daily',
  'definition',
  'definitions',
  'depression',
  'diagnosis',
  'discharge',
  'disorder',
  'family',
  'goal',
  'goals',
  'group',
  'individual',
  'intensive',
  'intervention',
  'interventions',
  'monthly',
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
  'review',
  'service',
  'skills',
  'substance',
  'therapy',
  'trauma',
  'treatment',
  'use',
  'weekly',
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
      const metadata: Record<string, string> = {}
      Object.entries(item.metadata || {}).forEach(([key, value]) => {
        const safeValue = safeMetadataValue(key, value)
        if (safeValue) metadata[key] = safeValue
      })
      return {
        kind,
        label: `${kind.replace(/_/g, ' ').replace(/\b\w/g, (character) => character.toUpperCase())} ${counts[kind]}`,
        source_path: scalar(item.source_path, 120),
        text: narrativeText(item.text, 2000),
        text_present: Boolean(item.text_present),
        metadata,
      }
    })
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
