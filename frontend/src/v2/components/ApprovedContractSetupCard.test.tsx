import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import type { ApiConfiguration } from '../api/types'
import { ApprovedContractSetupCard } from './ApprovedContractSetupCard'

const CONFIG: ApiConfiguration = {
  vendorName: 'Alleva REST API',
  apiBaseUrl: 'https://api.allevasoft.com',
  openapiUrl: 'https://api.allevasoft.com/swagger/v1/swagger.json',
  tokenUrl: 'https://authorization.allevasoft.com/connect/token',
  clientId: 'configured-client-id',
  apiKeyConfigured: true,
  clientSecretConfigured: true,
  tokenAuthStyle: 'body',
  scopes: 'https://authorization.allevasoft.com/api:read',
  paginationLimit: 100,
  syncLimit: 250,
  timeoutSeconds: 10,
  apiEnabled: true,
  treatmentPlanSyncEnabled: true,
  treatmentPlanSyncApproved: true,
  treatmentPlanEndpointMappingValidated: true,
  activeContractVersion: '',
  activeContractEffectiveAt: '',
}

afterEach(() => {
  vi.unstubAllGlobals()
})

it('records a confirmed published Alleva v1 mapping without exposing credentials', async () => {
  // Given: valid saved connection settings and an administrator confirming the vendor limits and test evidence.
  const fetchMock = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => new Response(
    JSON.stringify({
      contract_version: 'alleva-rest-v1-2026-07-13',
      contract_sha256: 'a'.repeat(64),
      effective_at: '2026-07-13T12:00:00Z',
      approved_at: '2026-07-13T12:00:00Z',
    }),
    { status: 201, headers: { 'content-type': 'application/json' } },
  ))
  vi.stubGlobal('fetch', fetchMock)
  const onApproved = vi.fn()
  render(<ApprovedContractSetupCard config={CONFIG} token='synthetic-token' onApproved={onApproved} />)

  fireEvent.change(screen.getByLabelText('Mapping version'), {
    target: { value: 'alleva-rest-v1-2026-07-13' },
  })
  fireEvent.change(screen.getByLabelText('Non-PHI test population reference'), {
    target: { value: 'Alleva sandbox cohort validated 2026-07-13' },
  })
  fireEvent.change(screen.getByLabelText('Vendor-approved maximum requests per minute'), {
    target: { value: '60' },
  })
  fireEvent.click(screen.getByLabelText(/I confirm this endpoint mapping/i))

  // When: the administrator records the approved contract.
  fireEvent.click(screen.getByRole('button', { name: 'Record approved Alleva v1 mapping' }))

  // Then: the exact saved connection profile is bound to the published v1 endpoint contract.
  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
  const request = fetchMock.mock.calls[0]?.[1]
  expect(request?.method).toBe('POST')
  expect(request?.body).toContain('"path":"/treatment-reviews/{review_id}"')
  expect(request?.body).toContain('"client_id":"client.id"')
  expect(JSON.parse(String(request?.body))).toMatchObject({
    endpoints: {
      treatment_plans: {
        parameters: { client_id: 'ClientId' },
        field_mappings: { client_id: 'client.id', client_reference: 'client.route' },
      },
    },
  })
  expect(request?.body).not.toContain('configured-client-id')
  expect(await screen.findByRole('status')).toHaveTextContent('Approved mapping alleva-rest-v1-2026-07-13 recorded.')
  expect(onApproved).toHaveBeenCalledWith('alleva-rest-v1-2026-07-13')
})
