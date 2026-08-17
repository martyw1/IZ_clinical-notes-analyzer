from __future__ import annotations

from typing import Protocol


class DataDirLease(Protocol):
    @property
    def canonical_data_dir_id(self) -> str: ...

    def is_held_by_current_process(self) -> bool: ...

    def release(self) -> None: ...
