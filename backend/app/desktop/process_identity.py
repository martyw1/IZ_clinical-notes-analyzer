from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import NewType, Protocol, assert_never


NormalizedExecutablePath = NewType("NormalizedExecutablePath", str)


class DesktopPlatform(StrEnum):
    WINDOWS = "windows"
    MACOS = "macos"


@dataclass(frozen=True, slots=True)
class ExecutablePathPolicy:
    platform: DesktopPlatform
    case_sensitive: bool


@dataclass(frozen=True, slots=True)
class ProcessIdentityError(RuntimeError):
    reason_code: str

    def __str__(self) -> str:
        return self.reason_code


@dataclass(frozen=True, slots=True)
class ProcessIdentity:
    pid: int
    creation_time_epoch_ns: int
    executable_path: NormalizedExecutablePath

    def __post_init__(self) -> None:
        if self.pid <= 0 or self.creation_time_epoch_ns <= 0:
            raise ProcessIdentityError("desktop_process_identity_invalid")
        path_text = str(self.executable_path)
        windows_path = PureWindowsPath(path_text)
        posix_path = PurePosixPath(path_text)
        if (
            not path_text
            or "\x00" in path_text
            or unicodedata.normalize("NFC", path_text) != path_text
            or not (windows_path.is_absolute() or posix_path.is_absolute())
            or ".." in windows_path.parts
            or ".." in posix_path.parts
        ):
            raise ProcessIdentityError("desktop_process_executable_path_invalid")


class ProcessIdentityProvider(Protocol):
    def identity_for_pid(self, pid: int) -> ProcessIdentity | None: ...


def normalize_executable_path(path: str | Path, policy: ExecutablePathPolicy) -> NormalizedExecutablePath:
    raw_path = str(path)
    match policy.platform:
        case DesktopPlatform.WINDOWS:
            parsed = PureWindowsPath(raw_path)
            normalized = str(parsed)
            folded = not policy.case_sensitive
        case DesktopPlatform.MACOS:
            parsed = PurePosixPath(raw_path)
            normalized = str(parsed)
            folded = not policy.case_sensitive
        case unreachable:
            assert_never(unreachable)
    if not parsed.is_absolute() or ".." in parsed.parts or "\x00" in normalized:
        raise ProcessIdentityError("desktop_process_executable_path_invalid")
    normalized = unicodedata.normalize("NFC", normalized)
    if folded:
        normalized = unicodedata.normalize("NFC", normalized.casefold())
    return NormalizedExecutablePath(normalized)


def process_identity_matches(provider: ProcessIdentityProvider, expected: ProcessIdentity) -> bool:
    return provider.identity_for_pid(expected.pid) == expected
