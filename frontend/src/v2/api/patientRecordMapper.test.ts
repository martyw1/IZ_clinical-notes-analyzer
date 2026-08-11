import { describe, expect, it } from 'vitest'
import { composePatientRecordSections } from './patientRecordMapper'

describe('composePatientRecordSections', () => {
  it('groups nested patient fields by their semantic parent before leaf labels', () => {
    const sections = composePatientRecordSections({
      firstName: 'Alex',
      contact: { email: 'alex.synthetic@example.invalid' },
      careTeam: [{ displayName: 'Synthetic Counselor', role: 'Primary counselor' }],
      coverage: { memberStatus: 'Active', payer: 'Synthetic Health Plan' },
      levelOfCare: 'PHP',
    })
    const pathsBySection = Object.fromEntries(
      sections.map((section) => [section.title, section.fields.map((field) => field.path)]),
    )

    expect(pathsBySection['Identity and demographics']).toEqual(['firstName'])
    expect(pathsBySection['Contact information']).toEqual(['contact.email'])
    expect(pathsBySection['Care and admission']).toEqual(['levelOfCare'])
    expect(pathsBySection['Care team']).toEqual(['careTeam[1].displayName', 'careTeam[1].role'])
    expect(pathsBySection['Coverage and payer information']).toEqual([
      'coverage.memberStatus',
      'coverage.payer',
    ])
  })
})
