import { useEffect, useState } from 'react'
import { createWorkflowProfile, listWorkflowProfiles, publishWorkflowProfile } from '../api/workflowClient'
import type { WorkflowProfile } from '../api/workflowClient'

type WorkflowProfilesPageProps = { readonly token: string }

export function WorkflowProfilesPage({ token }: WorkflowProfilesPageProps) {
  const [profiles, setProfiles] = useState<readonly WorkflowProfile[]>([])
  const [message, setMessage] = useState('')
  const [isCreating, setIsCreating] = useState(false)
  const [publishingVersionId, setPublishingVersionId] = useState<number | null>(null)

  async function refreshProfiles() {
    setProfiles(await listWorkflowProfiles(token))
  }

  useEffect(() => { void refreshProfiles() }, [token])

  async function create(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setMessage('')
    setIsCreating(true)
    const form = new FormData(event.currentTarget)
    try {
      await createWorkflowProfile(token, String(form.get('workflowKey') ?? ''), String(form.get('displayName') ?? ''), String(form.get('description') ?? ''))
      await refreshProfiles()
      setMessage('Workflow profile created as draft version 1.')
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Unable to create this workflow profile.')
    } finally {
      setIsCreating(false)
    }
  }

  async function publish(profileId: number, versionId: number, version: number) {
    setMessage('')
    setPublishingVersionId(versionId)
    try {
      await publishWorkflowProfile(token, profileId, versionId)
      await refreshProfiles()
      setMessage(`Workflow profile version ${version} published.`)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Unable to publish this workflow profile version.')
    } finally {
      setPublishingVersionId(null)
    }
  }

  return <section className='panel'>
    <p className='eyebrow'>Workflow Profiles</p>
    <h2>Versioned review workflows</h2>
    <form className='settings-form' onSubmit={create}>
      <label>Workflow key<input name='workflowKey' /></label>
      <label>Display name<input name='displayName' /></label>
      <label>Description<input name='description' /></label>
      <button type='submit' disabled={isCreating}>{isCreating ? 'Creating...' : 'Create workflow profile'}</button>
    </form>
    <div className='table-panel'>
      <table>
        <thead><tr><th>Name</th><th>Key</th><th>Versions</th><th>Active</th></tr></thead>
        <tbody>{profiles.map((profile) => <tr key={profile.id}>
          <td data-label='Name'>{profile.displayName}</td>
          <td data-label='Key'>{profile.workflowKey}</td>
          <td data-label='Versions'>{profile.versions.map((version) => <div key={version.id} className='workflow-version-row'>
            <span>Version {version.version}: {version.status}</span>
            {version.status === 'draft' && <button type='button' className='secondary-button' disabled={publishingVersionId === version.id} onClick={() => void publish(profile.id, version.id, version.version)}>
              {publishingVersionId === version.id ? 'Publishing...' : `Publish version ${version.version}`}
            </button>}
          </div>)}</td>
          <td data-label='Active'>{profile.isActive ? 'active' : 'archived'}</td>
        </tr>)}</tbody>
      </table>
    </div>
    {message && <p role='status'>{message}</p>}
  </section>
}
