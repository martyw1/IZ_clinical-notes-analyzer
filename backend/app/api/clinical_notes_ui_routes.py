from __future__ import annotations

from fastapi import APIRouter
from starlette.responses import HTMLResponse

router = APIRouter()


def _clinical_notes_intake_page() -> HTMLResponse:
    html = """
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Clinical Notes Intake - IZ Clinical Notes Analyzer</title>
    <style>
      :root { color-scheme: light; --green:#065f46; --ink:#10201a; --muted:#5e6f68; --line:#d8e1dc; --card:#ffffff; --bg:#f5f3e8; }
      body { margin:0; font-family: Segoe UI, Arial, sans-serif; background: linear-gradient(110deg,#f6ecd4 0%,#f8faf6 35%,#edf4ee 100%); color:var(--ink); }
      main { max-width:1180px; margin:0 auto; padding:2rem; }
      .eyebrow { color:var(--green); font-weight:800; letter-spacing:.08em; font-size:.78rem; text-transform:uppercase; }
      h1 { font-size: clamp(2.1rem, 4vw, 4.6rem); line-height:.96; margin:.4rem 0 1rem; max-width:920px; }
      .lead { max-width:760px; color:var(--muted); font-size:1.02rem; }
      .nav { display:flex; flex-wrap:wrap; gap:.7rem; margin:1.5rem 0; }
      .pill, button { border:1px solid var(--line); border-radius:999px; padding:.7rem 1rem; background:#fff; color:var(--ink); text-decoration:none; font-weight:700; cursor:pointer; }
      .pill.primary, button.primary { background:var(--green); border-color:var(--green); color:#fff; }
      .grid { display:grid; grid-template-columns: repeat(auto-fit,minmax(310px,1fr)); gap:1rem; }
      section { background:rgba(255,255,255,.88); border:1px solid rgba(6,95,70,.12); border-radius:24px; box-shadow:0 22px 50px rgba(16,32,26,.08); padding:1.25rem; }
      h2 { margin-top:.1rem; }
      label { display:block; font-weight:700; margin-top:.8rem; }
      input, textarea, select { box-sizing:border-box; width:100%; margin-top:.3rem; border:1px solid #c7d2cc; border-radius:14px; padding:.8rem; font:inherit; background:#fff; }
      textarea { min-height:6rem; }
      .workflow { display:grid; gap:.75rem; margin-top:1rem; }
      .step { display:grid; grid-template-columns:42px 1fr; gap:.8rem; align-items:start; padding:.8rem; border:1px solid #e2e8e3; border-radius:18px; background:#fbfdfb; }
      .num { width:32px; height:32px; display:grid; place-items:center; border-radius:50%; background:#e4f1ea; color:var(--green); font-weight:900; }
      .hint { color:var(--muted); font-size:.92rem; }
      pre { white-space:pre-wrap; overflow-wrap:anywhere; border-radius:18px; background:#0f172a; color:#e2e8f0; padding:1rem; min-height:8rem; }
      footer { margin-top:2rem; color:var(--muted); font-size:.85rem; display:flex; justify-content:space-between; gap:1rem; flex-wrap:wrap; }
    </style>
  </head>
  <body>
    <main>
      <div class="eyebrow">Clinical notes intake</div>
      <h1>Bring notes in by upload or by EMR lookup, then run the same completeness checks.</h1>
      <p class="lead">This page makes the two required intake paths explicit: manual upload of a patient's clinical-note bundle, and direct API-oriented lookup by patient ID or patient name when the Alleva/API connection is configured.</p>

      <nav class="nav">
        <a class="pill primary" href="/?view=uploads">Open manual upload</a>
        <a class="pill" href="/">Main dashboard</a>
        <a class="pill" href="/api-configuration" target="_blank" rel="noopener noreferrer">API connectivity</a>
        <a class="pill" href="/api/readiness" target="_blank" rel="noopener noreferrer">Readiness</a>
        <a class="pill" href="/docs" target="_blank" rel="noopener noreferrer">API docs</a>
      </nav>

      <div class="grid">
        <section>
          <h2>Manual upload workflow</h2>
          <p class="hint">Use this when staff already downloaded notes/documents from Alleva or received a clinical-note export bundle.</p>
          <div class="workflow">
            <div class="step"><div class="num">1</div><div><b>Choose Manual upload</b><br /><span class="hint">Use the main app's manual upload tab for PDFs, DOCX, TXT, CSV, RTF, images, ZIPs, or other supported exports.</span></div></div>
            <div class="step"><div class="num">2</div><div><b>Enter patient context</b><br /><span class="hint">Patient ID is preferred. Patient name can be entered as chart context when ID is unavailable.</span></div></div>
            <div class="step"><div class="num">3</div><div><b>Map each file</b><br /><span class="hint">Classify files as custom forms, uploaded documents, portal documents, labs, medication data, notes, or other.</span></div></div>
            <div class="step"><div class="num">4</div><div><b>Run completeness check</b><br /><span class="hint">The same Treatment Plan Tracking rules apply after intake regardless of manual or API source.</span></div></div>
          </div>
        </section>

        <section>
          <h2>Direct Alleva/API lookup</h2>
          <p class="hint">Use this once API configuration is tested and the clinic/vendor confirms the supported endpoints and credentials.</p>
          <label>Patient ID <input id="patientId" placeholder="Example: ALV-100245" /></label>
          <label>Patient name <input id="patientName" placeholder="Example: Jordan Sample" /></label>
          <label>Document scope
            <select id="scope">
              <option value="all">All clinical-note/document buckets</option>
              <option value="notes">Notes only</option>
              <option value="custom_forms">Custom forms / treatment-plan documents</option>
              <option value="uploaded_documents">Uploaded documents</option>
            </select>
          </label>
          <button class="primary" onclick="buildPlan()">Build API import plan</button>
          <button onclick="window.open('/api-configuration','_blank')">Configure/test API</button>
          <pre id="result">Enter a patient ID or name to see the planned API import workflow.</pre>
        </section>
      </div>

      <section>
        <h2>Design intent</h2>
        <p>This app should treat manual upload and direct API lookup as two front doors into the same internal review object: a patient note set with source metadata, document classification, extracted text where possible, and a generated completeness review.</p>
      </section>
      <footer><span>IZ Clinical Notes Analyzer</span><span>Use only test/synthetic patient data until a production PHI deployment is approved.</span></footer>
    </main>
    <script>
      function buildPlan() {
        const patientId = document.getElementById('patientId').value.trim();
        const patientName = document.getElementById('patientName').value.trim();
        const scope = document.getElementById('scope').value;
        const queryMode = patientId ? 'patient_id' : patientName ? 'patient_name' : 'missing';
        const plan = {
          status: queryMode === 'missing' ? 'needs_input' : 'planned',
          query_mode: queryMode,
          patient_id: patientId || null,
          patient_name: patientName || null,
          document_scope: scope,
          next_steps: queryMode === 'missing' ? ['Enter a patient ID or patient name.'] : [
            'Validate API configuration and credentials.',
            'Resolve patient record from the supplied ID or name.',
            'Request clinical note/document references from supported Alleva/API endpoints.',
            'Download supported document payloads or attachment URLs.',
            'Store files in the encrypted patient note set.',
            'Run Treatment Plan Tracking completeness rules.',
            'Send results to manager review queue.'
          ],
          note: 'Live import remains gated until the client/vendor confirms endpoint names, credentials, pagination, rate limits, and attachment download behavior.'
        };
        document.getElementById('result').textContent = JSON.stringify(plan, null, 2);
      }
    </script>
  </body>
</html>
    """
    return HTMLResponse(html, headers={'cache-control': 'no-store'})


@router.get('/clinical-notes-intake', include_in_schema=False)
def clinical_notes_intake_page():
    return _clinical_notes_intake_page()


@router.get('/desktop/clinical-notes-intake', include_in_schema=False)
def desktop_clinical_notes_intake_page():
    return _clinical_notes_intake_page()
