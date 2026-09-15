from __future__ import annotations

import ctypes
import os
import re
import threading
from collections.abc import Callable
from ctypes import wintypes
from dataclasses import dataclass
from types import TracebackType
from typing import Final, TypeAlias

from .desktop_identity import current_user_sid

MAX_REQUEST_BYTES: Final = 16_384
PIPE_REJECT_REMOTE_CLIENTS: Final = 0x00000008
PIPE_TYPE_MESSAGE: Final = 0x00000004
PIPE_READMODE_MESSAGE: Final = 0x00000002
PIPE_MODE: Final = PIPE_TYPE_MESSAGE | PIPE_READMODE_MESSAGE | PIPE_REJECT_REMOTE_CLIENTS
_PIPE_ACCESS_DUPLEX: Final = 0x00000003
_FILE_FLAG_FIRST_PIPE_INSTANCE: Final = 0x00080000
_ERROR_BROKEN_PIPE: Final = 109
_ERROR_MORE_DATA: Final = 234
_ERROR_NO_DATA: Final = 232
_ERROR_PIPE_CONNECTED: Final = 535
_ERROR_OPERATION_ABORTED: Final = 995
_MAX_WIRE_BYTES: Final = MAX_REQUEST_BYTES + 2
_TOKEN_PATTERN: Final = re.compile(r"iz-cna-runtime-v1-[0-9a-f]{32}\Z")
_UTF8_BOM: Final = b"\xef\xbb\xbf"

PipeHandler: TypeAlias = Callable[[bytes], bytes | None]


@dataclass(frozen=True, slots=True)
class PipeTransportError(RuntimeError):
    reason: str
    winerror: int | None = None

    def __str__(self) -> str:
        return self.reason


class _SecurityAttributes(ctypes.Structure):
    _fields_ = (
        ("length", wintypes.DWORD),
        ("security_descriptor", wintypes.LPVOID),
        ("inherit_handle", wintypes.BOOL),
    )


def _pipe_path(pipe_token: str) -> str:
    return rf"\\.\pipe\{pipe_token}"


def _current_user_sddl() -> str:
    sid = current_user_sid()
    return f"O:{sid}G:{sid}D:P(A;;GA;;;{sid})"


def _create_pipe(pipe_token: str, sddl: str) -> int:
    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = (
        wintypes.LPCWSTR,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.LPVOID),
        wintypes.LPVOID,
    )
    advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW.restype = wintypes.BOOL
    kernel32.CreateNamedPipeW.argtypes = (
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.POINTER(_SecurityAttributes),
    )
    kernel32.CreateNamedPipeW.restype = wintypes.HANDLE
    kernel32.LocalFree.argtypes = (wintypes.HLOCAL,)
    kernel32.LocalFree.restype = wintypes.HLOCAL
    descriptor = wintypes.LPVOID()
    converted = advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW(
        sddl, 1, ctypes.byref(descriptor), None
    )
    if not converted:
        raise PipeTransportError("pipe_security_invalid", ctypes.get_last_error())
    try:
        attributes = _SecurityAttributes(ctypes.sizeof(_SecurityAttributes), descriptor, False)
        handle = kernel32.CreateNamedPipeW(
            _pipe_path(pipe_token),
            _PIPE_ACCESS_DUPLEX | _FILE_FLAG_FIRST_PIPE_INSTANCE,
            PIPE_MODE,
            1,
            _MAX_WIRE_BYTES,
            _MAX_WIRE_BYTES,
            0,
            ctypes.byref(attributes),
        )
        if handle == wintypes.HANDLE(-1).value:
            raise PipeTransportError("pipe_create_failed", ctypes.get_last_error())
        return int(handle)
    finally:
        kernel32.LocalFree(descriptor)


def _connect_pipe(handle: int, stopping: threading.Event) -> bool:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.ConnectNamedPipe.argtypes = (wintypes.HANDLE, wintypes.LPVOID)
    kernel32.ConnectNamedPipe.restype = wintypes.BOOL
    if kernel32.ConnectNamedPipe(handle, None):
        return True
    error = ctypes.get_last_error()
    if error == _ERROR_PIPE_CONNECTED:
        return True
    if error == _ERROR_OPERATION_ABORTED and stopping.is_set():
        return False
    raise PipeTransportError("pipe_connect_failed", error)


def _valid_line(wire: bytes) -> bool:
    if not wire.endswith(b"\n") or wire.startswith(_UTF8_BOM):
        return False
    content = wire[:-1]
    if content.endswith(b"\r"):
        content = content[:-1]
    if len(content) > MAX_REQUEST_BYTES or b"\n" in content:
        return False
    try:
        wire.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        return False
    return True


