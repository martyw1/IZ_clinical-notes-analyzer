# S0 Repository Privacy Incident Record

Incident date: 2026-07-10

Status: **Active containment. Not remediated.**

2026-07-11 beta.2 release-readiness update: the credential rotation, downstream-copy disposition, history-remediation approval, and retention/legal-hold decisions remain open external incident gates. This metadata update does not alter incident status or authorize a rewrite, force push, or production release.

Scope: tracked clinical-export artifacts and a credential-pattern value retained in Git history/current repository metadata. This record contains metadata only. It does not contain clinical content, patient identifiers, original filenames, or the credential value.

## Preservation Baseline

The S0 baseline was captured from commit `2f2b656d2d13fca48c56ea6f33d63b83c2cd9d21` on branch `codex/v2-production-readiness` before any S1 removal. The worktree was clean. Evidence preservation did not open an export blob or working-tree export file.

### Tracked clinical-export exposure

| Metadata category | Count | Blob/object IDs and sizes in bytes |
|---|---:|---|
| `clinical-export.csv` | 3 | `3d9421c09e105ffa390ff928c6a754b9b7bf8a18` (17,221,041); `8330c56c5787f6f03ef4014e138e7a0466dd82ff` (17,017); `857bc65d3bb244c4811a118dc07f2e64d06b5304` (24,382) |
| `clinical-export.json` | 3 | `31a3e84f84e24403faa9b8b602c421831fb02cf3` (22,180); `8256a4a96ab456dc7fec031102e1eefa0d0a3aa6` (25,276,811); `834487cd94a8b1f55826435915433ca998cafe32` (155,287) |

The six object IDs above are the complete unique blob set found for this path category across the reachable local history at the baseline. The commits that touched the tracked export category are:

| Commit | Author date | Author metadata |
|---|---|---|
| `47762456c7003baf598dd0bad86f2089a6cec629` | `2026-07-09T13:53:24-04:00` | `R3 Developer Dell Laptop` |
| `8cca8d3590af34f84f83b683a50cb6e7cb28a196` | `2026-07-09T13:53:24-04:00` | `R3 Developer Dell Laptop` |

### Credential exposure metadata

A metadata-only high-confidence credential-pattern scan, excluding the clinical-export category, identified these commits:

| Commit | Parent | Author date | Change classification |
|---|---|---|---|
| `7f9553fb854a17e19ea1174cf4e1878cc7707d41` | `05155ed591698e3e7e2dd4e92652f6b3403594b3` | `2026-07-07T10:55:34-04:00` | First observed high-entropy credential assignments: 2 added lines in Python source metadata. |
| `47762456c7003baf598dd0bad86f2089a6cec629` | `7ff7108ed8a8b5b0878d5d74e0587cee945e3901` | `2026-07-09T13:53:24-04:00` | Later removal metadata: 4 removed high-entropy credential-assignment lines in Python source metadata. |

At the S0 baseline, the same high-entropy credential-assignment detector found zero current-tree matches outside the export category. That does not remediate reachable Git history and is not proof that the exposed credential is disabled.

## Mandatory Credential Rotation

The credential must be treated as compromised and rotated by the credential owner through the provider's approved administrative surface. Rotation evidence must record only:

- owner or accountable team;
- completion timestamp;
- provider-side key/version identifier that is safe to retain;
- confirmation that the old credential is disabled;
- confirmation that dependent approved systems were updated;
- reviewer and verification timestamp.

The old or replacement credential value must never be placed in Git, issue trackers, chat, screenshots, logs, evidence, or this record. S0 is not remediated until rotation and disablement are independently confirmed.

## Clone, Artifact, And Downstream-Owner Inventory

The baseline found two local Git worktrees, one configured remote, and no files or installer/archive artifacts under the local `dist` directory. Counts do not prove absence from other clones, caches, backups, or hosted artifacts.

