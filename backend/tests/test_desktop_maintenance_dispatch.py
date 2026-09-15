from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from test_desktop_maintenance import create_database, inspection_request, write_environment, write_request


@pytest.fixture(autouse=True)
def clear_dispatch_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    names = tuple(name for name in os.environ if name.startswith("IZ_CNA_"))
    names += ("LOCAL_SQLITE_DB_PATH", "DATA_ENCRYPTION_KEY", "SECRET_KEY")
    for name in names:
        monkeypatch.delenv(name, raising=False)


def test_runtime_dispatches_maintenance_before_application_imports(tmp_path: Path) -> None:
    data_root = tmp_path / "profile"
    data_root.mkdir()
    environment_file = write_environment(data_root)
    create_database(data_root / "profile.sqlite3").close()
    request = tmp_path / "request.json"
    result = tmp_path / "result.json"
    observation = tmp_path / "observation.json"
    write_request(request, inspection_request(data_root, environment_file))
    driver = tmp_path / "driver.py"
    driver.write_text(
        "import json,sys\n"
        "from pathlib import Path\n"
        "from app import desktop_runtime\n"
        "before={name:(name in sys.modules) for name in "
        "('app.main','app.desktop_main','app.v2.db')}\n"
        "code=desktop_runtime.main(sys.argv[1:-1])\n"
        "after={name:(name in sys.modules) for name in before}\n"
        "Path(sys.argv[-1]).write_text(json.dumps("
        "{'code':code,'before':before,'after':after},sort_keys=True),encoding='utf-8')\n",
        encoding="utf-8",
    )
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])

    completed = subprocess.run(
        [
            sys.executable,
            str(driver),
            "maintenance",
            "inspect-data",
            "--request",
            str(request),
            "--result",
            str(result),
            str(observation),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
        env=environment,
    )

    assert completed.returncode == 0
    assert completed.stdout == ""
    assert completed.stderr == ""
    observed = json.loads(observation.read_text(encoding="utf-8"))
    assert observed == {
        "code": 0,
        "before": {"app.desktop_main": False, "app.main": False, "app.v2.db": False},
        "after": {"app.desktop_main": False, "app.main": False, "app.v2.db": False},
    }
    assert json.loads(result.read_text(encoding="utf-8"))["status"] == "success"


def test_frozen_runtime_blocks_before_desktop_application_imports(tmp_path: Path) -> None:
    observation = tmp_path / "observation.json"
    driver = tmp_path / "driver.py"
    driver.write_text(
        "import json,sys\n"
        "from pathlib import Path\n"
        "from app import desktop_runtime\n"
        "sys.frozen=True\n"
        "code=desktop_runtime.main(())\n"
        "loaded={name:(name in sys.modules) for name in "
        "('app.main','app.desktop_main','app.v2.db')}\n"
        "Path(sys.argv[1]).write_text(json.dumps({'code':code,'loaded':loaded},sort_keys=True),encoding='utf-8')\n",
        encoding="utf-8",
    )
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])

    completed = subprocess.run(
        [sys.executable, str(driver), str(observation)],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
        env=environment,
    )

    assert completed.returncode == 0
    assert completed.stdout == ""
    assert completed.stderr == ""
    assert json.loads(observation.read_text(encoding="utf-8")) == {
        "code": 31,
        "loaded": {"app.desktop_main": False, "app.main": False, "app.v2.db": False},
    }
