import json
import shutil
import subprocess
from pathlib import Path


def test_api_configuration_page_places_treatment_plan_section_after_all_patient_records():
    # Given: the standalone API harness page is rendered by the desktop backend.
    from app.api.api_config_ui_routes import _api_configuration_page

    # When: the API configuration page loads.
    page = _api_configuration_page()

    # Then: treatment-plan controls appear after section 4 and before the advanced section.
    assert page.status_code == 200
    html = page.body.decode('utf-8')
    assert html.index('4. Pull ALL Patient Records') < html.index('5. Pull Patient Treatment Plans')
    assert html.index('5. Pull Patient Treatment Plans') < html.index('6. Advanced: test a specific API call')
    assert 'Pull Patient-Centered Treatment Plans' in html
    assert 'Pull Active Patient-Centered Treatment Plans' in html
    assert 'Pull Single Patient Treatment Plans' in html
    assert 'Diagnostic: Pull All Treatment Plans' in html
    assert 'GET /treatment-plans?ClientId={patient_id}' in html
    assert 'Patient / Client ID' in html


def test_api_configuration_page_executes_treatment_plan_payload_javascript(tmp_path):
    # Given: the backend-rendered harness JavaScript is evaluated with a minimal DOM.
    node = shutil.which('node')
    if node is None:
        import pytest

        pytest.skip('Node.js is required to execute the API harness browser JavaScript regression.')

    from app.api.api_config_ui_routes import _api_configuration_page

    html_path = tmp_path / 'api-configuration.html'
    html_path.write_text(_api_configuration_page().body.decode('utf-8'), encoding='utf-8')
    script_path = Path(__file__).with_name('fixtures') / 'api_harness_treatment_plan_ui_test.js'

    # When: Node executes the harness payload and disabled-state logic.
    completed = subprocess.run([node, str(script_path), str(html_path)], text=True, capture_output=True, check=False)

    # Then: the executable JavaScript regression reports no assertion failures.
    assert completed.returncode == 0, completed.stderr or completed.stdout
    assert json.loads(completed.stdout)['patient_id'] == 'PAT-HREF-001'
