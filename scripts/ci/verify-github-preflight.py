#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///

# ─── How to run ───
# 1. Install uv: https://docs.astral.sh/uv/getting-started/installation/
# 2. Run: uv run scripts/ci/verify-github-preflight.py --help
# 3. Or: python scripts/ci/verify-github-preflight.py --help
# ─────────────────

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Final, Sequence


CANONICAL_REPOSITORY: Final = "martyw1/IZ_clinical-notes-analyzer"
CANONICAL_REPOSITORY_ID: Final = 1172715348
CANONICAL_REPOSITORY_NODE_ID: Final = "R_kgDOReY3VA"


@dataclass(frozen=True, slots=True)
class GitHubPreflightError(Exception):
    reason: str

    def __str__(self) -> str:
        return self.reason


@dataclass(frozen=True, slots=True)
class RepositoryIdentity:
    repository: str
    repository_id: int
    repository_node_id: str


@dataclass(frozen=True, slots=True)
class RepositorySnapshot:
    repository_id: int
    repository_node_id: str
    default_branch: str
    actions_enabled: bool
    can_push: bool


def parse_repository_identity(repository: str, id_raw: str, node_raw: str) -> RepositoryIdentity:
    if repository != CANONICAL_REPOSITORY:
        raise GitHubPreflightError("repository does not match the canonical repository")
    if not re.fullmatch(r"[0-9]+", id_raw):
        raise GitHubPreflightError("numeric repository ID is not a decimal integer")
    repository_id = int(id_raw)
    if repository_id != CANONICAL_REPOSITORY_ID:
        raise GitHubPreflightError("numeric repository ID does not match the canonical repository")
    if node_raw != CANONICAL_REPOSITORY_NODE_ID:
        raise GitHubPreflightError("repository node ID does not match the canonical repository")
    return RepositoryIdentity(repository, repository_id, node_raw)


def validate_remote_url(repository: str, url: str) -> str:
    escaped = re.escape(repository)
    accepted = (
        rf"git@github\.com:{escaped}\.git",
        rf"ssh://git@github\.com/{escaped}(?:\.git)?",
        rf"https://github\.com/{escaped}(?:\.git)?",
    )
    if not any(re.fullmatch(pattern, url) for pattern in accepted):
        raise GitHubPreflightError("remote URL is local, credential-bearing, or names another repository")
    return url


def verify_repository_snapshot(identity: RepositoryIdentity, snapshot: RepositorySnapshot) -> RepositoryIdentity:
    if snapshot.repository_id != identity.repository_id:
        raise GitHubPreflightError("API numeric repository ID differs")
    if snapshot.repository_node_id != identity.repository_node_id:
        raise GitHubPreflightError("API repository node ID differs")
    if snapshot.default_branch != "main" or not snapshot.actions_enabled or not snapshot.can_push:
        raise GitHubPreflightError("default branch, Actions state, or authenticated write permission differs")
    return identity


def require_deleted_ref(ref: str, output: str) -> None:
    if output.strip():
        raise GitHubPreflightError(f"cleanup did not delete exact nonce ref {ref}")


def _run(command: Sequence[str], *, binary: bool = False) -> str | bytes:
    completed = subprocess.run(command, check=False, capture_output=True, text=not binary)
    if completed.returncode != 0:
        raise GitHubPreflightError(f"command failed: {command[0]} {command[1] if len(command) > 1 else ''}".rstrip())
    return completed.stdout


def _api_json(path: str) -> dict[str, object]:
    output = _run(("gh", "api", path))
    try:
        payload = json.loads(str(output))
    except json.JSONDecodeError as exc:
        raise GitHubPreflightError("GitHub API returned invalid JSON") from exc
    if not isinstance(payload, dict):
        raise GitHubPreflightError("GitHub API response is not an object")
    return payload


def _write_private(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(8)}.tmp")
    data = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def execute(args: argparse.Namespace) -> dict[str, object]:
    identity = parse_repository_identity(args.repository, args.repository_id, args.repository_node_id)
    if not re.fullmatch(r"[0-9a-f]{40}", args.expected_head):
        raise GitHubPreflightError("expected HEAD must be a full lowercase commit SHA")
    head = str(_run(("git", "rev-parse", "HEAD"))).strip()
    if head != args.expected_head:
        raise GitHubPreflightError("expected HEAD differs from the checked-out commit")
    remote_url = str(_run(("git", "remote", "get-url", args.remote))).strip()
    validate_remote_url(identity.repository, remote_url)
    repository = _api_json(f"repos/{identity.repository}")
    permissions = repository.get("permissions")
    actions = _api_json(f"repos/{identity.repository}/actions/permissions")
    snapshot = RepositorySnapshot(
        repository_id=repository.get("id") if isinstance(repository.get("id"), int) else -1,
        repository_node_id=str(repository.get("node_id", "")),
        default_branch=str(repository.get("default_branch", "")),
        actions_enabled=actions.get("enabled") is True,
        can_push=isinstance(permissions, dict) and permissions.get("push") is True,
    )
    verify_repository_snapshot(identity, snapshot)
    nonce_ref = f"refs/heads/codex-native/preflight-{secrets.token_hex(16)}"
    resolved = ""
    deleted = False
    try:
        _run(("git", "push", args.remote, f"{head}:{nonce_ref}"))
        resolved = str(_run(("git", "ls-remote", "--refs", args.remote, nonce_ref))).strip()
        if resolved != f"{head}\t{nonce_ref}":
            raise GitHubPreflightError("nonce ref did not resolve to the exact expected HEAD")
    finally:
        try:
            _run(("git", "push", args.remote, f":{nonce_ref}"))
            remaining = str(_run(("git", "ls-remote", "--refs", args.remote, nonce_ref)))
            require_deleted_ref(nonce_ref, remaining)
            deleted = True
        except GitHubPreflightError:
            deleted = False
    if not deleted:
        raise GitHubPreflightError("cleanup could not independently confirm nonce ref deletion")
    receipt = {
        "schema": "iz-github-preflight-v1", "result": "PASS", **asdict(identity),
        "default_branch": snapshot.default_branch, "actions_enabled": snapshot.actions_enabled,
        "can_push": snapshot.can_push, "remote": args.remote, "remote_url": remote_url,
        "expected_head": head, "nonce_ref": nonce_ref, "nonce_sha": resolved.split("\t", 1)[0],
        "nonce_ref_deleted": deleted,
    }
    _write_private(args.receipt, receipt)
    return receipt


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify the fixed GitHub execution identity")
    parser.add_argument("--repository", required=True)
    parser.add_argument("--repository-id", required=True)
    parser.add_argument("--repository-node-id", required=True)
    parser.add_argument("--remote", required=True)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--receipt", required=True, type=Path)
    return parser


def main() -> int:
    try:
        receipt = execute(_parser().parse_args())
    except GitHubPreflightError as exc:
        print(f"GitHub preflight failed: {exc}", file=sys.stderr)
        return 1
    print(f"GitHub preflight PASS: id={receipt['repository_id']} node_id={receipt['repository_node_id']} cleanup=true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
