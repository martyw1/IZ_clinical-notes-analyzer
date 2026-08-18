from __future__ import annotations

import os
import re
import subprocess
import sys
from fnmatch import fnmatch
from pathlib import Path
from unittest.mock import patch

import pytest


def test_windows_frozen_runtime_disables_uvicorn_default_logging_configuration(monkeypatch) -> None:
    # Given: PyInstaller --noconsole runs with sys.stdout unavailable to Uvicorn's default formatter.
    monkeypatch.delenv("IZ_CNA_PORT", raising=False)
    from app import desktop_runtime

    # When: the frozen desktop runtime starts the local Uvicorn server.
    with patch.object(desktop_runtime.uvicorn, "run") as run:
        desktop_runtime.main()

    # Then: it does not install the formatter that calls sys.stdout.isatty().
    run.assert_called_once_with(
        "app.desktop_main:app",
        host="127.0.0.1",
        port=8000,
        access_log=False,
        log_config=None,
    )


def test_windows_release_installer_initializes_packaged_runtime_configuration() -> None:
    build_script = Path(__file__).resolve().parents[2] / "scripts" / "build-windows-installer.ps1"
    preflight_script = Path(__file__).resolve().parents[2] / "scripts" / "preflight-windows.ps1"

    assert "-InitializePackagedRuntime" in build_script.read_text(encoding="utf-8")
    assert "[switch]$InitializePackagedRuntime" in preflight_script.read_text(encoding="utf-8")


def test_windows_release_build_excludes_local_pip_cache() -> None:
    build_script = Path(__file__).resolve().parents[2] / "scripts" / "build-windows-installer.ps1"

    assert "(Join-Path $RootDir 'pip')" in build_script.read_text(encoding="utf-8")


def test_windows_packaged_launcher_waits_for_runtime_readiness_before_success() -> None:
    # Given: a packaged launcher starts its runtime in the background.
    launcher = Path(__file__).resolve().parents[2] / "scripts" / "launch-packaged-runtime.cmd"

    # When: the launcher contract is inspected.
    launcher_contents = launcher.read_text(encoding="utf-8")

    # Then: it probes the documented readiness endpoint and returns failure on timeout.
    assert "/api/readiness" in launcher_contents
    assert "Readiness check failed" in launcher_contents
    assert "BACKEND_PORT" in launcher_contents
    assert "127.0.0.1:%IZ_CNA_PORT%" in launcher_contents
    assert "configured local port is invalid or already in use" in launcher_contents
    assert "exit /b 1" in launcher_contents


def test_windows_checkout_launcher_waits_for_runtime_readiness_before_success() -> None:
    # Given: the source-checkout wrapper launches startup PowerShell in the background.
    launcher = Path(__file__).resolve().parents[2] / "scripts" / "start-windows-local.ps1"

    # When: the checkout launcher contract is inspected.
    launcher_contents = launcher.read_text(encoding="utf-8")

    # Then: it waits for the readiness contract before reporting background startup.
    assert "Wait-ForReadiness" in launcher_contents
    assert "Startup readiness check failed" in launcher_contents
    assert "Get-ConfiguredPort" in launcher_contents
    assert "Assert-PortAvailable -Port $port" in launcher_contents
    assert "Wait-ForReadiness -Process $process -Port $port" in launcher_contents
    assert "$ready = $false" in launcher_contents


def test_windows_checkout_launcher_opens_browser_only_after_runtime_readiness() -> None:
    # Given: the source-checkout runtime owns its server process and browser launch.
    launcher = Path(__file__).resolve().parents[2] / "scripts" / "startup-windows-local.ps1"

    # When: the browser and readiness operations are inspected in execution order.
    launcher_contents = launcher.read_text(encoding="utf-8")
    server_start = "$serverProcess = Start-Process"
    readiness_call = "Wait-ForReadiness -Process $serverProcess -Port $port"
    browser_call = 'if (-not $NoBrowser) { Start-Process "http://localhost:$port" }'
    server_wait = "Wait-Process -Id $serverProcess.Id"

    # Then: the runtime starts first, readiness succeeds, the browser opens, and supervision continues.
    assert server_start in launcher_contents
    assert readiness_call in launcher_contents
    assert browser_call in launcher_contents
    assert server_wait in launcher_contents
    assert launcher_contents.index(server_start) < launcher_contents.index(readiness_call)
    assert launcher_contents.index(readiness_call) < launcher_contents.index(browser_call)
    assert launcher_contents.index(browser_call) < launcher_contents.index(server_wait)


def test_windows_checkout_runtime_disables_access_logging_for_patient_routes() -> None:
    runtime_launcher = Path(__file__).resolve().parents[2] / "scripts" / "startup-windows-local.ps1"

    assert "--no-access-log" in runtime_launcher.read_text(encoding="utf-8")


