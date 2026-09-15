from __future__ import annotations


class RuntimeAuthorityError(RuntimeError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason
