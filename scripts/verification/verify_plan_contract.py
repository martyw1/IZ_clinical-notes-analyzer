#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///

# ─── How to run ───
# 1. Install uv: https://docs.astral.sh/uv/getting-started/installation/
# 2. Run: uv run scripts/verification/verify_plan_contract.py --help
# 3. Or: python scripts/verification/verify_plan_contract.py --help
# ─────────────────

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
import unicodedata
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Final


TASK1_PATHS: Final = (
    "config/verification/approved-cross-platform-plan.md", "config/verification/cross-platform-plan-contract.json",
    "config/verification/lane1-task-graph.json", "config/performance/lane2-scope.json",
    "scripts/verification/render_plan_contract.py", "scripts/verification/verify_plan_contract.py",
    "scripts/ci/verify-github-preflight.py", "backend/tests/test_cross_platform_plan_contract.py",
    "backend/tests/test_github_execution_identity.py", "backend/tests/test_desktop_behavior_characterization.py",
    "backend/tests/fixtures/desktop_contract/routes.json", "backend/tests/fixtures/desktop_contract/safe-api-shapes.json",
    "backend/tests/fixtures/desktop_contract/resource-hashes.json", ".github/workflows/native-desktop-bootstrap.yml",
    "scripts/ci/dispatch-native-bootstrap.py", "scripts/ci/write-native-bootstrap-receipt.py",
    "backend/tests/test_native_bootstrap_receipt.py",
)
IMMUTABLE_PATHS: Final = (
    "config/verification/approved-cross-platform-plan.md", "scripts/verification/render_plan_contract.py",
    "config/verification/cross-platform-plan-contract.json", "config/verification/lane1-task-graph.json",
    "config/performance/lane2-scope.json",
)
GIT_POLICY: Final = {
    "allowed_object_type": "blob", "allowed_existing_modes": ["100644", "100755"],
    "existing_mode_rule": "preserve_base_exactly", "new_shell_mode": "100755", "new_other_mode": "100644",
    "forbidden_change_types": ["copy", "delete", "rename"],
    "forbidden_object_modes": ["040000", "120000", "160000"],
    "forbidden_aliases": ["casefold", "hardlink", "nfc"],
}
SOURCE_IDENTITY: Final = {
    "approved_plan_sha256": "f8a6bcafef1cb78bba94575095744d3d929ba0a4922dc67088f37b80ceb2be8e",
    "base_ref": "8c1edc460c2af354f74417cf27d26abaf72ccc70",
    "repository": "martyw1/IZ_clinical-notes-analyzer",
    "repository_id": 1172715348,
}


@dataclass(frozen=True, slots=True)
class PlanValidationError(Exception):
    reason: str

    def __str__(self) -> str:
        return self.reason


@dataclass(frozen=True, slots=True)
class GitDelta:
    path: str
    status: str
    old_mode: str
    new_mode: str
    old_type: str
    new_type: str


@dataclass(frozen=True, slots=True)
class ValidationRequest:
    execution_contract: Path
    approved_plan: Path
    approved_plan_sha256: str
    renderer: Path
    plan_contract: Path
    task_graph: Path
    lane2_scope: Path
    git_ref: str
    output: Path


