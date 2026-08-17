#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///

# ─── How to run ───
# 1. Install uv: https://docs.astral.sh/uv/getting-started/installation/
# 2. Run: uv run scripts/ci/dispatch-native-bootstrap.py --help
# 3. Or: python scripts/ci/dispatch-native-bootstrap.py --help
# ─────────────────

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import secrets
import subprocess
import sys
import tempfile
import time
import zipfile
from dataclasses import asdict, dataclass, replace
from io import BytesIO
from pathlib import Path, PurePosixPath
from types import ModuleType
from typing import Final, Sequence


CANONICAL_REPOSITORY, CANONICAL_REPOSITORY_ID, CANONICAL_REPOSITORY_NODE_ID, WORKFLOW_PATH = "martyw1/IZ_clinical-notes-analyzer", 1172715348, "R_kgDOReY3VA", ".github/workflows/native-desktop-bootstrap.yml"
ROOT = Path(__file__).resolve().parents[2]


class NativeBootstrapDispatchError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class WorkflowRun:
    run_id: int
    repository_id: int
    trigger_sha: str
    branch: str
    display_title: str


@dataclass(frozen=True, slots=True)
class DispatchCleanup:
    source_ref_deleted: bool
    trigger_ref_deleted: bool
    worktree_removed: bool


def _writer() -> ModuleType:
    if "task1_native_receipt_contract" in sys.modules:
        return sys.modules["task1_native_receipt_contract"]
    path = Path(__file__).with_name("write-native-bootstrap-receipt.py")
    spec = importlib.util.spec_from_file_location("task1_native_receipt_contract", path)
    if spec is None or spec.loader is None:
        raise NativeBootstrapDispatchError("native receipt validator cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules["task1_native_receipt_contract"] = module
    spec.loader.exec_module(module)
    return module


def select_matching_run(runs: Sequence[WorkflowRun], repository_id: int, trigger_sha: str, correlation_id: str) -> WorkflowRun:
    matches = tuple(run for run in runs if run.repository_id == repository_id and run.trigger_sha == trigger_sha
                    and run.branch == f"codex-native/{correlation_id}/trigger"
                    and run.display_title == f"ci(native-bootstrap): {correlation_id}")
    if len(matches) != 1:
        raise NativeBootstrapDispatchError("exact correlated push workflow run was not unique")
    return matches[0]


def verify_artifact_digest(api_digest: str, archive: bytes) -> str:
    actual = hashlib.sha256(archive).hexdigest()
    if api_digest != f"sha256:{actual}":
        raise NativeBootstrapDispatchError("artifact API digest differs from downloaded archive")
    return actual


def validate_collection(receipts: Sequence[dict[str, object]], cleanup: DispatchCleanup, expected: object) -> None:
    if cleanup != DispatchCleanup(True, True, True):
        raise NativeBootstrapDispatchError("native bootstrap cleanup is incomplete")
    writer = _writer()
    by_os = {str(receipt.get("runner", {}).get("target_os")): receipt for receipt in receipts
             if isinstance(receipt.get("runner"), dict)}
    if by_os.keys() != {"windows", "macos"} or len(receipts) != 2:
        raise NativeBootstrapDispatchError("native receipt platform inventory differs")
    for target_os in ("windows", "macos"):
        writer.validate_receipt(by_os[target_os], replace(expected, target_os=target_os))


def require_clean_worktree(status: str) -> None:
    if status.strip():
        raise NativeBootstrapDispatchError("dirty worktree cannot publish a native bootstrap request")


def remove_worktree(checkout: Path, temporary_root: Path) -> bool:
    if checkout.exists():
        try:
            _run(("git", "worktree", "remove", "--force", str(checkout)))
        except NativeBootstrapDispatchError:
            if checkout.exists():
                return False
    try:
        temporary_root.rmdir()
    except OSError:
        return False
    return not checkout.exists() and not temporary_root.exists()


def _run(command: Sequence[str], *, cwd: Path = ROOT) -> str:
    completed = subprocess.run(command, cwd=cwd, check=False, capture_output=True, text=True)
    if completed.returncode != 0:
        raise NativeBootstrapDispatchError(f"command failed: {command[0]} {command[1] if len(command) > 1 else ''}".rstrip())
    return completed.stdout


def _bytes(command: Sequence[str]) -> bytes:
    completed = subprocess.run(command, cwd=ROOT, check=False, capture_output=True)
    if completed.returncode != 0:
        raise NativeBootstrapDispatchError("artifact download failed")
    return completed.stdout


def _api(path: str) -> dict[str, object]:
    try:
        payload = json.loads(_run(("gh", "api", path)))
    except json.JSONDecodeError as exc:
        raise NativeBootstrapDispatchError("GitHub API returned invalid JSON") from exc
    if not isinstance(payload, dict):
        raise NativeBootstrapDispatchError("GitHub API response is not an object")
    return payload


def _remote_sha(remote: str, ref: str) -> str:
    return _run(("git", "ls-remote", "--refs", remote, ref)).partition("\t")[0].strip()


def _delete_ref(remote: str, ref: str) -> bool:
    try:
        if _remote_sha(remote, ref):
            _run(("git", "push", remote, f":{ref}"))
        return _remote_sha(remote, ref) == ""
    except NativeBootstrapDispatchError:
        return False


def _wait_for_run(repository: str, repository_id: int, trigger_sha: str, correlation: str) -> WorkflowRun:
    deadline = time.monotonic() + 300
    while time.monotonic() < deadline:
        payload = _api(f"repos/{repository}/actions/runs?event=push&head_sha={trigger_sha}&per_page=100")
        rows = payload.get("workflow_runs")
        runs = tuple(
            WorkflowRun(int(row["id"]), int(row.get("repository", {}).get("id", -1)), str(row.get("head_sha", "")),
                        str(row.get("head_branch", "")), str(row.get("display_title", "")))
            for row in rows if isinstance(rows, list) and isinstance(row, dict) and row.get("path") == WORKFLOW_PATH
        ) if isinstance(rows, list) else ()
        if runs:
            try:
                return select_matching_run(runs, repository_id, trigger_sha, correlation)
            except NativeBootstrapDispatchError:
                pass
        time.sleep(5)
    raise NativeBootstrapDispatchError("timed out waiting for the exact correlated push run")


def _extract_artifact(repository: str, artifact: dict[str, object], destination: Path) -> tuple[dict[str, object], dict[str, object]]:
    artifact_id, api_digest = artifact.get("id"), artifact.get("digest")
    if not isinstance(artifact_id, int) or not isinstance(api_digest, str):
        raise NativeBootstrapDispatchError("artifact identity or API digest is missing")
    archive = _bytes(("gh", "api", f"repos/{repository}/actions/artifacts/{artifact_id}/zip"))
    archive_sha = verify_artifact_digest(api_digest, archive)
    with zipfile.ZipFile(BytesIO(archive)) as bundle:
        names = tuple(item.filename for item in bundle.infolist() if not item.is_dir())
        if set(names) != {"native-receipt.json", "native-junit.xml"} or any(PurePosixPath(name).is_absolute() or ".." in PurePosixPath(name).parts for name in names):
            raise NativeBootstrapDispatchError("artifact file inventory differs")
        receipt_bytes, junit_bytes = bundle.read("native-receipt.json"), bundle.read("native-junit.xml")
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "receipt.json").write_bytes(receipt_bytes)
    (destination / "junit.xml").write_bytes(junit_bytes)
    try:
        receipt = json.loads(receipt_bytes)
    except json.JSONDecodeError as exc:
        raise NativeBootstrapDispatchError("artifact receipt is invalid JSON") from exc
    if not isinstance(receipt, dict):
        raise NativeBootstrapDispatchError("artifact receipt is not an object")
    metadata = {"artifact_id": artifact_id, "api_digest": api_digest, "archive_sha256": archive_sha,
                "receipt_sha256": hashlib.sha256(receipt_bytes).hexdigest(),
                "junit_sha256": hashlib.sha256(junit_bytes).hexdigest()}
    return receipt, metadata


