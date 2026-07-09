export type JsonRecord = Record<string, unknown>

export class ApiRequestError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiRequestError'
    this.status = status
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
  const text = await response.text()
  if (!text) return {}
  return JSON.parse(text)
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
