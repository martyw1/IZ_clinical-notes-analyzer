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
      input, textarea { width: 100%; box-sizing: border-box; margin-top: 0.25rem; padding: 0.65rem; border-radius: 10px; border: 1px solid #cbd5e1; font: inherit; }
      textarea { min-height: 5rem; }
      button { margin-top: 0.8rem; margin-right: 0.5rem; padding: 0.65rem 0.9rem; border: 0; border-radius: 10px; background: #1d4ed8; color: white; font-weight: 700; cursor: pointer; }
      button.secondary { background: #475569; }
      button.danger { background: #b91c1c; }
      pre { white-space: pre-wrap; overflow-wrap: anywhere; background: #0f172a; color: #e2e8f0; padding: 1rem; border-radius: 10px; }
      .hint { color: #475569; }
      .ok { color: #047857; font-weight: 700; }
      .warn { color: #b45309; font-weight: 700; }
      .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 1rem; }
    </style>
  </head>
  <body>
    <main>
      <h1>API Configuration and Connectivity Test</h1>
      <p class="hint">Use this local admin page to enter an API key, pull OpenAPI/Swagger definitions, and test connectivity without putting credentials into source files.</p>

      <section>
        <h2>1. Admin sign-in</h2>
        <div class="grid">
          <label>Username <input id="username" autocomplete="username" value="admin" /></label>
          <label>Password <input id="password" type="password" autocomplete="current-password" /></label>
        </div>
        <button onclick="login()">Sign in</button>
        <span id="loginStatus" class="hint">Not signed in.</span>
      </section>

      <section>
        <h2>2. API settings</h2>
        <div class="grid">
          <label>Vendor name <input id="vendorName" value="Alleva API" /></label>
          <label>API base URL <input id="apiBaseUrl" placeholder="https://api.allevasoft.com" /></label>
        </div>
        <label>Swagger UI URL <input id="swaggerUiUrl" value="https://api.allevasoft.com/swagger/index.html" /></label>
        <label>OpenAPI/Swagger JSON URL <input id="openApiUrl" placeholder="https://api.allevasoft.com/swagger/v1/swagger.json" /></label>
        <div class="grid">
          <label>API key header name <input id="apiKeyHeaderName" value="x-api-key" /></label>
          <label>Timeout seconds <input id="timeoutSeconds" type="number" min="1" max="60" value="10" /></label>
        </div>
        <label>API key for one-time test or saved configuration <input id="apiKey" type="password" autocomplete="off" placeholder="Paste key here; it is never shown in results or logs" /></label>
        <button onclick="loadConfig()" class="secondary">Load saved config</button>
        <button onclick="saveConfig()">Save config and encrypted API key</button>
        <button onclick="clearSavedKey()" class="danger">Clear saved API key</button>
        <p class="hint">Saving stores the key encrypted in the local app database. The connectivity test can also use a one-time pasted key without saving it.</p>
      </section>

      <section>
        <h2>3. Pull definitions and test connectivity</h2>
        <button onclick="testConnectivity()">Pull API definitions / test connectivity</button>
        <button onclick="useLocalSample()" class="secondary">Use local sample definition</button>
        <p id="testStatus" class="hint">No test run yet.</p>
        <pre id="result">Results will appear here.</pre>
      </section>
    </main>

    <script>
      let token = '';
      const api = '/api';
      const byId = (id) => document.getElementById(id);
      const setText = (id, text) => { byId(id).textContent = text; };
      const getValue = (id) => byId(id).value.trim();
      const authHeaders = () => ({ 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' });

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

      async function login() {
        setText('loginStatus', 'Signing in...');
        try {
          const payload = await readJson(await fetch(`${api}/auth/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username: getValue('username'), password: getValue('password') })
          }));
          token = payload.access_token;
          setText('loginStatus', 'Signed in.');
          byId('loginStatus').className = 'ok';
          await loadConfig();
        } catch (error) {
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
        setText('result', JSON.stringify(config, null, 2));
      }

      async function saveConfig() {
        if (!token) { setText('loginStatus', 'Sign in first.'); return; }
        const body = {
          vendor_name: getValue('vendorName'),
          api_base_url: getValue('apiBaseUrl'),
          api_key: getValue('apiKey') || null,
          timeout_seconds: Number(getValue('timeoutSeconds') || '10'),
          api_enabled: false
        };
        const config = await readJson(await fetch(`${api}/api-configuration`, { method: 'PATCH', headers: authHeaders(), body: JSON.stringify(body) }));
        byId('apiKey').value = '';
        setText('result', JSON.stringify(config, null, 2));
      }

      async function clearSavedKey() {
        if (!token) { setText('loginStatus', 'Sign in first.'); return; }
        const config = await readJson(await fetch(`${api}/api-configuration`, {
          method: 'PATCH',
          headers: authHeaders(),
          body: JSON.stringify({ clear_api_key: true })
        }));
        setText('result', JSON.stringify(config, null, 2));
      }

      async function testConnectivity() {
        if (!token) { setText('loginStatus', 'Sign in first.'); return; }
        setText('testStatus', 'Testing...');
        byId('testStatus').className = 'hint';
        const body = {
          swagger_ui_url: getValue('swaggerUiUrl'),
          api_base_url: getValue('apiBaseUrl'),
          openapi_url: getValue('openApiUrl'),
          api_key: getValue('apiKey') || null,
          use_saved_api_key: true,
          api_key_header_name: getValue('apiKeyHeaderName') || 'x-api-key',
          timeout_seconds: Number(getValue('timeoutSeconds') || '10')
        };
        try {
          const result = await readJson(await fetch(`${api}/api-configuration/pull-definitions`, {
            method: 'POST',
            headers: authHeaders(),
            body: JSON.stringify(body)
          }));
          setText('testStatus', `Result: ${result.status} - ${result.message}`);
          byId('testStatus').className = result.status === 'ok' ? 'ok' : 'warn';
          setText('result', JSON.stringify(result, null, 2));
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