def _preflight(args: argparse.Namespace, output: Path) -> None:
    _run((sys.executable, str(ROOT / "scripts/ci/verify-github-preflight.py"), "--repository", args.repository,
          "--repository-id", str(args.repository_id), "--repository-node-id", CANONICAL_REPOSITORY_NODE_ID,
          "--remote", args.remote, "--expected-head", args.commit, "--receipt", str(output)))


def dispatch(args: argparse.Namespace) -> dict[str, object]:
    if args.repository != CANONICAL_REPOSITORY or args.repository_id != CANONICAL_REPOSITORY_ID:
        raise NativeBootstrapDispatchError("fixed repository identity differs")
    if not re.fullmatch(r"[0-9a-f]{40}", args.commit) or args.mode not in _writer().TASK1_MODES:
        raise NativeBootstrapDispatchError("commit or mode is not an exact Task-1 value")
    if _run(("git", "rev-parse", "HEAD")).strip() != args.commit:
        raise NativeBootstrapDispatchError("target commit is not the current HEAD")
    require_clean_worktree(_run(("git", "status", "--porcelain", "--untracked-files=normal")))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    _preflight(args, args.output_dir / "github-preflight.json")
    correlation, nonce = secrets.token_hex(16), secrets.token_hex(16)
    source_ref, trigger_ref = (f"refs/heads/codex-native/{correlation}/{suffix}" for suffix in ("source", "trigger"))
    failure: NativeBootstrapDispatchError | None = None
    receipts: list[dict[str, object]] = []
    artifact_metadata: dict[str, object] = {}
    trigger_sha, workflow_blob, request_hash, run_id = "", "", "", 0
    temporary_root = Path(tempfile.mkdtemp(prefix="iz-native-bootstrap-"))
    checkout = temporary_root / "checkout"
    try:
        try:
            _run(("git", "worktree", "add", "--detach", str(checkout), args.commit))
            _run(("git", "push", args.remote, f"{args.commit}:{source_ref}"))
            if _remote_sha(args.remote, source_ref) != args.commit:
                raise NativeBootstrapDispatchError("source ref did not resolve to target commit")
            workflow_blob = _run(("git", "rev-parse", f"{args.commit}:{WORKFLOW_PATH}")).strip()
            request = {"schema": "iz-native-bootstrap-request-v1", "repository": args.repository,
                       "repository_id": args.repository_id, "repository_node_id": CANONICAL_REPOSITORY_NODE_ID,
                       "correlation_id": correlation, "target_sha": args.commit, "workflow_path": WORKFLOW_PATH,
                       "workflow_blob_sha": workflow_blob, "mode": args.mode, "nonce": nonce}
            request_hash = hashlib.sha256(_writer().canonical_json_bytes(request)).hexdigest()
            request["request_sha256"] = request_hash
            request_path = checkout / ".ci/native-bootstrap-request.json"
            request_path.parent.mkdir(parents=True)
            request_path.write_bytes(_writer().canonical_json_bytes(request))
            _run(("git", "add", "--", ".ci/native-bootstrap-request.json"), cwd=checkout)
            _run(("git", "-c", "user.name=Codex Native Bootstrap", "-c", "user.email=codex-native@invalid.local",
                  "commit", "-m", f"ci(native-bootstrap): {correlation}"), cwd=checkout)
            trigger_sha = _run(("git", "rev-parse", "HEAD"), cwd=checkout).strip()
            _run(("git", "push", args.remote, f"{trigger_sha}:{trigger_ref}"))
            if _remote_sha(args.remote, trigger_ref) != trigger_sha:
                raise NativeBootstrapDispatchError("trigger ref did not resolve to trigger commit")
            run_id = _wait_for_run(args.repository, args.repository_id, trigger_sha, correlation).run_id
            _run(("gh", "run", "watch", str(run_id), "--repo", args.repository, "--exit-status"))
            artifacts = _api(f"repos/{args.repository}/actions/runs/{run_id}/artifacts").get("artifacts")
            if not isinstance(artifacts, list):
                raise NativeBootstrapDispatchError("workflow artifact inventory is missing")
            for target_os in ("windows", "macos"):
                matches = [item for item in artifacts if isinstance(item, dict) and item.get("name") == f"native-bootstrap-{target_os}" and item.get("expired") is False]
                if len(matches) != 1:
                    raise NativeBootstrapDispatchError(f"{target_os} artifact is not unique")
                receipt, metadata = _extract_artifact(args.repository, matches[0], args.output_dir / target_os)
                receipts.append(receipt)
                artifact_metadata[target_os] = metadata
        except (NativeBootstrapDispatchError, OSError, subprocess.SubprocessError, zipfile.BadZipFile) as exc:
            failure = exc if isinstance(exc, NativeBootstrapDispatchError) else NativeBootstrapDispatchError(type(exc).__name__)
    finally:
        trigger_deleted = _delete_ref(args.remote, trigger_ref)
        source_deleted = _delete_ref(args.remote, source_ref)
        worktree_removed = remove_worktree(checkout, temporary_root)
    cleanup = DispatchCleanup(source_deleted, trigger_deleted, worktree_removed)
    base = {"schema": "iz-native-bootstrap-collection-v1", "repository": args.repository,
            "repository_id": args.repository_id, "repository_node_id": CANONICAL_REPOSITORY_NODE_ID,
            "correlation_id": correlation, "target_sha": args.commit, "trigger_sha": trigger_sha,
            "source_ref": source_ref, "trigger_ref": trigger_ref, "workflow_path": WORKFLOW_PATH,
            "workflow_blob_sha": workflow_blob, "request_sha256": request_hash, "mode": args.mode,
            "run_id": run_id, "artifacts": artifact_metadata, "cleanup": asdict(cleanup)}
    if failure is not None or cleanup != DispatchCleanup(True, True, True):
        failed = {**base, "result": "FAIL", "failure": str(failure or NativeBootstrapDispatchError("cleanup incomplete"))}
        _writer().write_private_receipt(args.receipt, failed)
        raise failure or NativeBootstrapDispatchError("native bootstrap cleanup is incomplete")
    expected = _writer().ExpectedNativeReceipt(args.repository, args.repository_id, CANONICAL_REPOSITORY_NODE_ID,
                                               correlation, args.commit, trigger_sha, workflow_blob, request_hash,
                                               args.mode, "windows")
    validate_collection(receipts, cleanup, expected)
    collection = {**base, "result": "PASS"}
    _writer().write_private_receipt(args.receipt, collection)
    return collection


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Dispatch exact push-only native bootstrap jobs")
    parser.add_argument("--commit", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--repository-id", required=True, type=int)
    parser.add_argument("--remote", required=True)
    parser.add_argument("--mode", required=True)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--receipt", required=True, type=Path)
    return parser


def main() -> int:
    try:
        result = dispatch(_parser().parse_args())
    except NativeBootstrapDispatchError as exc:
        print(f"Native bootstrap dispatch failed: {exc}", file=sys.stderr)
        return 1
    print(f"Native bootstrap PASS: run_id={result['run_id']} cleanup=true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
