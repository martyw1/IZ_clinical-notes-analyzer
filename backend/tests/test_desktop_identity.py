from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.desktop_identity import (
    IdentityError,
    contained_path,
    current_user_sid,
    data_identity_from_keys,
    install_identity_from_key,
    root_path_hash_from_key,
    scope_id_from_keys,
    windows_path_key,
)


@pytest.mark.skipif(os.name != "nt", reason="Windows SID contract")
def test_current_user_sid_uses_the_full_windows_process_handle() -> None:
    assert current_user_sid().startswith("S-1-")


@pytest.mark.skipif(os.name != "nt", reason="Windows path comparison contract")
def test_containment_does_not_normalize_distinct_unicode_siblings(tmp_path: Path) -> None:
    composed_root = tmp_path / "caf\u00e9"
    decomposed_sibling = tmp_path / "cafe\u0301"
    composed_root.mkdir()
    decomposed_sibling.mkdir()
    outside_file = decomposed_sibling / "outside.sqlite3"
    outside_file.write_bytes(b"synthetic")

    with pytest.raises(IdentityError, match="path_outside_root"):
        contained_path(composed_root.resolve(), outside_file, must_exist=True)


def test_cross_language_identity_golden_vectors() -> None:
    owner_sid = "S-1-5-21-1000-2000-3000-1001"
    install_key = "c:\\qa\\stra\u00dfe\\\u0130z\\program"
    data_key = "c:\\qa\\stra\u00dfe\\\u0130z\\data"
    database_key = "db\\caf\u00e9-\u0130z.sqlite3"

    assert windows_path_key("C:/QA/Stra\u00dfe/\u0130Z/Cafe\u0301") == "c:\\qa\\stra\u00dfe\\\u0130z\\caf\u00e9"
    assert root_path_hash_from_key("c:\\qa\\stra\u00dfe\\\u0130z\\caf\u00e9") == (
        "d616ba2ee0e935582ca98fee6fac12c45d82f508a842902c5db4c09defc4a090"
    )
    assert scope_id_from_keys(owner_sid, install_key, data_key) == (
        "7d31ef1b799bec3b4c3054a9a606d17377b19001bdf2b123baa4281a670a1b70"
    )
    assert install_identity_from_key(owner_sid, install_key) == (
        "cb15f4929deff4a46d1d064c1e31462f2cee86178b991cc19571dab04f0826f3"
    )
    assert data_identity_from_keys(owner_sid, data_key, database_key) == (
        "a4d429587970ad4e043888a6d6eb311dd2b644d50748e2e75ee9a27eb7fddfdb"
    )