| Potential copy class | Baseline state | Accountable owner/action |
|---|---|---|
| Current task worktree | Confirmed affected by reachable history and current tree. | Current repository operator preserves evidence and performs S1 ordinary-scope removal only after this gate. |
| Second local worktree | Existence confirmed; affected-object reachability/owner not yet confirmed. | Local workstation owner must identify the purpose, owner, and required reclone/cleanup action. |
| Configured remote repository | One remote configured; reachable remote refs and hosted retention are not yet confirmed. | Repository administrator must identify protected branches, forks, mirrors, caches, and retention constraints. |
| Developer/analyst clones | Unknown. | Engineering owner must identify every person/device with a clone or downloaded source archive. |
| CI runners and caches | Unknown. | CI owner must identify runner workspaces, caches, logs, and retained artifacts without exposing content. |
| Release zips/installers | None found under local `dist`; external copies unknown. | Release owner must inventory shared drives, email, device downloads, release pages, and deployment media. |
| Cloud sync, backup, and endpoint protection copies | Unknown. | IT/security owner must identify OneDrive/version history, backup sets, EDR quarantine, and recovery copies. |
| Tickets, chat, screenshots, and support bundles | Unknown. | Incident owner must ask downstream owners for a metadata-only confirmation and removal/retention status. |

Each downstream response must record owner, copy class, affected/not-affected/unknown status, containment action, completion time, and reviewer. Do not request or attach the unsafe material as proof.

## Remediation Gates

1. **S0 evidence preservation:** this metadata-only record, object IDs, commit metadata, and redacted verification evidence are reviewed and committed.
2. **Credential rotation:** the exposed credential is disabled and replaced; provider-side confirmation is recorded without values.
3. **Downstream inventory:** owners for clones, forks, caches, artifacts, backups, and shared copies are identified and report disposition.
4. **S1 ordinary-scope containment:** unsafe current-tree files are removed from ordinary repository/release inputs, ignore/packaging scanners are hardened, and the removal log records metadata-only proof. Ordinary deletion must not be called history remediation.
5. **History-remediation readiness:** evidence retention, legal/records requirements, remote protection rules, coordinated downtime, reclone instructions, and rollback contacts are documented.
6. **Explicit approval:** the user explicitly approves the exact destructive history rewrite and coordinated remote update. No approval is implied by this record.
7. **Post-rewrite verification:** only after gates 1-6, verify forbidden object reachability, credential rotation, protected refs, forks/mirrors/caches, and owner acknowledgements. Use `--force-with-lease` only in the separately approved procedure; never use a plain force push.

No history rewrite, force-push, artifact deletion, or export-file removal occurred in S0.

## Metadata-Only Verification Procedure

Run the repository-owned verifier from Windows PowerShell:

```powershell
& .\docs\security\verify-s0-incident-metadata.ps1 -ExpectedHead (git rev-parse HEAD)
```

The verifier:

- uses `git ls-tree`, `git status`, and `git rev-parse` only as metadata sources;
- reads tree metadata from the approved baseline commit `2f2b656d2d13fca48c56ea6f33d63b83c2cd9d21`, never from the moving current `HEAD`;
- requires exact equality with the six approved category/object-ID/size tuples in this record; successful-but-empty, incomplete, extra, duplicated, or substituted well-formed inventories fail closed;
- never calls `git show`, `git cat-file blob`, `Get-Content`, `type`, or another content-reading command for the export category;
- suppresses every matched path and every matched value;
- outputs only schema/status fields, category counts, blob IDs/sizes, commit hashes, and canary results;
- fails closed for malformed metadata, stale expected state, dirty worktrees, failed Git commands with misleading success text, and secret/PHI output canaries.

Before using output as evidence, independently scan it for original path fragments, credential/provider-token formats, patient-like names, clinical narrative terms, authorization headers, and local absolute paths. Store only the redacted output under `.omo/evidence/task-1a-v2-production-readiness/`; that directory is local-only and must not be staged or packaged.

## Verification Status

S0 verification proves only that the approved baseline commit and exact approved metadata inventory are present, metadata-only, and reproducible. It intentionally remains valid after separately logged S1 current-tree removal because it never substitutes current `HEAD` for the preserved baseline. It does not prove rotation, downstream containment, current-tree removal, history rewrite, remote garbage collection, or production-release readiness. Those remain gated as described above.
