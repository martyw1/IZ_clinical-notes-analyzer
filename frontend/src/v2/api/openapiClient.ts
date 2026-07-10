import { readNumber, readRecord, readRecordPayload, readString } from './json'
import { request } from './request'
import type { OpenApiDefinitionSummary } from './types'

export async function pullOpenApiDefinition(token: string): Promise<OpenApiDefinitionSummary> {
  const payload = await readRecordPayload(
    await request('/api/api-configuration/pull-definitions', { token, method: 'POST' }),
  )
  const summary = readRecord(payload, 'definition_summary')
  return { title: readString(summary, 'title'), operationCount: readNumber(summary, 'operation_count') }
}