def test_windows_checkout_launcher_passes_enabled_switches_without_string_boolean_values() -> None:
    launcher = Path(__file__).resolve().parents[2] / "scripts" / "start-windows-local.ps1"
    launcher_contents = launcher.read_text(encoding="utf-8")

    assert "-SkipFrontendBuild:$skipFrontendValue" not in launcher_contents
    assert "-AssumeYes:$assumeYesValue" not in launcher_contents
    assert "if ($SkipFrontendBuild) { $arguments += ' -SkipFrontendBuild' }" in launcher_contents
    assert "if ($AssumeYes) { $arguments += ' -AssumeYes' }" in launcher_contents


def test_windows_cmd_launcher_quotes_path_assignments() -> None:
    # Given: the user-facing CMD launcher may run from a path containing shell metacharacters.
    repository_root = Path(__file__).resolve().parents[2]
    launcher = repository_root / "scripts" / "Start-IZ-Clinical-Notes-Analyzer.cmd"
    build_launcher = repository_root / "Build-IZ-Windows-Installer.cmd"

    # When: its environment-variable assignments are inspected.
    launcher_contents = launcher.read_text(encoding="utf-8")
    build_launcher_contents = build_launcher.read_text(encoding="utf-8")

    # Then: path values use quoted batch assignment syntax and cannot become commands.
    assert 'set "SCRIPT_DIR=%~dp0"' in launcher_contents
    assert 'set "ROOT_DIR=%SCRIPT_DIR%.."' in launcher_contents
    assert "set SCRIPT_DIR=" not in launcher_contents
    assert "set ROOT_DIR=" not in launcher_contents
    assert 'set "ROOT_DIR=%~dp0"' in build_launcher_contents
    assert 'echo "%ROOT_DIR%"' in build_launcher_contents
    assert "echo %ROOT_DIR%" not in build_launcher_contents


def test_windows_frozen_runtime_uses_sanitized_data_staging() -> None:
    # Given: local backup files can exist beside otherwise packageable frontend or rule assets.
    build_script = Path(__file__).resolve().parents[2] / "scripts" / "build-windows-installer.ps1"

    # When: the PyInstaller data-source contract is inspected.
    build_script_contents = build_script.read_text(encoding="utf-8")

    # Then: PyInstaller consumes sanitized staging trees instead of the live repository directories.
    assert "Copy-SafeDataTree" in build_script_contents
    assert '--add-data "$runtimeFrontendDir;app\\static"' in build_script_contents
    assert '--add-data "$runtimeConfigDir;config"' in build_script_contents


def test_pytest_local_backup_exclusions_never_hide_tracked_tests() -> None:
    # Given: collection ignores local snapshots while tracked tests remain authoritative.
    repository_root = Path(__file__).resolve().parents[2]
    conftest = repository_root / "backend" / "tests" / "conftest.py"

    # When: the tracked backend test inventory and localized ignore contract are read.
    tracked = subprocess.run(
        ["git", "-C", str(repository_root), "ls-files", "backend/tests/*.py"],
        capture_output=True,
        text=True,
        check=False,
    )
    patterns = ("*.local-*.py", "*.local.*.py")
    hidden_tracked_tests = [
        path
        for path in tracked.stdout.splitlines()
        if any(
            fnmatch(Path(path).relative_to("backend/tests").as_posix(), pattern)
            for pattern in patterns
        )
    ]
    nested_path_canaries = ("archive.local-copy/test_v2_auth.py", "archive.local.copy/test_v2_auth.py")

    # Then: the ignore is test-directory scoped and no committed test can disappear behind it.
    assert tracked.returncode == 0
    assert all(pattern in conftest.read_text(encoding="utf-8") for pattern in patterns)
    assert all(any(fnmatch(path, pattern) for pattern in patterns) for path in nested_path_canaries)
    assert hidden_tracked_tests == []


def test_windows_frozen_runtime_explicitly_packages_desktop_asgi_entrypoint() -> None:
    # Given: the Windows installer bundles desktop_runtime.py, which resolves the ASGI app dynamically.
    build_script = Path(__file__).resolve().parents[2] / "scripts" / "build-windows-installer.ps1"

    # When: the PyInstaller invocation is read from the release build script.
    build_script_contents = build_script.read_text(encoding="utf-8")

    # Then: the dynamically imported ASGI entrypoint is explicitly collected for frozen execution.
    assert "--hidden-import app.desktop_main" in build_script_contents


def test_resolve_resource_root_uses_frozen_bundle_data_root(tmp_path: Path) -> None:
    # Given: a PyInstaller extraction location, source module, and separate local profile.
    bundled_root = tmp_path / "frozen-bundle"
    module_path = tmp_path / "source" / "backend" / "app" / "core" / "config.py"
    local_root = tmp_path / "local-profile"

    # When: stdlib-only packaged path resolution selects immutable and mutable roots.
    from app.core.platform_paths import PlatformPathContext, resolve_local_app_data_dir, resolve_resource_root

    resource_root = resolve_resource_root(module_path, bundled_root)
    context = PlatformPathContext("win32", {"IZ_CNA_LOCAL_APP_DATA_DIR": str(local_root)}, tmp_path, tmp_path / "working", True)
    data_root = resolve_local_app_data_dir(resource_root, context)

    # Then: resources remain in the bundle while every mutable path stays outside it.
    assert resource_root == bundled_root.resolve()
    assert data_root == local_root.resolve()
    assert data_root != resource_root
    assert not bundled_root.exists() and not local_root.exists()


