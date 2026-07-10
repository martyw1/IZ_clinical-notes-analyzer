import { useState } from 'react'
import { testReadOnlyOperation } from '../api/operationClient'
import { JobProgressCard } from '../components/JobProgressCard'

type ApiHarnessPageProps = {
  readonly token: string
}

export function ApiHarnessPage({ token }: ApiHarnessPageProps) {
  const [path, setPath] = useState('/health')
  const [operationMessage, setOperationMessage] = useState('')
  const [isTesting, setIsTesting] = useState(false)

  async function runOperationTest() {
    setIsTesting(true)
    try {
      const result = await testReadOnlyOperation(token, path)
      setOperationMessage(`${result.message} ${result.statusCode ?? 'No status'} | ${result.responseBytes} bytes${result.responseTruncated ? ' (truncated)' : ''}.`)
    } catch (error) {
      setOperationMessage(error instanceof Error ? error.message : 'Unable to test the saved API operation.')
    } finally {
      setIsTesting(false)
    }
  }

  return (
    <div className='page-grid'>
      <section className='panel'>
        <p className='eyebrow'>API Testing Harness</p>
        <h2>Alleva/OpenAPI testing</h2>
        <div className='harness-grid'>
          <article>Authentication test</article>
          <article>Swagger/OpenAPI load</article>
          <article>
            <label>
              Read-only operation path
              <input value={path} onChange={(event) => setPath(event.target.value)} placeholder='/health' />
            </label>
            <button type='button' onClick={() => void runOperationTest()} disabled={isTesting}>
              {isTesting ? 'Testing operation...' : 'Test read-only operation'}
            </button>
            {operationMessage && <p role='status'>{operationMessage}</p>}
          </article>
          <article>Pull ALL Patient Records</article>
          <article>Pull Patient-Centered Treatment Plans using ClientId</article>
          <article>Pull Active Patient-Centered Treatment Plans</article>
          <article>Pull Single Patient Treatment Plans</article>
          <article>Diagnostic Pull All Treatment Plans</article>
        </div>
      </section>
      <JobProgressCard token={token} />
    </div>
  )
}
