import type { JsonRecord } from './json'

export type PatientRecordField = {
  readonly path: string
  readonly label: string
  readonly value: string
}

export type PatientRecordSection = {
  readonly title: string
  readonly fields: readonly PatientRecordField[]
}

const sectionOrder = [
  'Identity and demographics',
  'Contact information',
  'Care and admission',
  'Care team',
  'Coverage and payer information',
  'Source metadata',
  'Additional patient information',
] as const

export function composePatientRecordSections(record: JsonRecord): readonly PatientRecordSection[] {
  const grouped = new Map<string, PatientRecordField[]>()
  for (const field of flattenRecord(record)) {
    const section = sectionForPath(field.path)
    const existing = grouped.get(section) ?? []
    existing.push(field)
    grouped.set(section, existing)
  }
  return sectionOrder
    .map((title) => ({ title, fields: grouped.get(title) ?? [] }))
    .filter((section) => section.fields.length > 0)
}

function flattenRecord(record: JsonRecord): readonly PatientRecordField[] {
  const fields: PatientRecordField[] = []
  for (const [key, value] of Object.entries(record)) flattenValue(value, key, fields)
  return fields
}

function flattenValue(value: unknown, path: string, fields: PatientRecordField[]) {
  if (Array.isArray(value)) {
    if (value.length === 0) {
      fields.push(fieldFor(path, 'None recorded'))
      return
    }
    if (value.every((item) => isScalar(item))) {
      fields.push(fieldFor(path, value.map(displayValue).join(', ')))
      return
    }
    value.forEach((item, index) => flattenValue(item, `${path}[${index + 1}]`, fields))
    return
  }
  if (isRecord(value)) {
    const entries = Object.entries(value)
    if (entries.length === 0) {
      fields.push(fieldFor(path, 'No fields returned'))
      return
    }
    for (const [key, nested] of entries) flattenValue(nested, `${path}.${key}`, fields)
    return
  }
  fields.push(fieldFor(path, displayValue(value)))
}

function fieldFor(path: string, value: string): PatientRecordField {
  return { path, label: humanizePath(path), value }
}

function humanizePath(path: string): string {
  const segments = path.split('.')
  const segment = segments[segments.length - 1] ?? path
  return segment
    .replace(/([a-z0-9])([A-Z])/g, '$1 $2')
    .replace(/_/g, ' ')
    .replace(/^./, (value) => value.toUpperCase())
}

function sectionForPath(path: string): (typeof sectionOrder)[number] {
  const normalized = path.toLowerCase()
  const root = normalized.split(/[.[]/, 1)[0] ?? normalized
  if (includesAny(root, ['careteam', 'care_team', 'providers', 'staff', 'counselors'])) return 'Care team'
  if (includesAny(root, ['insurance', 'payer', 'coverage', 'policy'])) return 'Coverage and payer information'
  if (includesAny(root, ['contact', 'address', 'phone', 'email'])) return 'Contact information'
  if (includesAny(normalized, ['name', 'mrn', 'birth', 'dob', 'gender', 'sex', 'pronoun', 'marital', 'race', 'ethnicity'])) return 'Identity and demographics'
  if (includesAny(normalized, ['address', 'phone', 'email', 'contact', 'city', 'state', 'postal', 'zip'])) return 'Contact information'
  if (includesAny(normalized, ['counselor', 'therapist', 'provider', 'staff', 'careteam', 'case manager', 'caseManager'])) return 'Care team'
  if (includesAny(normalized, ['insurance', 'payer', 'coverage', 'policy', 'member'])) return 'Coverage and payer information'
  if (includesAny(normalized, ['admission', 'discharge', 'levelofcare', 'level_of_care', 'program', 'facility', 'status', 'allerg', 'medication', 'diagnos', 'risk'])) return 'Care and admission'
  if (includesAny(normalized, ['id', 'route', 'href', 'created', 'updated', 'modified', 'deleted', 'client'])) return 'Source metadata'
  return 'Additional patient information'
}

function includesAny(value: string, candidates: readonly string[]): boolean {
  return candidates.some((candidate) => value.includes(candidate.toLowerCase()))
}

function displayValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return 'Not provided'
  if (typeof value === 'boolean') return value ? 'Yes' : 'No'
  if (typeof value === 'number' || typeof value === 'string') return String(value)
  return JSON.stringify(value)
}

function isScalar(value: unknown): boolean {
  return value === null || ['boolean', 'number', 'string'].includes(typeof value)
}

function isRecord(value: unknown): value is JsonRecord {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}
