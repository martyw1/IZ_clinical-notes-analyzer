from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PREFLIGHT = REPOSITORY_ROOT / "scripts" / "ci" / "verify-github-preflight.py"


def _load_preflight(name: str) -> ModuleType:
    assert PREFLIGHT.is_file(), "GitHub identity boundary is not implemented"
    spec = importlib.util.spec_from_file_location(name, PREFLIGHT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_repository_id_type_rejects_numeric_node_swap() -> None:
    # Given: the fixed numeric and GraphQL identifiers in reversed typed positions.
    preflight = _load_preflight("task1_preflight_id_type")

    # When/Then: parsing refuses to conflate REST database IDs with node IDs.
    with pytest.raises(preflight.GitHubPreflightError, match="numeric repository ID"):
        preflight.parse_repository_identity(
            "martyw1/IZ_clinical-notes-analyzer",
            "R_kgDOReY3VA",
            "1172715348",
        )


@pytest.mark.parametrize(
    "remote_url",
    (
        "C:/workspace/IZ_clinical-notes-analyzer",
        "../IZ_clinical-notes-analyzer",
        "file:///tmp/IZ_clinical-notes-analyzer",
        "git@github.com:someone-else/IZ_clinical-notes-analyzer.git",
    ),
    ids=("local_remote", "relative_local_remote", "file_remote", "wrong_repository"),
)
def test_local_remote_and_wrong_repository_are_rejected(remote_url: str) -> None:
    # Given: a remote that cannot identify the immutable canonical repository.
    preflight = _load_preflight("task1_preflight_local_remote")

    # When/Then: only the exact SSH/HTTPS GitHub repository URL is accepted.
    with pytest.raises(preflight.GitHubPreflightError, match="remote"):
        preflight.validate_remote_url("martyw1/IZ_clinical-notes-analyzer", remote_url)


def test_undeleted_ref_is_rejected() -> None:
    # Given: cleanup output that still resolves the exact nonce ref.
    preflight = _load_preflight("task1_preflight_undeleted")
    nonce_ref = "refs/heads/codex-native/preflight-synthetic"
    remote_output = f"{'1' * 40}\t{nonce_ref}\n"

    # When/Then: a retained remote ref cannot produce a passing preflight receipt.
    with pytest.raises(preflight.GitHubPreflightError, match="cleanup"):
        preflight.require_deleted_ref(nonce_ref, remote_output)


def test_fixed_repository_snapshot_matches_both_typed_ids() -> None:
    # Given: the independently fixed identity and matching safe API fields.
    preflight = _load_preflight("task1_preflight_snapshot")
    identity = preflight.parse_repository_identity(
        "martyw1/IZ_clinical-notes-analyzer",
        "1172715348",
        "R_kgDOReY3VA",
    )
    snapshot = preflight.RepositorySnapshot(
        repository_id=1172715348,
        repository_node_id="R_kgDOReY3VA",
        default_branch="main",
        actions_enabled=True,
        can_push=True,
    )

    # When: the API snapshot is compared by matching semantic type.
    result = preflight.verify_repository_snapshot(identity, snapshot)

    # Then: the trusted fixed identity is returned unchanged.
    assert result == identity


def test_preflight_cli_accepts_exactly_the_declared_flags(tmp_path: Path) -> None:
    # Given: the required flags plus one undeclared widening flag.
    assert PREFLIGHT.is_file(), "GitHub preflight CLI is not implemented"
    command = [
        sys.executable,
        str(PREFLIGHT),
        "--repository",
        "martyw1/IZ_clinical-notes-analyzer",
        "--repository-id",
        "1172715348",
        "--repository-node-id",
        "R_kgDOReY3VA",
        "--remote",
        "origin",
        "--expected-head",
        "8c1edc460c2af354f74417cf27d26abaf72ccc70",
        "--receipt",
        str(tmp_path / "receipt.json"),
        "--allow-local-remote",
    ]

    # When: the closed CLI parser receives the extra flag.
    completed = subprocess.run(command, cwd=REPOSITORY_ROOT, check=False, capture_output=True, text=True)

    # Then: it exits nonzero before any remote operation or receipt write.
    assert completed.returncode != 0
    assert not (tmp_path / "receipt.json").exists()
