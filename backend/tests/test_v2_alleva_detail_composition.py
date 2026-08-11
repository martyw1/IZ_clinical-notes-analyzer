from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from test_v2_manual_patient_correction import _fresh_client


def test_alleva_detail_preserves_every_nested_clinical_piece_and_signature(tmp_path, monkeypatch) -> None:
    _fresh_client(tmp_path, monkeypatch)

    from app.v2.db import SessionLocal
    from app.v2.models import AppSetting
    from app.v2.services.alleva_contracts import (
        ApprovedAllevaContract,
        _builtin_contract_payload,
    )
    from app.v2.services.alleva_sync import _aggregate_from_payload

    with SessionLocal() as database:
        profile = database.execute(select(AppSetting)).scalar_one()
        now = datetime.now(timezone.utc)
        contract = ApprovedAllevaContract(
            approval_id=0,
            contract_version="synthetic-detail-composition",
            contract_sha256="0" * 64,
            effective_at=now,
            approved_at=now,
            payload=_builtin_contract_payload(
                profile,
                contract_version="synthetic-detail-composition",
                effective_at=now,
            ),
        )

    detail = {
        "id": "plan-complete",
        "client": "/clients/source-complete",
        "startDate": "2026-01-03T09:00:00Z",
        "createdDate": "2026-01-02T08:00:00Z",
        "lastModified": "2026-02-04T17:30:00Z",
        "reasonForAdmission": "Synthetic reason.",
        "initialClientNeeds": "Synthetic initial needs.",
        "familyEducationNeeds": "Synthetic family education needs.",
        "problems": [
            {
                "id": 11,
                "description": "Synthetic problem one.",
                "diagnoses": [
                    {"id": 111, "description": "Synthetic diagnosis one.", "icD10Code": "F10.20"},
                    {"id": 112, "description": "Synthetic diagnosis two.", "icD10Code": "F41.1"},
                ],
                "behavioralDefinitions": [
                    {"id": 121, "description": "Synthetic behavior one."},
                    {"id": 122, "description": "Synthetic behavior two."},
                ],
                "goals": [
                    {
                        "id": 131,
                        "description": "Synthetic goal one.",
                        "objectives": [
                            {
                                "id": 141,
                                "description": "Synthetic objective one.",
                                "interventions": [
                                    {"id": 151, "description": "Synthetic intervention one."},
                                    {"id": 152, "description": "Synthetic intervention two."},
                                ],
                            }
                        ],
                    }
                ],
            },
            {
                "id": 21,
                "description": "Synthetic problem two.",
                "diagnoses": [{"id": 211, "description": "Synthetic diagnosis three.", "icD10Code": "F32.9"}],
                "behavioralDefinitions": [],
                "goals": [],
            },
        ],
        "clientSignature": {
            "entityId": 1,
            "signatureDateTime": "2026-02-03T10:00:00Z",
            "data": "synthetic-base64-omitted",
        },
        "guardianSignature": {
            "entityId": 2,
            "signatureDateTime": "2026-02-03T11:00:00Z",
            "data": "synthetic-base64-omitted",
        },
    }

    aggregate = _aggregate_from_payload(
        "MRN-SYNTHETIC-1",
        {"id": "source-complete", "mrn": "MRN-SYNTHETIC-1"},
        {"id": "plan-complete", "client": {"id": "source-complete", "route": "/clients/source-complete"}},
        detail,
        "plan-complete",
        contract,
    )

    assert [problem.problem_description for problem in aggregate.content_snapshot.problems] == [
        "Synthetic problem one.",
        "Synthetic problem two.",
    ]
    assert [diagnosis["diagnosis_description"] for diagnosis in aggregate.content_snapshot.problems[0].diagnoses] == [
        "Synthetic diagnosis one.",
        "Synthetic diagnosis two.",
    ]
    assert len(aggregate.content_snapshot.problems[0].behavioral_definitions) == 2
    assert len(aggregate.content_snapshot.problems[0].goals[0].objectives[0].interventions) == 2
    assert [signature.signature_type for signature in aggregate.content_snapshot.signatures] == [
        "clientSignature",
        "guardianSignature",
    ]
    assert all(signature.has_signature_data for signature in aggregate.content_snapshot.signatures)
    assert aggregate.source_last_updated == "2026-02-04T17:30:00Z"
    assert aggregate.treatment_plans[0]["plan_date"] == "2026-01-03T09:00:00Z"
