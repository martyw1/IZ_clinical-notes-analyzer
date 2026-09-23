from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from fnmatch import fnmatch
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


def _windows_powershell_environment(cache_root: Path) -> dict[str, str]:
    environment = os.environ.copy()
    cache_root.mkdir(parents=True, exist_ok=True)
    environment["PSModuleAnalysisCachePath"] = str(cache_root / "ModuleAnalysisCache")
    environment["PSModulePath"] = os.pathsep.join(
        (
            str(Path.home() / "Documents" / "WindowsPowerShell" / "Modules"),
            str(Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "WindowsPowerShell" / "Modules"),
            str(Path(os.environ["SystemRoot"]) / "System32" / "WindowsPowerShell" / "v1.0" / "Modules"),
        )
    )
    return environment


def test_windows_frozen_runtime_disables_uvicorn_default_logging_configuration() -> None:
    from app import desktop_runtime, desktop_runtime_host

    with patch("uvicorn.run") as run:
        assert desktop_runtime._run_unmanaged(8000) == 0
    run.assert_called_once_with(
        "app.desktop_main:app",
        host="127.0.0.1",
        port=8000,
        access_log=False,
        log_config=None,
    )

    launch = SimpleNamespace(authority=SimpleNamespace(gate="open"))
    config_value = object()
    with (
        patch.object(desktop_runtime_host.uvicorn, "Config", return_value=config_value) as config,
        patch.object(desktop_runtime_host.uvicorn, "Server") as server,
        patch.object(desktop_runtime_host.ManagedRuntimeHost, "_new_identity", return_value=object()),
        patch.object(desktop_runtime_host, "RuntimeController"),
    ):
        desktop_runtime_host.ManagedRuntimeHost(launch, object(), 8123)

    _, config_kwargs = config.call_args
    assert config_kwargs == {
        "host": "127.0.0.1",
        "port": 8123,
        "access_log": False,
        "log_config": None,
    }
    server.assert_called_once_with(config_value)