def _load(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PlanValidationError(f"invalid JSON contract: {path}") from exc
    if not isinstance(payload, dict):
        raise PlanValidationError(f"JSON contract must be an object: {path}")
    return payload


def _tasks(payload: dict[str, object], count: int, label: str) -> list[dict[str, object]]:
    rows = payload.get("tasks")
    if not isinstance(rows, list) or len(rows) != count or any(not isinstance(row, dict) for row in rows):
        raise PlanValidationError(f"{label} must contain exactly {count} task objects")
    if [row.get("task_id") for row in rows] != list(range(37 - count, 37)):
        raise PlanValidationError(f"{label} task IDs are incomplete or unordered")
    return rows


def _alias_key(path: str) -> str:
    return unicodedata.normalize("NFC", path).casefold()


def validate_policy_bundle(plan_path: Path, graph_path: Path, scope_path: Path) -> None:
    plan, graph, scope = _load(plan_path), _load(graph_path), _load(scope_path)
    if plan.get("schema") != "iz-cross-platform-plan-contract-v1" or graph.get("schema") != "iz-lane1-task-graph-v1" or scope.get("schema") != "iz-lane2-scope-v1":
        raise PlanValidationError("policy schema mismatch")
    if plan.get("source") != graph.get("source") or plan.get("source") != scope.get("source"):
        raise PlanValidationError("policy source identities differ")
    if plan.get("source") != SOURCE_IDENTITY:
        raise PlanValidationError("policy source identity differs from the approved anchor")
    if plan.get("git_object_policy") != GIT_POLICY:
        raise PlanValidationError("literal global Git object policy differs")
    if plan.get("immutable_policy_paths") != list(IMMUTABLE_PATHS):
        raise PlanValidationError("immutable policy path inventory differs")
    plan_tasks, graph_tasks, scope_tasks = _tasks(plan, 36, "plan contract"), _tasks(graph, 36, "task graph"), _tasks(scope, 10, "Lane-2 scope")
    expected_outcomes = {32: ["NOT_MATERIAL", "REJECTED", "ACCEPTED"], 33: ["REJECTED", "ACCEPTED"],
                         34: ["NOT_MATERIAL", "REJECTED", "ACCEPTED"], 35: ["NOT_MATERIAL", "REJECTED", "ACCEPTED"]}
    for row in scope_tasks:
        task_id, alternatives = row.get("task_id"), row.get("alternatives")
        if not isinstance(task_id, int) or not isinstance(alternatives, list):
            raise PlanValidationError("Lane-2 task alternatives are malformed")
        if [item.get("outcome") for item in alternatives if isinstance(item, dict)] != expected_outcomes.get(task_id, ["REQUIRED"]):
            raise PlanValidationError(f"Task {task_id} outcome alternatives differ")
        if any(not isinstance(item, dict) or not isinstance(item.get("subject"), str) or not item["subject"] for item in alternatives):
            raise PlanValidationError(f"Task {task_id} outcome subject is missing")
    if scope_tasks != plan_tasks[26:]:
        raise PlanValidationError("Lane-2 scope does not match the anchored plan contract")
    aliases: dict[str, str] = {}
    for row in plan_tasks:
        task_id, alternatives = row.get("task_id"), row.get("alternatives")
        if not isinstance(task_id, int) or not isinstance(alternatives, list):
            raise PlanValidationError("task alternatives are malformed")
        outcomes = [alternative.get("outcome") for alternative in alternatives if isinstance(alternative, dict)]
        if outcomes != expected_outcomes.get(task_id, ["REQUIRED"]):
            raise PlanValidationError(f"Task {task_id} outcome alternatives differ")
        for alternative in alternatives:
            if not isinstance(alternative, dict) or not isinstance(alternative.get("subject"), str) or not alternative["subject"]:
                raise PlanValidationError(f"Task {task_id} outcome subject is missing")
            paths, entries = alternative.get("paths"), alternative.get("directory_entries")
            if isinstance(paths, list) and task_id > 1 and any(
                isinstance(policy, dict) and policy.get("path") in IMMUTABLE_PATHS for policy in paths
            ):
                raise PlanValidationError(f"Task {task_id} attempts immutable policy self-amendment")
            if not isinstance(paths, list) or not isinstance(entries, list) or len(paths) != len(entries):
                raise PlanValidationError(f"Task {task_id} directory entries differ from paths")
            for policy, entry in zip(paths, entries, strict=True):
                if not isinstance(policy, dict) or not isinstance(entry, dict) or not isinstance(policy.get("path"), str):
                    raise PlanValidationError(f"Task {task_id} path policy is malformed")
                path = policy["path"]
                if entry != {"directory": PurePosixPath(path).parent.as_posix(), "entry": PurePosixPath(path).name, "path": path}:
                    raise PlanValidationError(f"Task {task_id} directory entry is not exact")
                if any(marker in path for marker in ("*", "?", "[", "]", "{", "}", "\\")):
                    raise PlanValidationError(f"Task {task_id} contains a wildcard or alias path")
                previous = aliases.setdefault(_alias_key(path), path)
                if previous != path:
                    raise PlanValidationError(f"case/NFC alias: {previous}, {path}")
    for row in graph_tasks:
        task_id, depends, blocks, parallel = row["task_id"], row.get("depends_on"), row.get("blocks"), row.get("parallel_with")
        if not all(isinstance(value, list) for value in (depends, blocks, parallel)):
            raise PlanValidationError(f"Task {task_id} graph fields are malformed")
        for dependency in (value for value in depends if isinstance(value, int)):
            if not 1 <= dependency <= len(graph_tasks) or task_id not in graph_tasks[dependency - 1]["blocks"]:
                raise PlanValidationError(f"Task {task_id} graph inverse dependency differs")
        for blocked in (value for value in blocks if isinstance(value, int)):
            if not 1 <= blocked <= len(graph_tasks) or task_id not in graph_tasks[blocked - 1]["depends_on"]:
                raise PlanValidationError(f"Task {task_id} graph inverse block differs")


def expected_task_entries(plan_contract: Path, task_id: int, outcome: str) -> tuple[GitDelta, ...]:
    tasks = _tasks(_load(plan_contract), 36, "plan contract")
    alternatives = tasks[task_id - 1]["alternatives"]
    selected = next((item for item in alternatives if item.get("outcome") == outcome), None)
    if selected is None:
        raise PlanValidationError(f"Task {task_id} has no outcome {outcome}")
    return tuple(
        GitDelta(policy["path"], "M" if policy["base_tracked"] else "A",
                 policy["mode"] if policy["base_tracked"] else "000000", policy["mode"],
                 policy["object_type"] if policy["base_tracked"] else "missing", policy["object_type"])
        for policy in selected["paths"]
    )


def validate_observed_entries(expected: tuple[GitDelta, ...], observed: tuple[GitDelta, ...]) -> None:
    expected_map, observed_map = {item.path: item for item in expected}, {item.path: item for item in observed}
    if len(expected_map) != len(expected) or len(observed_map) != len(observed) or expected_map.keys() != observed_map.keys():
        raise PlanValidationError("unlisted, duplicate, renamed, or deleted Git path")
    aliases: dict[str, str] = {}
    for path, entry in observed_map.items():
        previous = aliases.setdefault(_alias_key(path), path)
        if previous != path or entry != expected_map[path]:
            raise PlanValidationError(f"Git type/mode/status/alias mismatch: {path}")
        if entry.status not in {"A", "M"} or entry.new_type != "blob" or entry.new_mode not in {"100644", "100755"}:
            raise PlanValidationError(f"forbidden Git object or change type: {path}")


def _mode_type(mode: str) -> str:
    if mode == "000000":
        return "missing"
    if mode == "160000":
        return "commit"
    if mode == "040000":
        return "tree"
    return "blob"


def _git_delta(base_ref: str, git_ref: str) -> tuple[GitDelta, ...]:
    completed = subprocess.run(["git", "diff-tree", "--raw", "-z", "--no-commit-id", "-r", "-M", "-C", base_ref, git_ref], check=True, capture_output=True)
    records, entries, index = completed.stdout.split(b"\0"), [], 0
    while index < len(records) and records[index]:
        metadata, path = records[index].decode().split(), records[index + 1].decode("utf-8")
        old_mode, new_mode, status = metadata[0][1:], metadata[1], metadata[4]
        if status[0] in {"R", "C"}:
            index += 1
            path = records[index + 1].decode("utf-8")
        entries.append(GitDelta(path, status[0], old_mode, new_mode, _mode_type(old_mode), _mode_type(new_mode)))
        index += 2
    return tuple(entries)


def validate(request: ValidationRequest) -> dict[str, object]:
    execution = _load(request.execution_contract)
    plan_hash = hashlib.sha256(request.approved_plan.read_bytes()).hexdigest()
    if plan_hash != request.approved_plan_sha256.lower() or execution.get("approved_plan_sha256") != plan_hash:
        raise PlanValidationError("approved plan external/tracked hash mismatch")
    if execution.get("repository") != "martyw1/IZ_clinical-notes-analyzer" or execution.get("repository_id") != 1172715348 or execution.get("repository_node_id") != "R_kgDOReY3VA":
        raise PlanValidationError("execution repository identity mismatch")
    validate_policy_bundle(request.plan_contract, request.task_graph, request.lane2_scope)
    source = _load(request.plan_contract)["source"]
    with tempfile.TemporaryDirectory(prefix="iz-plan-contract-") as raw_temp:
        command = [sys.executable, str(request.renderer), "--approved-plan", str(request.approved_plan),
                   "--approved-plan-sha256", request.approved_plan_sha256, "--repository", source["repository"],
                   "--repository-id", str(source["repository_id"]), "--base-ref", source["base_ref"], "--output-dir", raw_temp]
        subprocess.run(command, check=True)
        for committed in (request.plan_contract, request.task_graph, request.lane2_scope):
            rerendered = Path(raw_temp) / committed.as_posix()
            if rerendered.read_bytes() != committed.read_bytes():
                raise PlanValidationError(f"private rerender differs: {committed}")
    count = subprocess.run(["git", "rev-list", "--count", f"{source['base_ref']}..{request.git_ref}"], check=True, capture_output=True, text=True).stdout.strip()
    if count != "1":
        raise PlanValidationError("Task 1 must be exactly one commit after the anchored base")
    expected = expected_task_entries(request.plan_contract, 1, "REQUIRED")
    if tuple(item.path for item in expected) != TASK1_PATHS:
        raise PlanValidationError("Task 1 exact path inventory differs")
    validate_observed_entries(expected, _git_delta(source["base_ref"], request.git_ref))
    tracked_plan = subprocess.run(["git", "show", f"{request.git_ref}:{IMMUTABLE_PATHS[0]}"], check=True, capture_output=True).stdout
    if hashlib.sha256(tracked_plan).hexdigest() != plan_hash:
        raise PlanValidationError("Task 1 tracked approved-plan blob differs from external anchor")
    return {"schema": "iz-plan-policy-validation-v1", "result": "PASS", "git_ref": request.git_ref,
            "approved_plan_sha256": plan_hash, "task_count": 36, "lane2_task_count": 10,
            "task1_paths": list(TASK1_PATHS)}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    for name in ("execution-contract", "approved-plan", "renderer", "plan-contract", "task-graph", "lane2-scope", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--approved-plan-sha256", required=True)
    parser.add_argument("--git-ref", required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    request = ValidationRequest(args.execution_contract, args.approved_plan, args.approved_plan_sha256, args.renderer,
                                args.plan_contract, args.task_graph, args.lane2_scope, args.git_ref, args.output)
    try:
        receipt = validate(request)
        request.output.parent.mkdir(parents=True, exist_ok=True)
        request.output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        request.output.chmod(0o600)
    except (OSError, KeyError, StopIteration, subprocess.CalledProcessError, PlanValidationError) as exc:
        print(f"plan contract validation failed: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
