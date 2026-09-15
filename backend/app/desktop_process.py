from __future__ import annotations

import ctypes
import threading
from collections.abc import Callable
from ctypes import wintypes
from datetime import datetime, timedelta, timezone

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
SYNCHRONIZE = 0x00100000
TOKEN_QUERY = 0x0008
WAIT_OBJECT_0 = 0
WAIT_TIMEOUT = 258


class ProcessIdentityError(RuntimeError):
    pass


class _SidAndAttributes(ctypes.Structure):
    _fields_ = (("sid", ctypes.c_void_p), ("attributes", wintypes.DWORD))


def _libraries() -> tuple[ctypes.WinDLL, ctypes.WinDLL]:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.GetProcessTimes.argtypes = (
        wintypes.HANDLE,
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
    )
    kernel32.GetProcessTimes.restype = wintypes.BOOL
    kernel32.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
    kernel32.WaitForSingleObject.restype = wintypes.DWORD
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
    advapi32.ConvertSidToStringSidW.argtypes = (ctypes.c_void_p, ctypes.POINTER(wintypes.LPWSTR))
    advapi32.ConvertSidToStringSidW.restype = wintypes.BOOL
    return kernel32, advapi32


def _process_sid(handle: wintypes.HANDLE, kernel32: ctypes.WinDLL, advapi32: ctypes.WinDLL) -> str:
    token = wintypes.HANDLE()
    if not advapi32.OpenProcessToken(handle, TOKEN_QUERY, ctypes.byref(token)):
        raise ProcessIdentityError("maintenance_owner_unavailable")
    try:
        required = wintypes.DWORD()
        advapi32.GetTokenInformation(token, 1, None, 0, ctypes.byref(required))
        if required.value == 0:
            raise ProcessIdentityError("maintenance_owner_unavailable")
        buffer = ctypes.create_string_buffer(required.value)
        if not advapi32.GetTokenInformation(token, 1, buffer, required, ctypes.byref(required)):
            raise ProcessIdentityError("maintenance_owner_unavailable")
        user = ctypes.cast(buffer, ctypes.POINTER(_SidAndAttributes)).contents
        sid_text = wintypes.LPWSTR()
        if not advapi32.ConvertSidToStringSidW(user.sid, ctypes.byref(sid_text)):
            raise ProcessIdentityError("maintenance_owner_unavailable")
        try:
            return sid_text.value
        finally:
            kernel32.LocalFree(ctypes.cast(sid_text, wintypes.HLOCAL))
    finally:
        kernel32.CloseHandle(token)


def _started_at(handle: wintypes.HANDLE, kernel32: ctypes.WinDLL) -> datetime:
    created = wintypes.FILETIME()
    exited = wintypes.FILETIME()
    kernel = wintypes.FILETIME()
    user = wintypes.FILETIME()
    if not kernel32.GetProcessTimes(handle, created, exited, kernel, user):
        raise ProcessIdentityError("maintenance_owner_unavailable")
    ticks = (created.dwHighDateTime << 32) | created.dwLowDateTime
    return datetime(1601, 1, 1, tzinfo=timezone.utc) + timedelta(microseconds=ticks // 10)


def _parse_utc(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ProcessIdentityError("maintenance_owner_mismatch") from exc
    if parsed.tzinfo is None:
        raise ProcessIdentityError("maintenance_owner_mismatch")
    return parsed.astimezone(timezone.utc)


def process_started_utc(process_id: int) -> str:
    kernel32, _ = _libraries()
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, process_id)
    if not handle:
        raise ProcessIdentityError("maintenance_owner_unavailable")
    try:
        return _started_at(handle, kernel32).isoformat(timespec="microseconds").replace("+00:00", "Z")
    finally:
        kernel32.CloseHandle(handle)


class OwnerProcessLease:
    def __init__(self, handle: wintypes.HANDLE, kernel32: ctypes.WinDLL) -> None:
        self._handle = handle
        self._kernel32 = kernel32
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def exited(self) -> bool:
        result = self._kernel32.WaitForSingleObject(self._handle, 0)
        if result not in (WAIT_OBJECT_0, WAIT_TIMEOUT):
            raise ProcessIdentityError("maintenance_owner_unavailable")
        return result == WAIT_OBJECT_0

    def watch(self, callback: Callable[[], None]) -> None:
        if self._thread is not None:
            raise RuntimeError("owner process already watched")

        def wait_for_exit() -> None:
            while not self._stop.wait(0.1):
                if self.exited:
                    callback()
                    return

        self._thread = threading.Thread(target=wait_for_exit, name="maintenance-owner-watch", daemon=True)
        self._thread.start()

    def close(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(2)
        if self._handle:
            self._kernel32.CloseHandle(self._handle)
            self._handle = wintypes.HANDLE()


def open_owner_process(process_id: int, expected_sid: str, expected_started_utc: str) -> OwnerProcessLease:
    kernel32, advapi32 = _libraries()
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE, False, process_id)
    if not handle:
        raise ProcessIdentityError("maintenance_owner_unavailable")
    try:
        actual_sid = _process_sid(handle, kernel32, advapi32)
        actual_started = _started_at(handle, kernel32)
        expected_started = _parse_utc(expected_started_utc)
        if actual_sid != expected_sid or abs((actual_started - expected_started).total_seconds()) > 1:
            raise ProcessIdentityError("maintenance_owner_mismatch")
        return OwnerProcessLease(handle, kernel32)
    except ProcessIdentityError:
        kernel32.CloseHandle(handle)
        raise
