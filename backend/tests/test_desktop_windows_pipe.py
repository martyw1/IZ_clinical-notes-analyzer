from __future__ import annotations

import base64
import ctypes
import os
import shutil
import subprocess
import uuid
from ctypes import wintypes
from pathlib import Path
from queue import Empty, Queue
from tempfile import TemporaryDirectory

import pytest

from app.desktop_identity import current_user_sid
from app.desktop_windows_pipe import (
    MAX_REQUEST_BYTES,
    PIPE_REJECT_REMOTE_CLIENTS,
    WindowsNamedPipeServer,
)

pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows named pipes are required")


def _token() -> str:
    return f"iz-cna-runtime-v1-{uuid.uuid4().hex}"


def _powershell() -> str:
    executable = shutil.which("pwsh") or shutil.which("powershell")
    if executable is None:
        pytest.fail("PowerShell is required for the runtime pipe compatibility test")
    return executable


def _run_powershell(script: str) -> subprocess.CompletedProcess[str]:
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    with TemporaryDirectory(prefix="iz-cna-pipe-powershell-") as cache_directory:
        cache_root = Path(cache_directory)
        environment = os.environ.copy()
        environment["PSModuleAnalysisCachePath"] = str(cache_root / "ModuleAnalysisCache")
        result = subprocess.run(
            [_powershell(), "-NoLogo", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
            env=environment,
        )
    if cache_root.exists():
        pytest.fail("PowerShell module analysis cache was not removed")
    return result


def _round_trip_script(token: str, request: str) -> str:
    return f"""
$pipe = [System.IO.Pipes.NamedPipeClientStream]::new('.', '{token}', [System.IO.Pipes.PipeDirection]::InOut, [System.IO.Pipes.PipeOptions]::Asynchronous)
try {{
    $pipe.Connect(3000)
    $pipe.ReadMode = [System.IO.Pipes.PipeTransmissionMode]::Message
    $utf8 = [System.Text.UTF8Encoding]::new($false, $true)
    $writer = [System.IO.StreamWriter]::new($pipe, $utf8, 1024, $true)
    $reader = [System.IO.StreamReader]::new($pipe, $utf8, $false, 1024, $true)
    $writer.NewLine = "`n"
    $writer.AutoFlush = $true
    $writer.WriteLine('{request}')
    [Console]::Out.Write($reader.ReadLine())
}} finally {{
    if ($null -ne $reader) {{ $reader.Dispose() }}
    if ($null -ne $writer) {{ $writer.Dispose() }}
    $pipe.Dispose()
}}
"""


def _invalid_write_script(token: str, payload_expression: str) -> str:
    return f"""
$pipe = [System.IO.Pipes.NamedPipeClientStream]::new('.', '{token}', [System.IO.Pipes.PipeDirection]::InOut, [System.IO.Pipes.PipeOptions]::Asynchronous)
try {{
    $pipe.Connect(3000)
    $pipe.ReadMode = [System.IO.Pipes.PipeTransmissionMode]::Message
    [byte[]]$payload = {payload_expression}
    $pipe.Write($payload, 0, $payload.Length)
    $pipe.Flush()
    [byte[]]$buffer = [byte[]]::new(1)
    try {{ $read = $pipe.Read($buffer, 0, 1) }} catch [System.IO.IOException] {{ $read = 0 }}
    if ($read -ne 0) {{ throw 'unexpected response to invalid request' }}
}} finally {{
    $pipe.Dispose()
}}
"""


def _read_pipe_sddl(token: str) -> str:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel32.CreateFileW.argtypes = (
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    )
    kernel32.CreateFileW.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = (wintypes.HLOCAL,)
    kernel32.LocalFree.restype = wintypes.HLOCAL
    advapi32.GetSecurityInfo.argtypes = (
        wintypes.HANDLE,
        ctypes.c_int,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.LPVOID,
        wintypes.LPVOID,
        wintypes.LPVOID,
        ctypes.POINTER(wintypes.LPVOID),
    )
    advapi32.GetSecurityInfo.restype = wintypes.DWORD
    advapi32.ConvertSecurityDescriptorToStringSecurityDescriptorW.argtypes = (
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.LPWSTR),
        wintypes.LPVOID,
    )
    advapi32.ConvertSecurityDescriptorToStringSecurityDescriptorW.restype = wintypes.BOOL

    desired_access = 0x80000000 | 0x40000000 | 0x00020000
    handle = kernel32.CreateFileW(
        rf"\\.\pipe\{token}", desired_access, 0, None, 3, 0, None
    )
    if handle == wintypes.HANDLE(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        descriptor = wintypes.LPVOID()
        security_information = 0x1 | 0x2 | 0x4
        status = advapi32.GetSecurityInfo(
            handle,
            6,
            security_information,
            None,
            None,
            None,
            None,
            ctypes.byref(descriptor),
        )
        if status != 0:
            raise OSError(status, "GetSecurityInfo failed")
        try:
            text = wintypes.LPWSTR()
            if not advapi32.ConvertSecurityDescriptorToStringSecurityDescriptorW(
                descriptor,
                1,
                security_information,
                ctypes.byref(text),
                None,
            ):
                raise ctypes.WinError(ctypes.get_last_error())
            try:
                if text.value is None:
                    pytest.fail("Windows returned an empty pipe security descriptor")
                return text.value
            finally:
                kernel32.LocalFree(text)
        finally:
            kernel32.LocalFree(descriptor)
    finally:
        kernel32.CloseHandle(handle)


def test_server_round_trips_with_named_pipe_client_stream() -> None:
    # Given: a real message-mode Windows named-pipe server.
    requests: Queue[bytes] = Queue()

    def handler(request: bytes) -> bytes:
        requests.put(request)
        return b'{"schema":"response","status":"ok"}\n'

    with WindowsNamedPipeServer(_token(), handler) as server:
        # When: the frozen PowerShell client shape writes one UTF-8 JSON line.
        result = _run_powershell(_round_trip_script(server.pipe_token, '{"operation":"status"}'))

        # Then: one response line returns and the handler receives the client's LF.
        assert result.returncode == 0, result.stderr
        assert result.stdout == '{"schema":"response","status":"ok"}'
        assert requests.get(timeout=1) == b'{"operation":"status"}\n'


def test_server_rejects_invalid_utf8_and_oversize_messages_then_recovers() -> None:
    # Given: a server whose handler records every accepted request.
    requests: Queue[bytes] = Queue()

    def handler(request: bytes) -> bytes:
        requests.put(request)
        return b'{"status":"ok"}\n'

    with WindowsNamedPipeServer(_token(), handler) as server:
        invalid_utf8 = _run_powershell(_invalid_write_script(server.pipe_token, "[byte[]](255, 10)"))
        oversized = _run_powershell(
            _invalid_write_script(
                server.pipe_token,
                f"[System.Text.Encoding]::UTF8.GetBytes(('x' * {MAX_REQUEST_BYTES + 1}) + \"`n\")",
            )
        )
        valid = _run_powershell(_round_trip_script(server.pipe_token, '{"operation":"status"}'))

        # Then: invalid connections receive no data and do not stop the server.
        assert invalid_utf8.returncode == 0, invalid_utf8.stderr
        assert oversized.returncode == 0, oversized.stderr
        assert valid.returncode == 0, valid.stderr
        assert valid.stdout == '{"status":"ok"}'
        assert requests.get(timeout=1) == b'{"operation":"status"}\n'
        with pytest.raises(Empty):
            requests.get_nowait()


def test_server_applies_current_user_protected_acl_and_remote_reject_mode() -> None:
    # Given: an active server created for the current Windows account.
    sid = current_user_sid()
    with WindowsNamedPipeServer(_token(), lambda request: None) as server:
        # When: the live kernel object's security descriptor is read through a client handle.
        sddl = _read_pipe_sddl(server.pipe_token)

        # Then: ownership and the protected allow ACE bind to this user only.
        assert f"O:{sid}" in sddl
        assert f"G:{sid}" in sddl
        assert "D:P" in sddl
        assert f"(A;;FA;;;{sid})" in sddl
        assert "S-1-1-0" not in sddl
        assert server.security_descriptor_sddl == f"O:{sid}G:{sid}D:P(A;;GA;;;{sid})"
        assert server.pipe_mode & PIPE_REJECT_REMOTE_CLIENTS
