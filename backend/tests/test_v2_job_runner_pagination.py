from __future__ import annotations

import hashlib
from types import SimpleNamespace

import httpx

from app.v2.services.job_runner import MAX_DIAGNOSTIC_RECORDS, fetch_paged_records


class _RepeatingPageClient:
    def __init__(self, **_: object) -> None:
        pass

    def __enter__(self) -> _RepeatingPageClient:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def post(self, url: str, **_: object) -> httpx.Response:
        return httpx.Response(
            200,
            request=httpx.Request("POST", url),
            json={"access_token": "synthetic-token", "token_type": "Bearer"},
        )

    def get(self, url: str, **_: object) -> httpx.Response:
        return httpx.Response(
            200,
            request=httpx.Request("GET", url),
            json=[{"id": "synthetic-1"}, {"id": "synthetic-2"}],
        )

    def build_request(self, method: str, url: str, **kwargs: object) -> httpx.Request:
        return httpx.Request(method, url, params=kwargs.get("params"), headers=kwargs.get("headers"))

    def send(self, request: httpx.Request, *, stream: bool = False) -> httpx.Response:
        response = self.get(str(request.url).split("?", 1)[0])
        response.request = request
        return response


def test_diagnostic_pull_stops_when_vendor_repeats_a_full_page(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("app.v2.services.job_runner.httpx.Client", _RepeatingPageClient)
    updates: list[dict[str, object]] = []
    connection = SimpleNamespace(
        token_url="https://synthetic.invalid/token",
        client_id="synthetic-client",
        client_secret="synthetic-secret",
        scope="synthetic.read",
        token_auth_style="body",
        timeout_seconds=5,
        api_base_url="https://synthetic.invalid",
        page_size=2,
    )

    result = fetch_paged_records(
        job_id="synthetic-job",
        connection=connection,
        output_dir=tmp_path,
        is_cancelled=lambda: False,
        update=lambda **values: updates.append(values),
    )

    assert result.status == "completed_with_warnings"
    assert len(result.rows) == 2
    assert updates[-1]["warnings_count"] == 1


class _OversizedRecordPageClient(_RepeatingPageClient):
    def get(self, url: str, **_: object) -> httpx.Response:
        return httpx.Response(
            200,
            request=httpx.Request("GET", url),
            json=[{"id": f"synthetic-{index}"} for index in range(MAX_DIAGNOSTIC_RECORDS + 50)],
        )


def test_diagnostic_pull_never_writes_beyond_the_record_cap(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("app.v2.services.job_runner.httpx.Client", _OversizedRecordPageClient)
    connection = SimpleNamespace(
        token_url="https://synthetic.invalid/token",
        client_id="synthetic-client",
        client_secret="synthetic-secret",
        scope="synthetic.read",
        token_auth_style="body",
        timeout_seconds=5,
        api_base_url="https://synthetic.invalid",
        page_size=MAX_DIAGNOSTIC_RECORDS + 50,
    )

    result = fetch_paged_records(
        job_id="bounded-job",
        connection=connection,
        output_dir=tmp_path,
        is_cancelled=lambda: False,
        update=lambda **_: None,
    )

    assert result.status == "completed_with_warnings"
    assert len(result.rows) == MAX_DIAGNOSTIC_RECORDS
    assert all(str(row["record_id"]).startswith("hmac-sha256:") for row in result.rows)
    naive_public_hash = hashlib.sha256("bounded-job:synthetic-0".encode("utf-8")).hexdigest()
    assert result.rows[0]["record_id"] != f"hmac-sha256:{naive_public_hash}"
    artifact = (tmp_path / "all-treatment-plans.all-fields.redacted.jsonl").read_text(encoding="utf-8")
    assert "synthetic-0" not in artifact
