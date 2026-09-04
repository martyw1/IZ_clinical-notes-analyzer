from __future__ import annotations

import pytest
from pydantic import TypeAdapter, ValidationError

from app.v2.api.plan_models import TreatmentPlanExportInput


@pytest.mark.parametrize("payload", [
    {}, {"plan_version_ids": [0]}, {"plan_version_ids": [-1]}, {"plan_version_ids": [True]},
    {"plan_version_ids": ["1"]}, {"plan_version_ids": [1.5]}, {"plan_version_ids": [1], "source_mode": "synthetic_fixture"},
    {"plan_version_ids": [1], "name": "synthetic"}, {"plan_version_ids": [1], "search": "synthetic"},
])
def test_export_boundary_rejects_nonidentities_and_search_text(payload: dict) -> None:
    # Given: an invalid immutable ID or a forbidden name/search transport field.
    adapter = TypeAdapter(TreatmentPlanExportInput)
    # When: the request crosses its typed boundary.
    with pytest.raises(ValidationError):
        adapter.validate_python(payload)
    # Then: no coerced identity, synthetic source, or search text reaches export logic.


@pytest.mark.parametrize("source", [None, "manual_upload", "alleva_rest_api"])
def test_export_boundary_preserves_explicit_empty_selection(source: str | None) -> None:
    # Given: a deliberate empty filtered-result identity set.
    payload = {"plan_version_ids": [], "source_mode": source}
    # When: the request crosses the Pydantic boundary.
    parsed = TypeAdapter(TreatmentPlanExportInput).validate_python(payload)
    # Then: explicit emptiness and the optional scope are preserved exactly.
    assert parsed.plan_version_ids == () and parsed.source_mode == source
