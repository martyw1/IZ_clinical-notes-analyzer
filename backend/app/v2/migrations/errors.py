from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MigrationStateError(Exception):
    reason: str

    def __str__(self) -> str:
        return f"migration state rejected: {self.reason}"


@dataclass(frozen=True, slots=True)
class MigrationPathError(ValueError):
    reason: str

    def __str__(self) -> str:
        return f"migration path rejected: {self.reason}"


@dataclass(frozen=True, slots=True)
class MigrationInterruptionError(RuntimeError):
    reason: str

    def __str__(self) -> str:
        return f"migration interrupted: {self.reason}"
