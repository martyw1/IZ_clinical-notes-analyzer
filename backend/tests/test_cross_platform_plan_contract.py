from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from types import ModuleType

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
APPROVED_PLAN = REPOSITORY_ROOT / ".omo" / "plans" / "cross-platform-desktop-refactor.md"
APPROVED_PLAN_SHA256 = "f8a6bcafef1cb78bba94575095744d3d929ba0a4922dc67088f37b80ceb2be8e"
BASE_REF = "8c1edc460c2af354f74417cf27d26abaf72ccc70"
RENDERER = REPOSITORY_ROOT / "scripts" / "verification" / "render_plan_contract.py"
VALIDATOR = REPOSITORY_ROOT / "scripts" / "verification" / "verify_plan_contract.py"


def _load_module(path: Path, name: str) -> ModuleType:
    assert path.is_file(), f"required contract boundary is not implemented: {path.name}"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _render(tmp_path: Path) -> tuple[ModuleType, object]:
    renderer = _load_module(RENDERER, "task1_render_plan_contract")
    request = renderer.RenderRequest(
        approved_plan=APPROVED_PLAN,
        approved_plan_sha256=APPROVED_PLAN_SHA256,
        repository="martyw1/IZ_clinical-notes-analyzer",
        repository_id=1172715348,
        base_ref=BASE_REF,
        output_dir=tmp_path,
    )
    return renderer, renderer.render(request)


def _policy_paths(rendered: object) -> tuple[Path, Path, Path]:
    return rendered.plan_contract, rendered.task_graph, rendered.lane2_scope


def test_approved_plan_hash_mismatch_is_rejected(tmp_path: Path) -> None:
    # Given: the immutable plan bytes paired with a forged external hash.
    renderer = _load_module(RENDERER, "task1_renderer_hash")
    request = renderer.RenderRequest(
        approved_plan=APPROVED_PLAN,
        approved_plan_sha256="0" * 64,
        repository="martyw1/IZ_clinical-notes-analyzer",
        repository_id=1172715348,
        base_ref=BASE_REF,
        output_dir=tmp_path,
    )

    # When/Then: hashing precedes parsing and no policy is emitted.
    with pytest.raises(renderer.PlanContractError, match="approved plan SHA-256"):
        renderer.render(request)
    assert tuple(tmp_path.rglob("*.json")) == ()


def test_renderer_omission_is_rejected(tmp_path: Path) -> None:
    # Given: plan bytes with one Task-36 Commit field removed and a matching supplied hash.
    renderer = _load_module(RENDERER, "task1_renderer_omission")
    forged_plan = tmp_path / "forged-plan.md"
    text = APPROVED_PLAN.read_text(encoding="utf-8")
    forged_plan.write_bytes(text.replace("  Commit: YES | Message: `perf(desktop): add final cross-platform certification`", "  Omitted: YES | Message: `perf(desktop): add final cross-platform certification`", 1).encode("utf-8"))
    supplied_hash = hashlib.sha256(forged_plan.read_bytes()).hexdigest()
    request = renderer.RenderRequest(forged_plan, supplied_hash, "martyw1/IZ_clinical-notes-analyzer", 1172715348, BASE_REF, tmp_path / "out")

    # When/Then: an unparsed required task field fails closed.
    with pytest.raises(renderer.PlanContractError, match="Task 36.*Commit"):
        renderer.render(request)


def test_renderer_rejects_unparsed_global_git_policy(tmp_path: Path) -> None:
    # Given: anchored-looking bytes whose new-shell mode rule was retrospectively weakened.
    renderer = _load_module(RENDERER, "task1_renderer_git_policy")
    forged_plan = tmp_path / "forged-plan.md"
    text = APPROVED_PLAN.read_text(encoding="utf-8")
    forged_plan.write_bytes(text.replace("A new path ending in `.sh` must be blob mode `100755`", "A new path ending in `.sh` must be blob mode `100644`", 1).encode())
    supplied_hash = hashlib.sha256(forged_plan.read_bytes()).hexdigest()

    # When/Then: policy text must be consumed rather than replaced with a default.
    with pytest.raises(renderer.PlanContractError, match="Git object policy"):
        renderer.render(renderer.RenderRequest(forged_plan, supplied_hash, "martyw1/IZ_clinical-notes-analyzer", 1172715348, BASE_REF, tmp_path / "out"))


def test_renderer_rejects_repository_identity_drift(tmp_path: Path) -> None:
    # Given: the exact approved bytes but caller-supplied identity for another repository.
    renderer = _load_module(RENDERER, "task1_renderer_repository_identity")

    # When/Then: caller inputs cannot replace the repository identity embedded in the anchor.
    with pytest.raises(renderer.PlanContractError, match="repository identity"):
        renderer.render(renderer.RenderRequest(APPROVED_PLAN, APPROVED_PLAN_SHA256, "other/repository", 1172715348, BASE_REF, tmp_path))


def test_rendered_policy_bundle_is_valid(tmp_path: Path) -> None:
    # Given: a deterministic render of the exact approved plan.
    _renderer, rendered = _render(tmp_path)
    validator = _load_module(VALIDATOR, "task1_validator_canonical_bundle")

    # When/Then: the independently implemented bundle checks accept its literal directional graph.
    validator.validate_policy_bundle(*_policy_paths(rendered))


