#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///

# ─── How to run ───
# 1. Install uv: https://docs.astral.sh/uv/getting-started/installation/
# 2. Run: uv run scripts/verification/render_plan_contract.py --help
# 3. Or: python scripts/verification/render_plan_contract.py --help
# ─────────────────

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Final


PLAN_CONTRACT_PATH: Final = Path("config/verification/cross-platform-plan-contract.json")
TASK_GRAPH_PATH: Final = Path("config/verification/lane1-task-graph.json")
LANE2_SCOPE_PATH: Final = Path("config/performance/lane2-scope.json")
CANONICAL_REPOSITORY: Final = "martyw1/IZ_clinical-notes-analyzer"
CANONICAL_REPOSITORY_ID: Final = 1172715348
BASE_REF: Final = "8c1edc460c2af354f74417cf27d26abaf72ccc70"
IMMUTABLE_POLICY_PATHS: Final = (
    "config/verification/approved-cross-platform-plan.md", "scripts/verification/render_plan_contract.py",
    PLAN_CONTRACT_PATH.as_posix(), TASK_GRAPH_PATH.as_posix(), LANE2_SCOPE_PATH.as_posix(),
)
GIT_POLICY_TEXT: Final = (
    "- Git object policy: every Task 1-36 Commit path denotes one regular Git blob and no task may delete or rename a listed path. "
    "A path already tracked at base `8c1edc460c2af354f74417cf27d26abaf72ccc70` must preserve its base object type and mode exactly. "
    "A new path ending in `.sh` must be blob mode `100755`; every other new path must be blob mode `100644`. Source-tree symlinks "
    "(`120000`), submodules/gitlinks (`160000`), directories represented as placeholders, hard-link aliases, case/NFC aliases, and any "
    "unlisted rename/copy/delete are forbidden. Generated package-internal framework links and the DMG `Applications` link are "
    "artifact-manifest entries governed by Task 6, never tracked Git links. Task 1 renders these literal rules once; later validators "
    "compare raw `git diff-tree --raw -z`/`git ls-tree -rz` objects and never infer a mode from the local filesystem, `core.filemode`, "
    "extension beyond this rule, or platform defaults."
)


@dataclass(frozen=True, slots=True)
class PlanContractError(Exception):
    reason: str

    def __str__(self) -> str:
        return self.reason


@dataclass(frozen=True, slots=True)
class RenderRequest:
    approved_plan: Path
    approved_plan_sha256: str
    repository: str
    repository_id: int
    base_ref: str
    output_dir: Path


@dataclass(frozen=True, slots=True)
class RenderedContracts:
    plan_contract: Path
    task_graph: Path
    lane2_scope: Path


def _canonical(payload: dict[str, object]) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode()


def _task_blocks(text: str) -> dict[int, tuple[str, str]]:
    matches = tuple(re.finditer(r"(?m)^- \[ \] (\d+)\. (.+)$", text))
    if tuple(int(item.group(1)) for item in matches) != tuple(range(1, 37)):
        raise PlanContractError("approved plan must contain exactly the ordered Task 1-36 headings")
    blocks: dict[int, tuple[str, str]] = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else text.index("\n## Final verification wave", match.end())
        blocks[int(match.group(1))] = (match.group(2).strip(), text[match.start() : end])
    return blocks


def _expand_nodes(raw: str) -> tuple[int | str, ...]:
    value = raw.strip().removeprefix("[").removesuffix("]")
    if value == "none":
        return ()
    nodes: list[int | str] = []
    for token in (item.strip() for item in value.split(",")):
        range_match = re.fullmatch(r"(F?)(\d+)-(?:F)?(\d+)", token)
        if range_match:
            prefix, first, last = range_match.groups()
            nodes.extend(f"F{number}" if prefix else number for number in range(int(first), int(last) + 1))
        elif re.fullmatch(r"F\d+", token):
            nodes.append(token)
        elif token.isdigit():
            nodes.append(int(token))
        else:
            raise PlanContractError(f"unparsed dependency token: {token}")
    if len(nodes) != len(set(nodes)):
        raise PlanContractError(f"duplicate dependency token in: {raw}")
    return tuple(nodes)


def _matrix(text: str) -> dict[int, tuple[tuple[int | str, ...], tuple[int | str, ...], tuple[int | str, ...]]]:
    rows: dict[int, tuple[tuple[int | str, ...], tuple[int | str, ...], tuple[int | str, ...]]] = {}
    for match in re.finditer(r"(?m)^\| (\d+) \| ([^|]+) \| ([^|]+) \| ([^|]+) \|$", text):
        task_id = int(match.group(1))
        if task_id in rows:
            raise PlanContractError(f"duplicate dependency-matrix row for Task {task_id}")
        rows[task_id] = tuple(_expand_nodes(match.group(index)) for index in range(2, 5))
    if tuple(sorted(rows)) != tuple(range(1, 37)):
        raise PlanContractError("dependency matrix must contain exactly Tasks 1-36")
    return rows


