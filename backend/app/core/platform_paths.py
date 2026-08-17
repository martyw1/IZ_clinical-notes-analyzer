from __future__ import annotations

import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


APP_DATA_DIRECTORY_NAME = "IZ Clinical Notes Analyzer"


class PlatformPathError(RuntimeError):
    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__(reason_code)

    def __str__(self) -> str:
        return self.reason_code


@dataclass(frozen=True, slots=True)
class PlatformPathContext:
    platform_name: str
    environment: Mapping[str, str]
    home: Path
    cwd: Path
    frozen: bool


@dataclass(frozen=True, slots=True)
class VolumeIdentity:
    identifier: str
    case_sensitive: bool


class VolumeIdentityProvider(Protocol):
    def identity_for_path(self, path: Path) -> VolumeIdentity: ...


def resolve_resource_root(module_path: Path, bundled_data_root: Path | None) -> Path:
    return (bundled_data_root if bundled_data_root is not None else module_path.resolve().parents[3]).resolve()


def resolve_local_app_data_dir(resource_root: Path, context: PlatformPathContext) -> Path:
    configured = context.environment.get("IZ_CNA_LOCAL_APP_DATA_DIR", "").strip()
    if configured:
        candidate = _configured_path(configured, context)
    elif context.platform_name.casefold() in {"win32", "windows"}:
        base = context.environment.get("LOCALAPPDATA", "").strip()
        if not base:
            if context.frozen:
                raise PlatformPathError("desktop_local_app_data_unavailable")
            return (resource_root / ".local-app-data").resolve()
        candidate = Path(base) / APP_DATA_DIRECTORY_NAME
    elif context.platform_name.casefold() in {"darwin", "macos"}:
        candidate = context.home / "Library" / "Application Support" / APP_DATA_DIRECTORY_NAME
    elif not context.frozen:
        return (resource_root / ".local-app-data").resolve()
    else:
        raise PlatformPathError("desktop_platform_unsupported")
    if context.frozen and not candidate.is_absolute():
        raise PlatformPathError("desktop_data_dir_must_be_absolute")
    resolved = (candidate if candidate.is_absolute() else context.cwd / candidate).resolve()
    if context.frozen:
        assert_mutable_path_outside_resources(resolved, resource_root)
        assert_mutable_path_outside_resources(resolved, context.cwd)
    return resolved


def canonical_data_dir_id(
    data_root: Path,
    platform_name: str,
    identity_provider: VolumeIdentityProvider,
) -> str:
    resolved = data_root.resolve()
    existing = resolved
    while not existing.exists() and existing != existing.parent:
        existing = existing.parent
    identity = identity_provider.identity_for_path(existing)
    folded = platform_name.casefold() in {"win32", "windows"} or (
        platform_name.casefold() in {"darwin", "macos"} and not identity.case_sensitive
    )
    path_text = unicodedata.normalize("NFC", str(resolved))
    volume_text = unicodedata.normalize("NFC", identity.identifier)
    if folded:
        path_text, volume_text = path_text.casefold(), volume_text.casefold()
    return f"{volume_text}|{path_text}"


def assert_mutable_path_outside_resources(data_root: Path, resource_root: Path) -> None:
    data = data_root.resolve()
    resource = resource_root.resolve()
    boundaries = [resource]
    parts = resource.parts
    for index, part in enumerate(parts):
        if part.casefold().endswith(".app") and index + 1 < len(parts) and parts[index + 1].casefold() == "contents":
            boundaries.append(Path(*parts[: index + 2]))
        if part.casefold() == "volumes" and index + 1 < len(parts):
            boundaries.append(Path(*parts[: index + 2]))
    if any(_is_within(data, boundary) for boundary in boundaries):
        raise PlatformPathError("desktop_data_dir_is_immutable")


def _configured_path(value: str, context: PlatformPathContext) -> Path:
    if value == "~":
        return context.home
    if value.startswith(("~/", "~\\")):
        return context.home / value[2:]
    candidate = Path(value)
    if context.frozen and not candidate.is_absolute():
        raise PlatformPathError("desktop_data_dir_must_be_absolute")
    return candidate


def _is_within(candidate: Path, boundary: Path) -> bool:
    try:
        candidate.relative_to(boundary)
    except ValueError:
        return False
    return True
