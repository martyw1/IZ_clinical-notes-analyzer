from __future__ import annotations

from fastapi import APIRouter
from starlette.responses import HTMLResponse

router = APIRouter()


def _api_configuration_page() -> HTMLResponse:
    html = """
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>API Configuration - IZ Clinical Notes Analyzer</title>
    <style>
      :root { color-scheme: light; }
      body { font-family: Segoe UI, Arial, sans-serif; margin: 0; background: #f8fafc; color: #0f172a; }
      main { max-width: 1040px; margin: 0 auto; padding: 2rem; }
      section { background: white; border: 1px solid #e2e8f0; border-radius: 8px; padding: 1.25rem; margin: 1rem 0; box-shadow: 0 8px 28px rgba(15, 23, 42, 0.06); }
      h1 { margin-bottom: 0.25rem; }
      h2 { margin-top: 0; }
      label { display: block; font-weight: 650; margin-top: 0.8rem; }
      input, textarea, select { width: 100%; box-sizing: border-box; margin-top: 0.25rem; padding: 0.65rem; border-radius: 10px; border: 1px solid #cbd5e1; font: inherit; }
      textarea { min-height: 5rem; }
      button { margin-top: 0.8rem; margin-right: 0.5rem; padding: 0.65rem 0.9rem; border: 0; border-radius: 10px; background: #1d4ed8; color: white; font-weight: 700; cursor: pointer; }
      button.secondary { background: #475569; }
      button.danger { background: #b91c1c; }
      pre { white-space: pre-wrap; overflow-wrap: anywhere; background: #0f172a; color: #e2e8f0; padding: 1rem; border-radius: 10px; }
      .hint { color: #475569; }
      .ok { color: #047857; font-weight: 700; }
      .warn { color: #b45309; font-weight: 700; }
      .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 1rem; }
      .operation-row { display: grid; grid-template-columns: 110px 1fr; gap: 0.8rem; align-items: end; }
      .field-card { border: 1px solid #e2e8f0; border-radius: 10px; padding: 0.8rem; background: #f8fafc; }
      .required { color: #b91c1c; font-weight: 800; }
      .preset-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 0.75rem; }
      .preset-grid button { width: 100%; text-align: left; }
      .status-frame { margin-top: 0.85rem; border: 1px solid #cbd5e1; border-radius: 10px; background: #f8fafc; padding: 0.75rem; }
      .status-frame strong { display: block; margin-bottom: 0.35rem; }
      .status-frame pre { margin: 0; max-height: 8rem; overflow: auto; background: transparent; color: #334155; padding: 0; font-size: 0.9rem; }
      .workflow-list { margin: 0.75rem 0 0; padding-left: 1.4rem; color: #334155; }
      .workflow-list li { margin: 0.35rem 0; }
      .parameter-list { margin: 0.5rem 0 0; padding-left: 1.2rem; color: #475569; }
      .primary-action { font-size: 1rem; padding: 0.8rem 1rem; }
      .copy-output { min-height: 12rem; font-family: Consolas, 'Courier New', monospace; white-space: pre; overflow: auto; }
    </style>
  </head>
  <body onload="initializeSession()">
    <main>
      <h1>API Configuration and Connectivity Test</h1>
      <p class="hint">Use this local admin page to test the same active Alleva/API connection saved in App settings without putting credentials into source files.</p>
      <ol class="workflow-list">
        <li>Use the current admin session.</li>
        <li>Load or save the active API settings from App Settings.</li>
        <li>Test authentication and OpenAPI connectivity.</li>
        <li>Run ALL Patient Records only after the auth/connectivity test is understood.</li>
      </ol>

      <section>
        <h2>1. Admin session</h2>
        <p class="hint">This test harness uses the admin session from the main app window. Open it from App settings after signing in as an administrator.</p>
        <button onclick="initializeSession()">Use current app session</button>
        <span id="loginStatus" class="hint">Checking admin session...</span>
      </section>

      <section>
        <h2>2. Active API settings</h2>
        <p class="hint">App settings is the source of truth. This page loads and saves those same active values. Saved endpoint profiles in the main app are presets; activating one copies its values into these fields.</p>
        <div class="grid">
          <label>Vendor name <input id="vendorName" value="Alleva API" /></label>
          <label>REST API base URL <input id="apiBaseUrl" placeholder="https://api.allevasoft.com" /></label>
        </div>
        <label>Swagger UI URL <input id="swaggerUiUrl" value="https://api.allevasoft.com/swagger/index.html" /></label>
        <label>OpenAPI/Swagger JSON URL <input id="openApiUrl" placeholder="https://api.allevasoft.com/swagger/v1/swagger.json" /></label>
        <div class="grid">
          <label>API key header name <input id="apiKeyHeaderName" value="x-api-key" /></label>
          <label>Timeout seconds <input id="timeoutSeconds" type="number" min="1" max="60" value="10" /></label>
        </div>
        <label>Auth mode
          <select id="authMode">
            <option value="api_key">API key / saved secret</option>
            <option value="client_credentials">Client credentials token</option>
            <option value="none">No auth</option>
          </select>
        </label>
        <label>API key for one-time test or saved configuration <input id="apiKey" type="password" autocomplete="off" placeholder="Optional for API-key vendors; not usually used for Alleva OAuth" /></label>
        <div class="grid">
          <label>OAuth client ID <input id="clientId" autocomplete="off" /></label>
          <label>OAuth client secret <input id="clientSecret" type="password" autocomplete="off" placeholder="Paste secret here; saved encrypted and never shown after save" /></label>
        </div>
        <label>Token URL <input id="tokenUrl" value="https://authorization.allevasoft.com/connect/token" /></label>
        <label>Token auth style
          <select id="tokenAuthStyle">
            <option value="body">Body credentials</option>
            <option value="basic">Basic auth header</option>
            <option value="basic_urlencoded">Basic auth header, URL-encoded pair</option>
            <option value="both">Try body, then Basic</option>
            <option value="all">Try all supported styles</option>
          </select>
        </label>
        <label>OAuth scopes <input id="scope" placeholder="Optional client-credentials scope string" /></label>
        <button onclick="loadConfig()" class="secondary">Load saved config</button>
        <button onclick="saveConfig()">Save active config and encrypted secret</button>
        <button onclick="clearSavedKey()" class="danger">Clear saved secret</button>
        <p class="hint">For Alleva REST/OpenAPI tests, use the REST API base URL, usually https://api.allevasoft.com, and the Swagger/OpenAPI JSON URL. Alleva has confirmed HL7 is the current standards path. Pasting the client ID and secret supplied by Alleva/R3 is expected for OAuth client credentials. Saving stores the API key or client secret encrypted in the local app database. One-time values can be used for a test without saving.</p>
      </section>

      <section>
        <h2>3. Test authentication and connectivity</h2>
        <p class="hint">Run this after settings are saved. It requests a client-credentials token when OAuth is selected, then loads the OpenAPI definition so you can tell whether credentials, token style, base URL, and API documentation are usable.</p>
        <button onclick="testConnectivity()">Test saved auth and load API definition</button>
        <button onclick="useLocalSample()" class="secondary">Use local sample definition</button>
        <div class="status-frame" role="status" aria-live="polite">
          <strong>Harness status</strong>
          <pre id="statusFrame">No API harness action has run yet.</pre>
        </div>
        <p id="testStatus" class="hint">No test run yet.</p>
        <pre id="result">Results will appear here.</pre>
      </section>

      <section>
        <h2>4. Pull ALL Patient Records</h2>
        <p class="hint">Use this after Step 3 succeeds. The button sends GET /clients to the active Alleva REST API connection and formats the returned list as tab-separated rows that can be pasted into Excel.</p>
        <ul class="parameter-list">
          <li>Endpoint: GET /clients</li>
          <li>Parameters: Limit, Cursor, optional StartDate/EndDate, fields, api-version</li>
          <li>Header: X-Version</li>
          <li>Output fields: patient/client ID, source ID, admission date, status, client flag, discharge date, level of care, facility, primary clinician, first contact date. Patient names are not requested or displayed.</li>
        </ul>
        <button onclick="prepareAllevaQuickPull('all_patient_records')" class="secondary">Reset ALL Patient Records request</button>
        <button onclick="runAllevaQuickPull()" class="primary-action">Run ALL Patient Records pull</button>
        <label>Request details that will be sent
          <textarea id="quickPullPayload" spellcheck="false"></textarea>
        </label>
        <div class="status-frame" role="status" aria-live="polite">
          <strong>ALL Patient Records status</strong>
          <pre id="quickPullStatus">The ALL Patient Records request is prepared after settings load.</pre>
        </div>
        <label>Excel-ready TSV output
          <textarea id="quickPullTsv" class="copy-output" readonly spellcheck="false">Run the ALL Patient Records pull to create copy/paste rows for Excel.</textarea>
        </label>
        <pre id="quickPullResult">Detailed non-secret pull result will appear here.</pre>
      </section>

      <section>
        <h2>5. Advanced: test a specific API call</h2>
        <p class="hint">After pulling an OpenAPI/Swagger definition, choose an operation. The form below is generated from that operation's path, query, header, and request body requirements.</p>
        <label>API call / operation
          <select id="operationSelect" onchange="renderOperationForm()">
            <option value="">Pull definitions first.</option>
          </select>
        </label>
        <div id="operationFields" class="grid"></div>
        <button onclick="testSelectedOperation()">Test selected API call</button>
        <p id="operationStatus" class="hint">No API call selected.</p>
        <pre id="operationResult">API call test results will appear here.</pre>
      </section>
    </main>

    <script>
      const SESSION_TOKEN_KEY = 'iz-cna-session-token';
      let token = '';
      let currentDefinition = {};
      let currentSelectedDefinitionUrl = '';
      let currentOperations = [];
      const api = '/api';
      const byId = (id) => document.getElementById(id);
      const setText = (id, text) => { byId(id).textContent = text; };
      const getValue = (id) => byId(id).value.trim();
      const authHeaders = () => ({ 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' });
      const operationByKey = () => currentOperations.find((item) => item.operation_key === byId('operationSelect').value);
      window.addEventListener('message', (event) => {
        if (event.origin !== window.location.origin) return;
        const data = event.data || {};
        if (data.type !== 'iz-cna-session-token' || !data.token) return;
        window.sessionStorage.setItem(SESSION_TOKEN_KEY, data.token);
        token = data.token;
        initializeSession();
      });
      const displayResult = (id, payload) => {
        const clone = JSON.parse(JSON.stringify(payload || {}));
        if (clone.definition) clone.definition = { omitted_from_screen: true, definition_summary: clone.definition_summary || {} };
        if (Array.isArray(clone.operations) && clone.operations.length > 50) {
          clone.operations = clone.operations.slice(0, 50).concat([{ _truncated_items: clone.operations.length - 50 }]);
        }
        setText(id, JSON.stringify(clone, null, 2));
      };
      function appendStatus(id, message) {
        const element = byId(id);
        const stamp = new Date().toLocaleTimeString();
        const line = `${stamp} ${message}`;
        const existing = element.textContent && !element.textContent.startsWith('No ') && !element.textContent.startsWith('Choose ')
          ? element.textContent.split('\\n')
          : [];
        element.textContent = [line, ...existing].slice(0, 8).join('\\n');
      }

      function allevaVersion() {
        return '1.0';
      }

      function quickPullOperationParameters(_report) {
        const version = allevaVersion();
        const common = {
          Limit: 500,
          Cursor: 0,
          StartDate: '',
          EndDate: '',
          fields: ['id', 'clientId', 'uniqueId', 'mrn', 'status', 'isClient', 'admissionDateTime', 'firstContactDate', 'dischargeDateTime', 'facilityName', 'levelOfCare', 'primaryClinician', 'primaryClinicians'],
          'api-version': version,
          'X-Version': version
        };
        return common;
      }

      function quickPullLabel(report) {
        return {
          all_patient_records: 'ALL Patient Records',
          active_treatment_plans: 'all active treatment plans',
          overdue_treatment_plans: 'overdue treatment plans with computed reasons',
          inactive_treatment_plans: 'inactive treatment plans with computed reasons',
          active_patients: 'active patients with patient ID and first admission'
        }[report] || report;
      }

      async function readJson(response) {
        const text = await response.text();
        let payload = null;
        try { payload = text ? JSON.parse(text) : null; } catch { payload = { raw: text }; }
        if (!response.ok) {
          const detail = payload && payload.detail ? payload.detail : response.statusText;
          throw new Error(`HTTP ${response.status}: ${detail}`);
        }
        return payload;
      }

      function readSessionToken() {
        const localToken = window.sessionStorage.getItem(SESSION_TOKEN_KEY) || '';
        if (localToken) return localToken;
        try {
          const openerToken = window.opener?.sessionStorage?.getItem(SESSION_TOKEN_KEY) || '';
          if (openerToken) {
            window.sessionStorage.setItem(SESSION_TOKEN_KEY, openerToken);
            return openerToken;
          }
        } catch {
          return '';
        }
        return '';
      }

      async function initializeSession() {
        setText('loginStatus', 'Checking admin session...');
        token = readSessionToken();
        if (!token) {
          try {
            window.opener?.postMessage({ type: 'iz-cna-session-token-request' }, window.location.origin);
          } catch {}
          setText('loginStatus', 'Waiting for the admin session from the main app. Return to the main app, sign in as admin, then open this page from App settings if this does not update.');
          byId('loginStatus').className = 'warn';
          return;
        }
        try {
          const profile = await readJson(await fetch(`${api}/users/me`, { headers: authHeaders() }));
          if (!profile || profile.role !== 'admin') {
            token = '';
            setText('loginStatus', 'Admin access is required for API configuration and connectivity tests.');
            byId('loginStatus').className = 'warn';
            return;
          }
          setText('loginStatus', `Using signed-in admin session for ${profile.username}.`);
          byId('loginStatus').className = 'ok';
          await loadConfig();
        } catch (error) {
          token = '';
          window.sessionStorage.removeItem(SESSION_TOKEN_KEY);
          setText('loginStatus', error.message);
          byId('loginStatus').className = 'warn';
        }
      }

      async function loadConfig() {
        if (!token) { setText('loginStatus', 'Sign in first.'); return; }
        const config = await readJson(await fetch(`${api}/api-configuration`, { headers: authHeaders() }));
        byId('vendorName').value = config.vendor_name || '';
        byId('apiBaseUrl').value = config.api_base_url || '';
        byId('swaggerUiUrl').value = config.swagger_ui_url || 'https://api.allevasoft.com/swagger/index.html';
        byId('openApiUrl').value = config.openapi_url || '';
        byId('apiKeyHeaderName').value = config.api_key_header_name || 'x-api-key';
        byId('timeoutSeconds').value = String(config.timeout_seconds || 10);
        byId('clientId').value = config.client_id || '';
        byId('tokenUrl').value = config.token_url || 'https://authorization.allevasoft.com/connect/token';
        byId('tokenAuthStyle').value = config.token_auth_style || 'body';
        byId('authMode').value = config.recommended_auth_mode || (config.client_secret_configured && config.client_id_configured ? 'client_credentials' : 'api_key');
        if (!getValue('quickPullPayload')) prepareAllevaQuickPull('all_patient_records');
        displayResult('result', config);
      }

      async function saveConfig() {
        if (!token) { setText('loginStatus', 'Sign in first.'); return; }
        const body = {
          vendor_name: getValue('vendorName'),
          api_base_url: getValue('apiBaseUrl'),
          openapi_url: getValue('openApiUrl'),
          api_key: getValue('apiKey') || null,
          client_id: getValue('clientId') || null,
          client_secret: getValue('clientSecret') || null,
          token_url: getValue('tokenUrl') || null,
          token_auth_style: getValue('tokenAuthStyle') || 'body',
          timeout_seconds: Number(getValue('timeoutSeconds') || '10'),
          api_enabled: true
        };
        const config = await readJson(await fetch(`${api}/api-configuration`, { method: 'PATCH', headers: authHeaders(), body: JSON.stringify(body) }));
        byId('apiKey').value = '';
        byId('clientSecret').value = '';
        appendStatus('statusFrame', 'Saved active API config. Stored secrets were cleared from the browser fields.');
        displayResult('result', config);
      }

      async function clearSavedKey() {
        if (!token) { setText('loginStatus', 'Sign in first.'); return; }
        const config = await readJson(await fetch(`${api}/api-configuration`, {
          method: 'PATCH',
          headers: authHeaders(),
          body: JSON.stringify({ clear_api_key: true, clear_client_secret: true })
        }));
        appendStatus('statusFrame', 'Cleared saved API secret.');
        displayResult('result', config);
      }

      async function testConnectivity() {
        if (!token) {
          setText('loginStatus', 'Sign in first.');
          setText('testStatus', 'Sign in with the admin account before pulling definitions.');
          byId('testStatus').className = 'warn';
          return;
        }
        setText('testStatus', 'Testing...');
        appendStatus('statusFrame', 'Pulling API definitions and testing connectivity...');
        byId('testStatus').className = 'hint';
        const body = {
          swagger_ui_url: getValue('swaggerUiUrl'),
          api_base_url: getValue('apiBaseUrl'),
          openapi_url: getValue('openApiUrl'),
          api_key: getValue('apiKey') || null,
          use_saved_api_key: true,
          api_key_header_name: getValue('apiKeyHeaderName') || 'x-api-key',
          auth_mode: getValue('authMode') || 'api_key',
          token_url: getValue('tokenUrl') || null,
          token_auth_style: getValue('tokenAuthStyle') || 'body',
          client_id: getValue('clientId') || null,
          client_secret: getValue('clientSecret') || null,
          use_saved_client_credentials: true,
          scope: getValue('scope') || null,
          timeout_seconds: Number(getValue('timeoutSeconds') || '10')
        };
        try {
          const result = await readJson(await fetch(`${api}/api-configuration/pull-definitions`, {
            method: 'POST',
            headers: authHeaders(),
            body: JSON.stringify(body)
          }));
          currentDefinition = result.definition || {};
          currentSelectedDefinitionUrl = result.selected_definition_url || '';
          currentOperations = result.operations || [];
          populateOperations();
          setText('testStatus', `Result: ${result.status} - ${result.message}`);
          byId('testStatus').className = result.status === 'ok' ? 'ok' : 'warn';
          appendStatus('statusFrame', `Definition pull ${result.status}: ${result.message}`);
          displayResult('result', result);
        } catch (error) {
          setText('testStatus', error.message);
          byId('testStatus').className = 'warn';
          appendStatus('statusFrame', `Definition pull failed: ${error.message}`);
        }
      }

      function useLocalSample() {
        const origin = window.location.origin;
        byId('swaggerUiUrl').value = `${origin}/api/api-configuration/sample-openapi.json`;
        byId('openApiUrl').value = `${origin}/api/api-configuration/sample-openapi.json`;
        byId('apiBaseUrl').value = origin;
        setText('testStatus', 'Local sample definition selected. Sign in, then click Pull API definitions / test connectivity.');
        byId('testStatus').className = 'ok';
        appendStatus('statusFrame', 'Loaded local sample OpenAPI definition fields.');
        setText('result', JSON.stringify({
          swagger_ui_url: byId('swaggerUiUrl').value,
          openapi_url: byId('openApiUrl').value,
          api_base_url: byId('apiBaseUrl').value,
          next_step: 'Click Pull API definitions / test connectivity.'
        }, null, 2));
      }

      function prepareAllevaQuickPull(report) {
        byId('authMode').value = 'client_credentials';
        const payload = {
          report,
          swagger_ui_url: getValue('swaggerUiUrl') || 'https://api.allevasoft.com/swagger/index.html',
          api_base_url: getValue('apiBaseUrl') || 'https://api.allevasoft.com',
          openapi_url: getValue('openApiUrl') || 'https://api.allevasoft.com/swagger/v1/swagger.json',
          auth_mode: 'client_credentials',
          token_url: getValue('tokenUrl') || 'https://authorization.allevasoft.com/connect/token',
          token_auth_style: getValue('tokenAuthStyle') || 'body',
          client_id: getValue('clientId') || null,
          client_secret: null,
          use_saved_client_credentials: true,
          api_key: null,
          use_saved_api_key: true,
          api_key_header_name: getValue('apiKeyHeaderName') || 'x-api-key',
          scope: getValue('scope') || null,
          timeout_seconds: Number(getValue('timeoutSeconds') || '10'),
          max_pages: 20,
          operation_parameters: quickPullOperationParameters(report)
        };
        byId('quickPullPayload').value = JSON.stringify(payload, null, 2);
        appendStatus('quickPullStatus', `Prepared ${quickPullLabel(report)} using GET /clients with Limit, Cursor, fields, api-version, and X-Version.`);
      }

      async function runAllevaQuickPull() {
        if (!token) {
          setText('loginStatus', 'Sign in first.');
          appendStatus('quickPullStatus', 'Sign in with the admin account before running a quick pull.');
          return;
        }
        let body = {};
        try {
          body = JSON.parse(byId('quickPullPayload').value || '{}');
        } catch (error) {
          appendStatus('quickPullStatus', `POST fields are not valid JSON: ${error.message}`);
          return;
        }
        body.api_base_url = body.api_base_url || getValue('apiBaseUrl') || 'https://api.allevasoft.com';
        body.openapi_url = body.openapi_url || getValue('openApiUrl') || 'https://api.allevasoft.com/swagger/v1/swagger.json';
        body.swagger_ui_url = body.swagger_ui_url || getValue('swaggerUiUrl') || 'https://api.allevasoft.com/swagger/index.html';
        body.token_url = body.token_url || getValue('tokenUrl') || 'https://authorization.allevasoft.com/connect/token';
        body.token_auth_style = body.token_auth_style || getValue('tokenAuthStyle') || 'body';
        body.client_id = body.client_id || getValue('clientId') || null;
        body.client_secret = body.client_secret || getValue('clientSecret') || null;
        body.api_key = body.api_key || getValue('apiKey') || null;
        body.api_key_header_name = body.api_key_header_name || getValue('apiKeyHeaderName') || 'x-api-key';
        body.scope = body.scope || getValue('scope') || null;
        body.timeout_seconds = Number(body.timeout_seconds || getValue('timeoutSeconds') || '10');
        appendStatus('quickPullStatus', `Running ${quickPullLabel(body.report)}...`);
        try {
          const result = await readJson(await fetch(`${api}/api-configuration/alleva-quick-pull`, {
            method: 'POST',
            headers: authHeaders(),
            body: JSON.stringify(body)
          }));
          appendStatus('quickPullStatus', `${result.status}: ${result.message}`);
          byId('quickPullTsv').value = result.tsv || 'No TSV rows returned.';
          displayResult('quickPullResult', result);
        } catch (error) {
          appendStatus('quickPullStatus', `Quick pull failed: ${error.message}`);
        }
      }

      function populateOperations() {
        const select = byId('operationSelect');
        select.innerHTML = '';
        if (!currentOperations.length) {
          select.appendChild(new Option('No operations found in the loaded definition.', ''));
          byId('operationFields').innerHTML = '';
          return;
        }
        currentOperations.forEach((operation) => {
          const label = `${operation.method} ${operation.path}${operation.summary ? ' - ' + operation.summary : ''}`;
          select.appendChild(new Option(label, operation.operation_key));
        });
        renderOperationForm();
      }

      function inputTypeFor(field) {
        if (field.type === 'integer' || field.type === 'number') return 'number';
        if (field.type === 'boolean') return 'checkbox';
        if (field.format === 'date') return 'date';
        if (field.format === 'date-time') return 'datetime-local';
        return 'text';
      }

      function fieldInput(field, prefix) {
        const id = `${prefix}-${field.name}`;
        const required = field.required ? 'required' : '';
        const label = `${field.in || prefix}: ${field.name}${field.required ? ' *' : ''}`;
        if (field.enum && field.enum.length) {
          return `<label class="field-card">${label}<select id="${id}" data-name="${field.name}" data-kind="${prefix}" ${required}>${field.enum.map((value) => `<option value="${String(value)}">${String(value)}</option>`).join('')}</select><span class="hint">${field.description || ''}</span></label>`;
        }
        const type = inputTypeFor(field);
        if (type === 'checkbox') {
          return `<label class="field-card"><input id="${id}" data-name="${field.name}" data-kind="${prefix}" type="checkbox" /> ${label}<br /><span class="hint">${field.description || ''}</span></label>`;
        }
        return `<label class="field-card">${label}<input id="${id}" data-name="${field.name}" data-kind="${prefix}" type="${type}" value="${field.default || ''}" ${required} /><span class="hint">${field.description || ''}</span></label>`;
      }

      function renderOperationForm() {
        const operation = operationByKey();
        if (!operation) {
          byId('operationFields').innerHTML = '';
          setText('operationStatus', 'No API call selected.');
          return;
        }
        const parts = [];
        const parameters = operation.parameters || [];
        const bodyFields = operation.request_body_fields || [];
        if (parameters.length) parts.push(...parameters.map((field) => fieldInput(field, 'parameter')));
        if (bodyFields.length) parts.push(...bodyFields.map((field) => fieldInput(field, 'body')));
        if (!parts.length) parts.push('<p class="hint">This operation does not declare required path, query, header, or request body fields.</p>');
        byId('operationFields').innerHTML = parts.join('');
        setText('operationStatus', `${operation.method} ${operation.path} is ready to test.`);
      }

      function collectGeneratedValues(kind) {
        const values = {};
        document.querySelectorAll(`[data-kind="${kind}"]`).forEach((input) => {
          const name = input.getAttribute('data-name');
          if (!name) return;
          if (input.type === 'checkbox') values[name] = input.checked;
          else if (input.value !== '') values[name] = input.value;
        });
        return values;
      }

      async function testSelectedOperation() {
        if (!token) { setText('loginStatus', 'Sign in first.'); return; }
        const operation = operationByKey();
        if (!operation) { setText('operationStatus', 'Choose an API call first.'); return; }
        setText('operationStatus', 'Testing selected API call...');
        appendStatus('statusFrame', `Testing selected operation ${operation.method} ${operation.path}...`);
        byId('operationStatus').className = 'hint';
        const body = {
          definition: currentDefinition,
          selected_definition_url: currentSelectedDefinitionUrl,
          method: operation.method,
          path: operation.path,
          parameters: collectGeneratedValues('parameter'),
          request_body: collectGeneratedValues('body'),
          api_base_url: getValue('apiBaseUrl'),
          api_key: getValue('apiKey') || null,
          use_saved_api_key: true,
          api_key_header_name: getValue('apiKeyHeaderName') || 'x-api-key',
          auth_mode: getValue('authMode') || 'api_key',
          token_url: getValue('tokenUrl') || null,
          token_auth_style: getValue('tokenAuthStyle') || 'body',
          client_id: getValue('clientId') || null,
          client_secret: getValue('clientSecret') || null,
          use_saved_client_credentials: true,
          scope: getValue('scope') || null,
          timeout_seconds: Number(getValue('timeoutSeconds') || '10')
        };
        try {
          const result = await readJson(await fetch(`${api}/api-configuration/test-operation`, {
            method: 'POST',
            headers: authHeaders(),
            body: JSON.stringify(body)
          }));
          setText('operationStatus', `${result.status}: ${result.message}`);
          byId('operationStatus').className = result.status === 'ok' ? 'ok' : 'warn';
          appendStatus('statusFrame', `Operation test ${result.status}: ${result.message}`);
          displayResult('operationResult', result);
        } catch (error) {
          setText('operationStatus', error.message);
          byId('operationStatus').className = 'warn';
          appendStatus('statusFrame', `Operation test failed: ${error.message}`);
        }
      }
    </script>
  </body>
</html>
    """
    return HTMLResponse(html, headers={'cache-control': 'no-store'})


@router.get('/api-configuration', include_in_schema=False)
def api_configuration_page():
    return _api_configuration_page()


@router.get('/desktop/api-configuration', include_in_schema=False)
def desktop_api_configuration_page():
    return _api_configuration_page()