@pytest.mark.parametrize(
    ("mutation", "error_match"),
    (
        ("widened_graph", "graph"),
        ("missing_outcome_subject", "subject"),
        ("task33_not_material", "Task 33"),
        ("policy_self_amendment", "immutable"),
    ),
    ids=("widened_graph", "missing_outcome_subject", "task33_not_material", "policy_self_amendment"),
)
def test_mutated_policy_bundle_is_rejected(tmp_path: Path, mutation: str, error_match: str) -> None:
    # Given: a byte-valid render whose machine policy is retrospectively broadened.
    _renderer, rendered = _render(tmp_path / "rendered")
    validator = _load_module(VALIDATOR, f"task1_validator_{mutation}")
    plan_path, graph_path, scope_path = _policy_paths(rendered)
    forged_root = tmp_path / mutation
    shutil.copytree(tmp_path / "rendered", forged_root)
    forged_plan = forged_root / plan_path.relative_to(tmp_path / "rendered")
    forged_graph = forged_root / graph_path.relative_to(tmp_path / "rendered")
    forged_scope = forged_root / scope_path.relative_to(tmp_path / "rendered")
    target = forged_graph if mutation == "widened_graph" else forged_scope if mutation in {"missing_outcome_subject", "task33_not_material"} else forged_plan
    payload = json.loads(target.read_text(encoding="utf-8"))
    if mutation == "widened_graph":
        payload["tasks"][25]["blocks"].append(99)
    elif mutation == "missing_outcome_subject":
        payload["tasks"][5]["alternatives"][0].pop("subject")
    elif mutation == "task33_not_material":
        payload["tasks"][6]["alternatives"].append(dict(payload["tasks"][6]["alternatives"][0], outcome="NOT_MATERIAL"))
    else:
        payload["tasks"][1]["alternatives"][0]["paths"].append(
            {"base_tracked": False, "mode": "100644", "object_type": "blob", "path": "scripts/verification/render_plan_contract.py"}
        )
    target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    # When/Then: independent bundle validation rejects the forged field.
    with pytest.raises(validator.PlanValidationError, match=error_match):
        validator.validate_policy_bundle(forged_plan, forged_graph, forged_scope)


def test_mutated_policy_source_identity_is_rejected(tmp_path: Path) -> None:
    # Given: all three rendered documents colluding on a different repository identity.
    _renderer, rendered = _render(tmp_path)
    validator = _load_module(VALIDATOR, "task1_validator_source_identity")
    paths = _policy_paths(rendered)
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["source"]["repository"] = "other/repository"
        payload["source"]["repository_id"] = 9
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    # When/Then: cross-file agreement cannot replace the anchored source identity.
    with pytest.raises(validator.PlanValidationError, match="source identity"):
        validator.validate_policy_bundle(*paths)


@pytest.mark.parametrize(
    ("mutation", "status", "path", "mode", "object_type"),
    (
        ("unlisted_nested", "A", "backend/tests/fixtures/desktop_contract/nested/extra.json", "100644", "blob"),
        ("mode_type", "A", "backend/tests/test_cross_platform_plan_contract.py", "100755", "blob"),
        ("new_shell_mode", "A", "synthetic-new.sh", "100644", "blob"),
        ("new_other_executable", "A", "synthetic-new.py", "100755", "blob"),
        ("rename_delete", "D", "config/verification/approved-cross-platform-plan.md", "000000", "missing"),
        ("symlink_gitlink", "A", "synthetic-link", "120000", "blob"),
        ("gitlink", "A", "synthetic-module", "160000", "commit"),
        ("unicode_alias", "A", "synthetic/cafe\u0301.json", "100644", "blob"),
        ("case_alias", "A", "CONFIG/verification/approved-cross-platform-plan.md", "100644", "blob"),
    ),
    ids=("unlisted_nested", "mode_type", "new_shell_mode", "new_other_executable", "rename_delete", "symlink", "gitlink", "unicode_alias", "case_alias"),
)
def test_invalid_git_delta_is_rejected(
    tmp_path: Path,
    mutation: str,
    status: str,
    path: str,
    mode: str,
    object_type: str,
) -> None:
    # Given: the exact Task-1 delta with one forged object/path mutation.
    _renderer, rendered = _render(tmp_path)
    validator = _load_module(VALIDATOR, f"task1_delta_{mutation}")
    expected = validator.expected_task_entries(rendered.plan_contract, 1, "REQUIRED")
    forged = list(expected)
    forged.append(validator.GitDelta(path, status, "000000", mode, "missing", object_type))
    if mutation == "mode_type":
        forged = [replace(item, new_mode=mode) if item.path == path else item for item in expected]

    # When/Then: raw Git-object validation cannot accept the altered delta.
    with pytest.raises(validator.PlanValidationError):
        validator.validate_observed_entries(expected, tuple(forged))


def test_renderer_cli_rejects_unknown_arguments(tmp_path: Path) -> None:
    # Given: the exact renderer CLI plus an undeclared argument.
    assert RENDERER.is_file(), "renderer CLI boundary is not implemented"
    command = [sys.executable, str(RENDERER), "--unexpected", str(tmp_path)]

    # When: argparse evaluates the unsupported surface.
    completed = subprocess.run(command, cwd=REPOSITORY_ROOT, check=False, capture_output=True, text=True)

    # Then: the closed argument contract exits nonzero without output policy files.
    assert completed.returncode != 0
    assert tuple(tmp_path.rglob("*.json")) == ()
