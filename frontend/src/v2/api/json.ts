export type JsonRecord = Record<string, unknown>

export class ApiRequestError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiRequestError'
    this.status = status
  }
}

const safeDetails = new Set([
  'Access denied', 'Invalid credentials', 'Account inactive', 'Account locked', 'Account temporarily locked',
  'Password change is required before accessing the workspace', 'Current password is incorrect',
  'New password must differ from the current password', 'Password cannot be the same as the username.',
  'Password is too common.', 'Password must include at least one letter and one number.',
  'Username is required', 'Username exists', 'Confirm the MRN correction and submit again.',
  'Manual aggregate uploads must use source_mode=manual_upload', 'Select a specific treatment-plan version.',
  'MRN correction confirmation is required because conflicting MRNs were detected across the binder.',
  'MRN correction confirmation is required because the binder MRN differs from the override.',
  'MRN correction confirmation is required because the file MRN differs from the override.',
  'MRN is required in an extractable source or the MRN override field.',
  'MRN is required in the file or the MRN override field.', 'Manual treatment-plan source files cannot be empty.',
])

const validationFields = new Map<string, string>([
  ['username', 'Username'], ['password', 'Password'], ['current_password', 'Current password'],
  ['new_password', 'New password'], ['patient_id', 'MRN'], ['source_mode', 'Source mode'],
  ['treatment_plans', 'Treatment plans'], ['file', 'Selected file'], ['full_name', 'Full name'],
  ['role', 'Role'], ['admission_date', 'Admission date'], ['plan_version_id', 'Treatment-plan version'],
])

const validationTypes = new Map<string, string>([
  ['missing', 'is required.'], ['string_too_short', 'does not meet the minimum length requirement.'],
  ['string_too_long', 'exceeds the maximum length.'], ['string_type', 'must be text.'],
  ['int_parsing', 'must be a whole number.'], ['int_type', 'must be a whole number.'],
  ['bool_parsing', 'must be a true or false value.'], ['list_type', 'must be a list.'],
  ['model_type', 'must be an object.'], ['dict_type', 'must be an object.'],
  ['date_from_datetime_parsing', 'must be a valid date.'], ['date_parsing', 'must be a valid date.'],
  ['literal_error', 'must use a supported value.'], ['json_invalid', 'must contain valid JSON.'],
])

export function safeApiErrorMessage(status: number, payload: JsonRecord): string {
  if (status === 422 && Array.isArray(payload.detail)) {
    const messages = readRecordList(payload, 'detail').slice(0, 5).map((error) => {
      const field = readList(error, 'loc').slice().reverse()
        .map((part) => typeof part === 'string' ? validationFields.get(part) : undefined).find(Boolean)
      return `${field ?? 'A submitted field'} ${validationTypes.get(readString(error, 'type')) ?? 'has an invalid value.'}`
    })
    return [...new Set(messages)].join(' ') || 'Check the submitted fields and try again.'
  }
  const detail = readString(payload, 'detail')
  if (status < 500 && safeDetails.has(detail)) return detail
  switch (status) {
    case 400: return 'The submitted data could not be accepted. Check it and try again.'
    case 401: return 'Authentication is required. Sign in and try again.'
    case 403: return 'Access denied.'
    case 404: return 'The requested record is unavailable.'
    case 409: return 'The request conflicts with the current record. Refresh and try again.'
    case 413: return 'The selected upload is too large.'
    case 422: return 'Check the submitted fields and try again.'
    case 429: return 'Too many requests. Wait before trying again.'
    default: return 'The local service returned an unexpected error. Restart the app and try again.'
  }
}

export function isRecord(value: unknown): value is JsonRecord {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

export function readString(record: JsonRecord, key: string, fallback = ''): string {
  const value = record[key]
  return typeof value === 'string' ? value : fallback
}

export function readNumber(record: JsonRecord, key: string, fallback = 0): number {
  const value = record[key]
  return typeof value === 'number' ? value : fallback
}

export function readBoolean(record: JsonRecord, key: string, fallback = false): boolean {
  const value = record[key]
  return typeof value === 'boolean' ? value : fallback
}

export function readList(record: JsonRecord, key: string): readonly unknown[] {
  const value = record[key]
  return Array.isArray(value) ? value : []
}

export function readRecord(record: JsonRecord, key: string): JsonRecord {
  const value = record[key]
  return isRecord(value) ? value : {}
}

export function readRecordList(record: JsonRecord, key: string): readonly JsonRecord[] {
  return readList(record, key).filter(isRecord)
}

export function readStringList(record: JsonRecord, key: string): readonly string[] {
  return readList(record, key).filter((value) => typeof value === 'string')
}

export async function readPayload(response: Response): Promise<unknown> {
  try {
    const text = await response.text()
    return text ? JSON.parse(text) : {}
  } catch {
    throw new ApiRequestError(response.status, 'The local service returned an unexpected error. Restart the app and try again.')
  }
}

export async function readRecordPayload(response: Response): Promise<JsonRecord> {
  const payload = await readPayload(response)
  if (isRecord(payload)) return payload
  throw new ApiRequestError(response.status, 'Expected an object response from the local API.')
}

export async function readRecordListPayload(response: Response): Promise<readonly JsonRecord[]> {
  const payload = await readPayload(response)
  if (Array.isArray(payload)) return payload.filter(isRecord)
  throw new ApiRequestError(response.status, 'Expected a list response from the local API.')
}