def _base_tree(base_ref: str) -> dict[str, tuple[str, str]]:
    completed = subprocess.run(["git", "ls-tree", "-rz", "--full-tree", base_ref], check=False, capture_output=True)
    if completed.returncode != 0:
        raise PlanContractError(f"base ref is unavailable: {base_ref}")
    tree: dict[str, tuple[str, str]] = {}
    for record in completed.stdout.split(b"\0"):
        if not record:
            continue
        metadata, raw_path = record.split(b"\t", 1)
        mode, object_type, _sha = metadata.decode().split(" ", 2)
        tree[raw_path.decode("utf-8")] = (mode, object_type)
    return tree


def _validate_path(path: str, aliases: dict[str, str]) -> None:
    pure = PurePosixPath(path)
    if pure.is_absolute() or path != pure.as_posix() or any(part in {"", ".", ".."} for part in pure.parts):
        raise PlanContractError(f"invalid exact Commit path: {path}")
    if any(marker in path for marker in ("*", "?", "[", "]", "{", "}", "\\")) or path.endswith("/"):
        raise PlanContractError(f"wildcard, prefix, or non-POSIX Commit path: {path}")
    alias_key = unicodedata.normalize("NFC", path).casefold()
    previous = aliases.setdefault(alias_key, path)
    if previous != path:
        raise PlanContractError(f"case/NFC alias paths are forbidden: {previous}, {path}")


def _path_policy(path: str, base_tree: dict[str, tuple[str, str]], aliases: dict[str, str]) -> dict[str, object]:
    _validate_path(path, aliases)
    tracked = base_tree.get(path)
    if tracked is not None:
        mode, object_type = tracked
        if object_type != "blob" or mode not in {"100644", "100755"}:
            raise PlanContractError(f"base path is not a regular Git blob: {path}")
    else:
        mode, object_type = ("100755" if path.endswith(".sh") else "100644"), "blob"
    return {"base_tracked": tracked is not None, "mode": mode, "object_type": object_type, "path": path}


def _commit_alternatives(task_id: int, block: str) -> tuple[tuple[str, str, tuple[str, ...]], ...]:
    line_match = re.search(r"(?m)^  Commit: YES \| Message: (.+) \| Files: \[(.+)\]$", block)
    if line_match is None:
        raise PlanContractError(f"Task {task_id} is missing an exact Commit field")
    message, files_field = line_match.groups()
    paths = tuple(re.findall(r"`([^`]+)`", files_field))
    if not paths or len(paths) != len(set(paths)):
        raise PlanContractError(f"Task {task_id} has missing or duplicate Commit paths")
    conditional = re.fullmatch(r"`([^`]+)` if accepted, otherwise `([^`]+)`", message)
    if conditional is None:
        subject = re.fullmatch(r"`([^`]+)`", message)
        if subject is None:
            raise PlanContractError(f"Task {task_id} has an unparsed Commit subject")
        return (("REQUIRED", subject.group(1), paths),)
    if task_id not in {32, 33, 34, 35} or "; accepted only:" not in files_field:
        raise PlanContractError(f"Task {task_id} has an unexpected conditional delta")
    accepted_subject, rejected_subject = conditional.groups()
    outcomes = ("REJECTED", "ACCEPTED") if task_id == 33 else ("NOT_MATERIAL", "REJECTED", "ACCEPTED")
    return tuple((outcome, accepted_subject if outcome == "ACCEPTED" else rejected_subject,
                  paths if outcome == "ACCEPTED" else paths[:1]) for outcome in outcomes)


def _expand_braces(value: str) -> tuple[str, ...]:
    match = re.search(r"\{([^{}]+)\}", value)
    if match is None:
        return (value,)
    return tuple(expanded for option in match.group(1).split(",")
                 for expanded in _expand_braces(value[: match.start()] + option + value[match.end() :]))


def _evidence(block: str, task_id: int) -> tuple[tuple[str, ...], tuple[str, ...]]:
    descriptions = tuple(re.findall(r"(?m)^    Evidence: (.+)$", block))
    if not descriptions:
        raise PlanContractError(f"Task {task_id} has no Evidence IDs")
    identifiers: list[str] = []
    for description in descriptions:
        for match in re.findall(r"\$ATTEMPT_DIR/[^\s,;]+", description):
            identifiers.extend(_expand_braces(match.rstrip(".")))
    if not identifiers:
        raise PlanContractError(f"Task {task_id} Evidence IDs are unparsed")
    return descriptions, tuple(sorted(set(identifiers)))