def _config_probe(env_file: Path, overrides: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    for key in tuple(environment):
        if key.startswith("IZ_CNA_") or key in {
            "ENVIRONMENT",
            "SECRET_KEY",
            "DATA_ENCRYPTION_KEY",
            "BOOTSTRAP_ADMIN_USERNAME",
            "BOOTSTRAP_ADMIN_PASSWORD",
            "LOCAL_SQLITE_DB_PATH",
        }:
            environment.pop(key)
    environment["IZ_CNA_ENV_FILE"] = str(env_file)
    environment.update(overrides or {})
    return subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from app.core.config import settings; "
                "print(settings.environment, settings.bootstrap_admin_username, "
                "settings.local_sqlite_db_path, len(settings.secret_key), "
                "len(settings.data_encryption_key))"
            ),
        ],
        cwd=Path(__file__).resolve().parents[1],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


def test_env_file_is_loaded_before_settings_and_generated_names_are_normalized(tmp_path: Path) -> None:
    # Given: the exact unprefixed names generated by Windows preflight.
    env_file = tmp_path / "generated.env"
    env_file.write_text(
        "\n".join(
            (
                "ENVIRONMENT=local-client",
                "SECRET_KEY=synthetic-secret-key-12345678901234567890",
                "DATA_ENCRYPTION_KEY=synthetic-data-key-12345678901234567890",
                "LOCAL_SQLITE_DB_PATH=generated.sqlite3",
                "BOOTSTRAP_ADMIN_USERNAME=localadmin",
                "BOOTSTRAP_ADMIN_PASSWORD=SyntheticBootstrapPass123",
            )
        ),
        encoding="utf-8",
    )

    # When: settings are imported in a fresh interpreter.
    result = _config_probe(env_file)

    # Then: the file values are available during global settings construction.
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "local-client localadmin generated.sqlite3 41 39"


def test_process_environment_overrides_env_file(tmp_path: Path) -> None:
    # Given: a safe file value and a safe explicit process override.
    env_file = tmp_path / "generated.env"
    env_file.write_text(
        "\n".join(
            (
                "ENVIRONMENT=local-client",
                "SECRET_KEY=synthetic-secret-key-12345678901234567890",
                "DATA_ENCRYPTION_KEY=synthetic-data-key-12345678901234567890",
                "BOOTSTRAP_ADMIN_USERNAME=admin",
                "BOOTSTRAP_ADMIN_PASSWORD=SyntheticBootstrapPass123",
            )
        ),
        encoding="utf-8",
    )

    # When: the process supplies the canonical prefixed administrator name.
    result = _config_probe(env_file, {"IZ_CNA_BOOTSTRAP_ADMIN_USERNAME": "overrideadmin"})

    # Then: explicit process configuration wins.
    assert result.returncode == 0, result.stderr
    assert "local-client overrideadmin" in result.stdout


def test_local_client_fails_closed_for_default_or_missing_security_values(tmp_path: Path) -> None:
    # Given: generated local-client configuration containing known unsafe defaults.
    env_file = tmp_path / "unsafe.env"
    env_file.write_text(
        "\n".join(
            (
                "ENVIRONMENT=local-client",
                "SECRET_KEY=change-me",
                "DATA_ENCRYPTION_KEY=",
                "BOOTSTRAP_ADMIN_USERNAME=admin",
                "BOOTSTRAP_ADMIN_PASSWORD=change-me",
            )
        ),
        encoding="utf-8",
    )

    # When: production settings are constructed.
    result = _config_probe(env_file)

    # Then: startup fails without echoing any supplied value.
    assert result.returncode != 0
    assert "unsafe production configuration" in result.stderr.lower()
    assert "change-me" not in result.stderr


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell generators are Windows-only")
def test_windows_generated_secrets_always_include_password_policy_character_classes() -> None:
    repository_root = Path(__file__).resolve().parents[2]
    generators = (
        (repository_root / "scripts" / "test-api-configuration-local.ps1", "New-RandomSecret", ()),
        (repository_root / "scripts" / "test-local-app-stack.ps1", "New-Secret", ("New-RandomBytes",)),
        (repository_root / "scripts" / "preflight-windows.ps1", "New-RandomSecret", ()),
    )

    for script_path, function_name, dependencies in generators:
        contents = script_path.read_text(encoding="utf-8")
        functions: list[str] = []
        for name in (*dependencies, function_name):
            function = re.search(
                rf"function {name}\b.*?^\}}",
                contents,
                flags=re.MULTILINE | re.DOTALL,
            )
            assert function is not None
            functions.append(function.group(0))
        probe = (
            f"{'\n'.join(functions)}\n"
            "$invalid = 0\n"
            f"1..16 | ForEach-Object {{ $value = {function_name} 2; "
            "if ($value -notmatch '[A-Za-z]' -or $value -notmatch '[0-9]') { $invalid += 1 } }\n"
            "Write-Output $invalid"
        )
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", probe],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "0", f"{script_path.name} generated policy-invalid passwords"