def _read_request(handle: int, stopping: threading.Event) -> bytes | None:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.ReadFile.argtypes = (
        wintypes.HANDLE,
        wintypes.LPVOID,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
        wintypes.LPVOID,
    )
    kernel32.ReadFile.restype = wintypes.BOOL
    buffer = ctypes.create_string_buffer(_MAX_WIRE_BYTES)
    received = wintypes.DWORD()
    if not kernel32.ReadFile(handle, buffer, len(buffer), ctypes.byref(received), None):
        error = ctypes.get_last_error()
        if error in {_ERROR_BROKEN_PIPE, _ERROR_MORE_DATA, _ERROR_NO_DATA}:
            return None
        if error == _ERROR_OPERATION_ABORTED and stopping.is_set():
            return None
        raise PipeTransportError("pipe_read_failed", error)
    wire = bytes(buffer.raw[: received.value])
    return wire if _valid_line(wire) else None


def _write_response(handle: int, response: bytes) -> None:
    if not _valid_line(response):
        return
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.WriteFile.argtypes = (
        wintypes.HANDLE,
        wintypes.LPVOID,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
        wintypes.LPVOID,
    )
    kernel32.WriteFile.restype = wintypes.BOOL
    kernel32.FlushFileBuffers.argtypes = (wintypes.HANDLE,)
    kernel32.FlushFileBuffers.restype = wintypes.BOOL
    buffer = ctypes.create_string_buffer(response, len(response))
    written = wintypes.DWORD()
    if kernel32.WriteFile(handle, buffer, len(response), ctypes.byref(written), None):
        kernel32.FlushFileBuffers(handle)
        return
    error = ctypes.get_last_error()
    if error not in {_ERROR_BROKEN_PIPE, _ERROR_NO_DATA}:
        raise PipeTransportError("pipe_write_failed", error)


def _close_pipe(handle: int) -> None:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.DisconnectNamedPipe.argtypes = (wintypes.HANDLE,)
    kernel32.DisconnectNamedPipe.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.DisconnectNamedPipe(handle)
    kernel32.CloseHandle(handle)


def _cancel_thread_io(native_thread_id: int) -> None:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenThread.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel32.OpenThread.restype = wintypes.HANDLE
    kernel32.CancelSynchronousIo.argtypes = (wintypes.HANDLE,)
    kernel32.CancelSynchronousIo.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel32.CloseHandle.restype = wintypes.BOOL
    thread_handle = kernel32.OpenThread(0x0001, False, native_thread_id)
    if not thread_handle:
        return
    try:
        kernel32.CancelSynchronousIo(thread_handle)
    finally:
        kernel32.CloseHandle(thread_handle)


class WindowsNamedPipeServer:
    def __init__(self, pipe_token: str, handler: PipeHandler) -> None:
        if os.name != "nt":
            raise PipeTransportError("windows_required")
        if _TOKEN_PATTERN.fullmatch(pipe_token) is None:
            raise PipeTransportError("pipe_token_invalid")
        self.pipe_token = pipe_token
        self.pipe_mode = PIPE_MODE
        self._handler = handler
        self._sddl = _current_user_sddl()
        self._stopping = threading.Event()
        self._ready = threading.Event()
        self._failure: PipeTransportError | None = None
        self._thread: threading.Thread | None = None

    @property
    def security_descriptor_sddl(self) -> str:
        return self._sddl

    def start(self, timeout: float = 5.0) -> None:
        if self._thread is not None:
            raise PipeTransportError("pipe_already_started")
        self._thread = threading.Thread(target=self._serve, name="iz-cna-runtime-pipe", daemon=True)
        self._thread.start()
        if not self._ready.wait(timeout):
            self.stop(timeout)
            raise PipeTransportError("pipe_start_timeout")
        if self._failure is not None:
            self.stop(timeout)
            raise self._failure

    def stop(self, timeout: float = 5.0) -> None:
        thread = self._thread
        if thread is None:
            return
        self._stopping.set()
        if thread.native_id is not None:
            _cancel_thread_io(thread.native_id)
        thread.join(timeout)
        if thread.is_alive():
            raise PipeTransportError("pipe_stop_timeout")
        self._thread = None

    def _serve(self) -> None:
        try:
            while not self._stopping.is_set():
                handle = _create_pipe(self.pipe_token, self._sddl)
                self._ready.set()
                try:
                    if _connect_pipe(handle, self._stopping):
                        request = _read_request(handle, self._stopping)
                        if request is not None:
                            response = self._handler(request)
                            if response is not None:
                                _write_response(handle, response)
                finally:
                    _close_pipe(handle)
        except PipeTransportError as exc:
            self._failure = exc
            self._ready.set()

    def __enter__(self) -> WindowsNamedPipeServer:
        self.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.stop()