def render(request: RenderRequest) -> RenderedContracts:
    plan_bytes = request.approved_plan.read_bytes()
    actual_hash = hashlib.sha256(plan_bytes).hexdigest()
    if actual_hash != request.approved_plan_sha256.lower():
        raise PlanContractError("approved plan SHA-256 does not match immutable handoff metadata")
    if not isinstance(request.repository_id, int) or isinstance(request.repository_id, bool):
        raise PlanContractError("repository ID must be a numeric JSON integer")
    text = plan_bytes.decode("utf-8")
    if text.count(GIT_POLICY_TEXT) != 1:
        raise PlanContractError("Git object policy is unparsed or duplicated")
    if (request.repository, request.repository_id, request.base_ref) != (CANONICAL_REPOSITORY, CANONICAL_REPOSITORY_ID, BASE_REF):
        raise PlanContractError("repository identity or base ref differs from the approved plan")
    blocks, matrix, base_tree = _task_blocks(text), _matrix(text), _base_tree(request.base_ref)
    aliases: dict[str, str] = {}
    tasks: list[dict[str, object]] = []
    graph_rows: list[dict[str, object]] = []
    for task_id, (heading, block) in blocks.items():
        parallel = re.search(r"(?m)^  Parallelization: Can parallel: (YES|NO) \| (.+) \| Blocked by: (.+) \| Blocks: (.+)$", block)
        if parallel is None:
            raise PlanContractError(f"Task {task_id} has no parsed Parallelization field")
        depends_on, blocks_list, parallel_with = matrix[task_id]
        if _expand_nodes(parallel.group(3)) != depends_on or _expand_nodes(parallel.group(4)) != blocks_list:
            raise PlanContractError(f"Task {task_id} contradicts its dependency-matrix row")
        alternatives = _commit_alternatives(task_id, block)
        rendered_alternatives = tuple({
            "outcome": outcome, "subject": subject,
            "paths": tuple(_path_policy(path, base_tree, aliases) for path in paths),
            "directory_entries": tuple({"directory": PurePosixPath(path).parent.as_posix(),
                                        "entry": PurePosixPath(path).name, "path": path} for path in paths),
        } for outcome, subject, paths in alternatives)
        descriptions, evidence_ids = _evidence(block, task_id)
        adversarial = re.search(r"(?m)^  Adversarial classes: (.+)\.$", block)
        if adversarial is None:
            raise PlanContractError(f"Task {task_id} has no adversarial-class field")
        tasks.append({"task_id": task_id, "heading": heading, "alternatives": rendered_alternatives,
                      "evidence_descriptions": descriptions, "evidence_ids": evidence_ids,
                      "adversarial_classes": tuple(re.findall(r"`([^`]+)`", adversarial.group(1)))})
        graph_rows.append({"task_id": task_id, "heading": heading, "can_parallel": parallel.group(1) == "YES",
                           "wave": parallel.group(2), "depends_on": depends_on,
                           "blocks": blocks_list, "parallel_with": parallel_with})
    inventory_lines = tuple(line.strip() for line in text.splitlines() if any(line.startswith(prefix) for prefix in (
        "  - Enumerate common source-to-destination", "  - Enumerate Windows generated destinations",
        "  - Enumerate macOS DMG roots")))
    if len(inventory_lines) != 3:
        raise PlanContractError("enumerated release directory entries are unparsed")
    source = {"approved_plan_sha256": actual_hash, "base_ref": request.base_ref,
              "repository": request.repository, "repository_id": request.repository_id}
    contract = {
        "schema": "iz-cross-platform-plan-contract-v1",
        "source": source,
        "immutable_policy_paths": IMMUTABLE_POLICY_PATHS,
        "git_object_policy": {"allowed_object_type": "blob", "allowed_existing_modes": ("100644", "100755"),
                              "existing_mode_rule": "preserve_base_exactly", "new_shell_mode": "100755",
                              "new_other_mode": "100644", "forbidden_change_types": ("copy", "delete", "rename"),
                              "forbidden_object_modes": ("040000", "120000", "160000"),
                              "forbidden_aliases": ("casefold", "hardlink", "nfc")},
        "enumerated_release_directory_contracts": inventory_lines,
        "tasks": tasks,
    }
    graph = {"schema": "iz-lane1-task-graph-v1", "source": source, "tasks": graph_rows}
    lane2 = {"schema": "iz-lane2-scope-v1", "source": source, "tasks": tuple(tasks[26:])}
    outputs = ((request.output_dir / PLAN_CONTRACT_PATH, contract), (request.output_dir / TASK_GRAPH_PATH, graph),
               (request.output_dir / LANE2_SCOPE_PATH, lane2))
    for path, payload in outputs:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(_canonical(payload))
    return RenderedContracts(*(path for path, _payload in outputs))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--approved-plan", type=Path, required=True)
    parser.add_argument("--approved-plan-sha256", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--repository-id", type=int, required=True)
    parser.add_argument("--base-ref", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        render(RenderRequest(args.approved_plan, args.approved_plan_sha256, args.repository, args.repository_id, args.base_ref, args.output_dir))
    except (OSError, UnicodeDecodeError, PlanContractError) as exc:
        print(f"plan contract render failed: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
