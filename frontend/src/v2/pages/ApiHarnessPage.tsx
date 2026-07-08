import { JobProgressCard } from '../components/JobProgressCard'

export function ApiHarnessPage() {
  return (
    <div className='page-grid'>
      <section className='panel'>
        <p className='eyebrow'>API Testing Harness</p>
        <h2>Alleva/OpenAPI testing</h2>
        <div className='harness-grid'>
          <article>Authentication test</article>
          <article>Swagger/OpenAPI load</article>
          <article>Operation workbench</article>
          <article>Pull ALL Patient Records</article>
          <article>Pull Patient-Centered Treatment Plans using ClientId</article>
          <article>Pull Active Patient-Centered Treatment Plans</article>
          <article>Pull Single Patient Treatment Plans</article>
          <article>Diagnostic Pull All Treatment Plans</article>
        </div>
      </section>
      <JobProgressCard />
    </div>
  )
}