def test_windows_release_installer_renders_and_executes_versioned_wrapper(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    build_script = root / "scripts" / "build-windows-installer.ps1"
    packaging_test = root / "scripts" / "tests" / "test-windows-installer-packaging.ps1"

    if os.name != "nt":
        build_source = build_script.read_text(encoding="utf-8")
        assert "Write-IzPackageInstallerFiles" in build_source
        assert "function New-Shortcut" not in build_source
        return

    report_path = tmp_path / "packaging-wrapper-results.json"
    powershell = Path(os.environ["SystemRoot"]) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    environment = _windows_powershell_environment(tmp_path / "PowerShell")
    completed = subprocess.run(
        [
            str(powershell),
            "-NoLogo",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(packaging_test),
            "-ReportPath",
            str(report_path),
        ],
        cwd=root,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["wrapper"]["unknown_flag_exit_code"] == 20
    assert report["wrapper"]["real_unknown_flag_exit_code"] == 20
    assert report["wrapper"]["success_exit_code"] == 0
    assert report["wrapper"]["default_pause_observed"] is True
    assert {entry["variant"] for entry in report["wrapper"]["variants"]} == {
        "spaces",
        "apostrophe",
        "ampersand",
        "parentheses",
        "unicode",
        "percent",
        "exclamation",
    }
    assert report["launch_wrapper"] == {
        "missing_install_exit_code": 20,
        "installed_launcher_exit_code": 37,
        "forwarded_arguments": "-NoBrowser -NoPause",
    }


def test_windows_release_build_excludes_local_pip_cache() -> None:
    build_script = Path(__file__).resolve().parents[2] / "scripts" / "build-windows-installer.ps1"

    assert "(Join-Path $RootDir 'pip')" in build_script.read_text(encoding="utf-8")


def test_windows_release_stage_and_public_paths_fit_powershell_51(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    build_script = root / "scripts" / "build-windows-installer.ps1"
    build_source = build_script.read_text(encoding="utf-8")
    version = (root / "VERSION").read_text(encoding="utf-8").strip()
    metadata = json.loads((root / "VERSION.json").read_text(encoding="utf-8"))
    package_name = (
        f"IZ-Clinical-Notes-Analyzer-v{version}-build-{metadata['build']}-installer-r1"
    )
    identity_inputs = (
        package_name,
        package_name.replace(str(metadata["build"]), "2026.09.14.2"),
        package_name.replace(version, "2.0.0-beta.5"),
        package_name.removesuffix("r1") + "r2",
    )
    public_names = [
        f"IZ-CNA-{hashlib.sha256(value.encode('utf-8')).hexdigest()[:16]}"
        for value in identity_inputs
    ]
    if os.name == "nt":
        controller = tmp_path / "release-directory-name.ps1"
        names_path = tmp_path / "release-directory-inputs.json"
        names_path.write_text(json.dumps(identity_inputs), encoding="utf-8")
        controller_source = "\n".join(
            (
                "param([string]$BuildScript, [string]$NamesPath)",
                "$ErrorActionPreference = 'Stop'",
                "$tokens = $null",
                "$errors = $null",
                "$ast = [Management.Automation.Language.Parser]::ParseFile($BuildScript, [ref]$tokens, [ref]$errors)",
                "if ($errors.Count) { throw 'BUILDER_PARSE_FAILED' }",
                "$definitions = @($ast.FindAll({ param($node)",
                "    $node -is [Management.Automation.Language.FunctionDefinitionAst] -and",
                "    $node.Name -ceq 'Get-IzReleaseDirectoryName'",
                "}, $true))",
                "if ($definitions.Count -ne 1) { throw 'RELEASE_DIRECTORY_FUNCTION_REQUIRED' }",
                ". ([ScriptBlock]::Create($definitions[0].Extent.Text))",
                "$names = Get-Content -LiteralPath $NamesPath -Raw | ConvertFrom-Json",
                "$actual = @(foreach ($name in $names) { Get-IzReleaseDirectoryName -PackageName ([string]$name) })",
                "ConvertTo-Json -InputObject $actual -Compress",
            )
        )
        controller.write_text(
            controller_source + "\n",
            encoding="utf-8",
        )
        powershell = Path(os.environ["SystemRoot"]) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
        completed = subprocess.run(
            [
                str(powershell),
                "-NoLogo",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(controller),
                "-BuildScript",
                str(build_script),
                "-NamesPath",
                str(names_path),
            ],
            cwd=root,
            env=_windows_powershell_environment(tmp_path / "PowerShell"),
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        assert completed.returncode == 0, completed.stdout + completed.stderr
        assert json.loads(completed.stdout) == public_names
    assert len(set(public_names)) == 4
    assert all(re.fullmatch(r"IZ-CNA-[0-9a-f]{16}", name) for name in public_names)
    guide = Path(
        "docs",
        "guides",
        "Version 2.0 Beta  2.0.0-beta.2  beta-local-desktop-v2",
        "Marleigh-Setup-Install-and-User-Guide.html",
    )
    release_root = root / "dist" / "windows-release"
    token = "0123456789ab"
    old_staged_path = release_root / f".{package_name}.stage-{token}" / "package" / "app" / guide
    bounded_staged_path = release_root / f".stage-{token}" / "package" / "app" / guide
    versioned_public_path = release_root / package_name / "app" / guide
    bounded_public_path = release_root / public_names[0] / "app" / guide

    assert (root / guide).is_file()
    assert len(str(bounded_public_path)) < len(str(bounded_staged_path)) < len(str(old_staged_path))
    assert len(str(bounded_public_path)) < len(str(versioned_public_path))
    if os.name == "nt":
        assert len(str(bounded_staged_path)) < 260
        assert len(str(bounded_public_path)) < 260
    original_release_root_length = 116
    packaged_guide_length = len(str(Path("app") / guide))
    assert packaged_guide_length == 112
    assert (
        original_release_root_length
        + 1
        + len(f".stage-{token}")
        + 1
        + len("package")
        + 1
        + packaged_guide_length
    ) == 257
    assert (
        original_release_root_length
        + 1
        + len(public_names[0])
        + 1
        + packaged_guide_length
    ) == 253
    assert original_release_root_length + 1 + len(f"{package_name}.zip") == 186
    assert (
        '$FinalPackageDir = Join-Path $ReleaseRoot (Get-IzReleaseDirectoryName -PackageName $PackageName)'
        in build_source
    )
    assert '$FinalZipPath = Join-Path $ReleaseRoot "$PackageName.zip"' in build_source
    assert '$FinalReceiptPath = Join-Path $ReleaseRoot "$PackageName.build-receipt.json"' in build_source
    assert 'New-OwnedRoot -Parent $ReleaseRoot -Name ".stage-$invocationId"' in build_source
    assert '.$PackageName.stage-$invocationId' not in build_source
    assert (
        "Remove-OwnedRoot -Path $stageOwnerRoot -Parent $ReleaseRoot "
        "-Owner 'iz-cna-release-stage-v1'"
    ) in build_source


def test_windows_packaged_launcher_waits_for_runtime_readiness_before_success(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    command_wrapper = (root / "scripts" / "launch-packaged-runtime.cmd").read_text(encoding="utf-8")
    powershell_launcher = (root / "scripts" / "launch-packaged-runtime.ps1").read_text(encoding="utf-8")
    runtime_module = (root / "scripts" / "installer" / "maintenance-runtime.psm1").read_text(encoding="utf-8")

    assert "launch-packaged-runtime.ps1" in command_wrapper
    assert "exit /b %EXIT_CODE%" in command_wrapper
    assert "Start-IzOwnedRuntime -Context $context -RuntimeRole Installed" in powershell_launcher
    assert "Get-IzConfiguredRuntimePort -Context $Context" in runtime_module
    assert "Read-IzRuntimeIdentity -Context $Context" in runtime_module
    assert "Invoke-IzRuntimeControl -Context $Context -Operation status" in runtime_module
    assert "RUNTIME_IDENTITY_TIMEOUT" in runtime_module

    if os.name != "nt":
        return

    powershell = Path(os.environ["SystemRoot"]) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    evidence_root = root / ".omo" / "evidence" / "windows-cmd-maintenance" / "packaging" / "launcher-production-config"
    environment = _windows_powershell_environment(tmp_path / "PowerShell")
    completed = subprocess.run(
        [
            str(powershell),
            "-NoLogo",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(root / "scripts" / "tests" / "maintenance-launch-stop.Tests.ps1"),
            "-Case",
            "All",
            "-EvidenceRoot",
            str(evidence_root),
        ],
        cwd=root,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=90,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    evidence_lines = [line for line in completed.stdout.splitlines() if line.startswith("Evidence: ")]
    assert len(evidence_lines) == 1
    receipt_path = Path(evidence_lines[0].removeprefix("Evidence: ")).resolve()
    assert receipt_path.is_relative_to(evidence_root.resolve())
    receipt = json.loads(receipt_path.read_text(encoding="utf-8-sig"))
    results = {entry["name"]: entry for entry in receipt["results"]}
    assert receipt["status"] == "passed"
    assert all(entry["status"] == "passed" for entry in results.values())
    readiness = results["configured_port_runtime_readiness"]["binary_observables"]
    assert readiness == {
        "configured_port": 48123,
        "control_status": "ok",
        "runtime_identity_port": 48123,
    }
    timeout = results["runtime_identity_timeout_fails"]["binary_observables"]
    assert timeout["reason"] == "RUNTIME_IDENTITY_TIMEOUT"
    assert timeout["processes_remaining"] == 0


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
    launcher = Path(__file__).resolve().parents[2] / "scripts" / "start-windows-local.ps1"

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
    runtime_launcher = Path(__file__).resolve().parents[2] / "scripts" / "start-windows-local.ps1"

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
    build_launcher = repository_root / "scripts" / "Build-IZ-Windows-Installer.cmd"

    # When: its environment-variable assignments are inspected.
    launcher_contents = launcher.read_text(encoding="utf-8")
    build_launcher_contents = build_launcher.read_text(encoding="utf-8")

    # Then: path values use quoted batch assignment syntax and cannot become commands.
    assert 'set "SCRIPT_DIR=%~dp0"' in launcher_contents
    assert 'set "ROOT_DIR=%SCRIPT_DIR%.."' in launcher_contents
    assert "set SCRIPT_DIR=" not in launcher_contents
    assert "set ROOT_DIR=" not in launcher_contents
    assert 'set "SCRIPT_DIR=%~dp0"' in build_launcher_contents
    assert 'set "ROOT_DIR=%SCRIPT_DIR%.."' in build_launcher_contents
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
    assert '--add-data "$runtimeVersionFile;."' in build_script_contents
    assert "Copy-Item -LiteralPath $versionFile -Destination $runtimeVersionFile -Force" in build_script_contents
    assert "'app\\VERSION.json'" in build_script_contents


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


def test_resolve_repository_root_uses_frozen_bundle_data_root(tmp_path: Path) -> None:
    # Given: a PyInstaller extraction location and a source-style module path.
    bundled_root = tmp_path / "frozen-bundle"
    module_path = tmp_path / "source" / "backend" / "app" / "core" / "config.py"

    # When: packaged-runtime configuration resolves its resource root.
    from app.core.config import resolve_repository_root

    actual = resolve_repository_root(module_path, bundled_root)

    # Then: deterministic rules are read from the bundled data directory.
    assert actual == bundled_root


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


def test_windows_generated_secrets_always_include_password_policy_character_classes() -> None:
    repository_root = Path(__file__).resolve().parents[2]
    generators = (
        (repository_root / "scripts" / "tests" / "test-api-configuration-local.ps1", "New-RandomSecret", ()),
        (repository_root / "scripts" / "tests" / "test-local-app-stack.ps1", "New-Secret", ("New-RandomBytes",)),
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
