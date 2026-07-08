export function SettingsPage() {
  return (
    <section className='panel'>
      <p className='eyebrow'>Settings</p>
      <h2>Local V2 controls</h2>
      <div className='warning-band'>
        LOC-change update window remains unvalidated by R3/Marleigh. The placeholder is configurable and currently shown as 7 calendar days.
      </div>
      <dl className='summary-grid'>
        <div><dt>Runtime</dt><dd>local FastAPI + React/Vite</dd></div>
        <div><dt>Data</dt><dd>%LOCALAPPDATA%\\IZ Clinical Notes Analyzer</dd></div>
        <div><dt>LLM decisions</dt><dd>Disabled for compliance decisions</dd></div>
        <div><dt>Raw sensitive mode</dt><dd>Off by default</dd></div>
      </dl>
    </section>
  )
}
