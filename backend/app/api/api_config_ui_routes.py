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
      section { background: white; border: 1px solid #e2e8f0; border-radius: 14px; padding: 1.25rem; margin: 1rem 0; box-shadow: 0 8px 28px rgba(15, 23, 42, 0.06); }
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
    </style>
  </head>
  <body onload="initializeSession()">
    <main>
      <h1>API Configuration and Connectivity Test</h1>
      <p class="hint">Use this local admin page to test API-key or OAuth client-credentials connectivity without putting credentials into source files.</p>

      <section>
        <h2>1. Admin session</h2>
        <p class="hint">This test harness uses the admin session from the main app window. Open it from App settings after signing in as an administrator.</p>
        <button onclick="initializeSession()">Use current app session</button>
        <span id="loginStatus" class="hint">Checking admin session...</span>
      </section>

      <section>
        <h2>2. API settings</h2>
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
        <label>API key for one-time test or saved configuration <input id="apiKey" type="password" autocomplete="off" placeholder="Paste key here; it is never shown in results or logs" /></label>
        <div class="grid">
          <label>Client ID <input id="clientId" autocomplete="off" /></label>
          <label>Client secret <input id="clientSecret" type="password" autocomplete="off" placeholder="Saved encrypted; never shown in results" /></label>
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
        <button onclick="saveConfig()">Save config and encrypted secret</button>
        <button onclick="clearSavedKey()" class="danger">Clear saved secret</button>
        <p class="hint">For Alleva REST/OpenAPI tests, use the REST API base URL, usually https://api.allevasoft.com, and the Swagger/OpenAPI JSON URL. Alleva has confirmed HL7 is the current standards path. Saving stores the API key or client secret encrypted in the local app database. One-time values can be used for a test without saving.</p>
      </section>

      <section>
        <h2>3. Test a specific API call</h2>
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

      <section>
        <h2>4. Pull definitions and test connectivity</h2>
        <button onclick="testConnectivity()">Pull API definitions / test connectivity</button>
        <button onclick="useLocalSample()" class="secondary">Use local sample definition</button>
        <p id="testStatus" class="hint">No test run yet.</p>
        <pre id="result">Results will appear here.</pre>
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
        displayResult('result', config);
      }

      async function saveConfig() {
        if (!token) { setText('loginStatus', 'Sign in first.'); return; }
        const body = {
          vendor_name: getValue('vendorName'),
          api_base_url: getValue('apiBaseUrl'),
          api_key: getValue('apiKey') || null,
          client_id: getValue('clientId') || null,
          client_secret: getValue('clientSecret') || null,
          token_url: getValue('tokenUrl') || null,
          token_auth_style: getValue('tokenAuthStyle') || 'body',
          timeout_seconds: Number(getValue('timeoutSeconds') || '10'),
          api_enabled: false
        };
        const config = await readJson(await fetch(`${api}/api-configuration`, { method: 'PATCH', headers: authHeaders(), body: JSON.stringify(body) }));
        byId('apiKey').value = '';
        byId('clientSecret').value = '';
        displayResult('result', config);
      }

      async function clearSavedKey() {
        if (!token) { setText('loginStatus', 'Sign in first.'); return; }
        const config = await readJson(await fetch(`${api}/api-configuration`, {
          method: 'PATCH',
          headers: authHeaders(),
          body: JSON.stringify({ clear_api_key: true, clear_client_secret: true })
        }));
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
          displayResult('result', result);
        } catch (error) {
          setText('testStatus', error.message);
          byId('testStatus').className = 'warn';
        }
      }

      function useLocalSample() {
        const origin = window.location.origin;
        byId('swaggerUiUrl').value = `${origin}/api/api-configuration/sample-openapi.json`;
        byId('openApiUrl').value = `${origin}/api/api-configuration/sample-openapi.json`;
        byId('apiBaseUrl').value = origin;
        setText('testStatus', 'Local sample definition selected. Sign in, then click Pull API definitions / test connectivity.');
        byId('testStatus').className = 'ok';
        setText('result', JSON.stringify({
          swagger_ui_url: byId('swaggerUiUrl').value,
          openapi_url: byId('openApiUrl').value,
          api_base_url: byId('apiBaseUrl').value,
          next_step: 'Click Pull API definitions / test connectivity.'
        }, null, 2));
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
          displayResult('operationResult', result);
        } catch (error) {
          setText('operationStatus', error.message);
          byId('operationStatus').className = 'warn';
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
