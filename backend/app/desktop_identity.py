from __future__ import annotations

import ctypes
import hashlib
import os
import unicodedata
from ctypes import wintypes
from pathlib import Path
from typing import Final

PRODUCT_ID: Final = "r3.iz-clinical-notes-analyzer.desktop"
REPARSE_ATTRIBUTE: Final = 0x400


class IdentityError(RuntimeError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _ascii_lower(value: str) -> str:
    return "".join(chr(ord(character) + 32) if "A" <= character <= "Z" else character for character in value)


def windows_path_key(path: str | Path) -> str:
    value = str(path).replace("/", "\\")
    if value.startswith("\\\\?\\UNC\\"):
        value = "\\\\" + value[8:]
    elif value.startswith("\\\\?\\"):
        value = value[4:]
    if len(value) > 3:
        value = value.rstrip("\\")
    return _ascii_lower(unicodedata.normalize("NFC", value))


def relative_path_key(path: str) -> str:
    return _ascii_lower(unicodedata.normalize("NFC", path.replace("/", "\\").strip("\\")))


def _domain_hash(domain: str, *values: str) -> str:
    encoded = "\n".join((domain, *values)).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def root_path_hash(path: Path) -> str:
    return root_path_hash_from_key(windows_path_key(path.resolve(strict=True)))


def root_path_hash_from_key(path_key: str) -> str:
    return _domain_hash("iz-cna-root-path-v1", path_key)


def scope_id_from_keys(owner_sid: str, install_path_key: str, data_path_key: str) -> str:
    return _domain_hash("iz-cna-maintenance-scope-v1", PRODUCT_ID, owner_sid, install_path_key, data_path_key)


def scope_id(owner_sid: str, install_root: Path, data_root: Path) -> str:
    return scope_id_from_keys(owner_sid, windows_path_key(install_root), windows_path_key(data_root))


def install_identity_from_key(owner_sid: str, install_path_key: str) -> str:
    return _domain_hash("iz-cna-install-identity-v1", PRODUCT_ID, owner_sid, install_path_key)


def install_identity(owner_sid: str, install_root: Path) -> str:
    return install_identity_from_key(owner_sid, windows_path_key(install_root))


def data_identity_from_keys(owner_sid: str, data_path_key: str, database_path_key: str) -> str:
    return _domain_hash("iz-cna-data-identity-v1", PRODUCT_ID, owner_sid, data_path_key, database_path_key)


def data_identity(owner_sid: str, data_root: Path, database_relative_path: str) -> str:
    return data_identity_from_keys(
        owner_sid,
        windows_path_key(data_root.resolve(strict=True)),
        relative_path_key(database_relative_path),
    )


class _SidAndAttributes(ctypes.Structure):
    _fields_ = (("sid", ctypes.c_void_p), ("attributes", wintypes.DWORD))


def _windows_user_sid() -> str:
    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GetCurrentProcess.argtypes = ()
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = (wintypes.HLOCAL,)
    kernel32.LocalFree.restype = wintypes.HLOCAL
    advapi32.OpenProcessToken.argtypes = (
        wintypes.HANDLE,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.HANDLE),
    )
    advapi32.OpenProcessToken.restype = wintypes.BOOL
    advapi32.GetTokenInformation.argtypes = (
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    )
    advapi32.GetTokenInformation.restype = wintypes.BOOL
    advapi32.ConvertSidToStringSidW.argtypes = (
        ctypes.c_void_p,
        ctypes.POINTER(wintypes.LPWSTR),
    )
    advapi32.ConvertSidToStringSidW.restype = wintypes.BOOL
    token = wintypes.HANDLE()
    if not advapi32.OpenProcessToken(kernel32.GetCurrentProcess(), 0x0008, ctypes.byref(token)):
        raise IdentityError("owner_identity_unavailable")
    try:
        required = wintypes.DWORD()
        advapi32.GetTokenInformation(token, 1, None, 0, ctypes.byref(required))
        if required.value == 0:
            raise IdentityError("owner_identity_unavailable")
        buffer = ctypes.create_string_buffer(required.value)
        if not advapi32.GetTokenInformation(token, 1, buffer, required, ctypes.byref(required)):
            raise IdentityError("owner_identity_unavailable")
        token_user = ctypes.cast(buffer, ctypes.POINTER(_SidAndAttributes)).contents
        sid_text = wintypes.LPWSTR()
        if not advapi32.ConvertSidToStringSidW(token_user.sid, ctypes.byref(sid_text)):
            raise IdentityError("owner_identity_unavailable")
        try:
            return sid_text.value
        finally:
            kernel32.LocalFree(ctypes.cast(sid_text, wintypes.HLOCAL))
    finally:
        kernel32.CloseHandle(token)


def current_user_sid() -> str:
    if os.name == "nt":
        return _windows_user_sid()
    if hasattr(os, "getuid"):
        return f"uid-{os.getuid()}"
    raise IdentityError("owner_identity_unavailable")


def _reject_unsafe_text(path: Path) -> None:
    value = str(path)
    if not path.is_absolute() or value.startswith(("\\\\", "//", "\\?\\", "\\.\\")):
        raise IdentityError("path_invalid")
    drive, tail = os.path.splitdrive(value)
    if os.name == "nt" and (len(drive) != 2 or drive[1] != ":"):
        raise IdentityError("path_invalid")
    if ":" in tail or "\x00" in value:
        raise IdentityError("path_invalid")


def _reject_reparse_components(path: Path) -> None:
    existing = path
    while not existing.exists() and existing != existing.parent:
        existing = existing.parent
    for candidate in (existing, *existing.parents):
        attributes = getattr(candidate.stat(), "st_file_attributes", 0)
        if candidate.is_symlink() or attributes & REPARSE_ATTRIBUTE:
            raise IdentityError("path_reparse_point")


def validated_path(path: str | Path, *, must_exist: bool) -> Path:
    candidate = Path(path).expanduser()
    _reject_unsafe_text(candidate)
    _reject_reparse_components(candidate)
    try:
        return candidate.resolve(strict=must_exist)
    except (FileNotFoundError, OSError) as exc:
        raise IdentityError("path_missing") from exc


def _ordinal_equal(left: str, right: str) -> bool:
    if os.name != "nt":
        return left == right
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CompareStringOrdinal.argtypes = (
        wintypes.LPCWSTR,
        ctypes.c_int,
        wintypes.LPCWSTR,
        ctypes.c_int,
        wintypes.BOOL,
    )
    kernel32.CompareStringOrdinal.restype = ctypes.c_int
    return kernel32.CompareStringOrdinal(left, len(left), right, len(right), True) == 2


def authorized_paths_equal(left: Path, right: Path) -> bool:
    left_parts = left.parts
    right_parts = right.parts
    return len(left_parts) == len(right_parts) and all(
        _ordinal_equal(left_part, right_part)
        for left_part, right_part in zip(left_parts, right_parts, strict=True)
    )


def _is_contained(root: Path, candidate: Path) -> bool:
    root_parts = root.parts
    candidate_parts = candidate.parts
    return len(candidate_parts) >= len(root_parts) and all(
        _ordinal_equal(root_part, candidate_part)
        for root_part, candidate_part in zip(root_parts, candidate_parts[: len(root_parts)], strict=True)
    )


def contained_path(root: Path, candidate: str | Path, *, must_exist: bool) -> Path:
    candidate_path = validated_path(candidate, must_exist=False)
    if not _is_contained(root, candidate_path):
        raise IdentityError("path_outside_root")
    return validated_path(candidate_path, must_exist=True) if must_exist else candidate_path
