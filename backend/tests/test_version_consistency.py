import json

from fastapi.testclient import TestClient

from app.core.config import REPO_ROOT


def test_beta_version_metadata_is_consistent_across_primary_surfaces(app_with_sqlite):
    app, _ = app_with_sqlite
    version = (REPO_ROOT / 'VERSION').read_text(encoding='utf-8').strip()
    metadata = json.loads((REPO_ROOT / 'VERSION.json').read_text(encoding='utf-8'))
    package_json = json.loads((REPO_ROOT / 'frontend' / 'package.json').read_text(encoding='utf-8'))
    package_lock = json.loads((REPO_ROOT / 'frontend' / 'package-lock.json').read_text(encoding='utf-8'))

    assert version == '1.4.6-beta.1'
    assert metadata['version'] == version
    assert metadata['release_channel'] == 'beta-local-desktop'
    assert metadata['stability'] == 'beta'
    assert metadata['is_prerelease'] is True
    assert package_json['version'] == version
    assert package_lock['version'] == version
    assert package_lock['packages']['']['version'] == version

    current_docs = [
        REPO_ROOT / 'README.md',
        REPO_ROOT / 'AGENTS.md',
        REPO_ROOT / 'docs' / 'release-notes.md',
        REPO_ROOT / 'docs' / 'open-blockers.md',
        REPO_ROOT / 'docs' / 'codebase-map.md',
        REPO_ROOT / 'docs' / 'treatment-plan-checklist-v1.md',
    ]
    for doc_path in current_docs:
        text = doc_path.read_text(encoding='utf-8')
        assert version in text, f'{doc_path} is missing {version}'

    app_tsx = (REPO_ROOT / 'frontend' / 'src' / 'App.tsx').read_text(encoding='utf-8')
    assert 'Beta v' in app_tsx
    assert "'Not loaded'" in app_tsx
    assert "|| '1.2.0'" not in app_tsx

    with TestClient(app) as client:
        payload = client.get('/api/version').json()
    assert payload['version'] == version
    assert payload['release_channel'] == 'beta-local-desktop'
    assert payload['stability'] == 'beta'
    assert payload['is_prerelease'] is True
