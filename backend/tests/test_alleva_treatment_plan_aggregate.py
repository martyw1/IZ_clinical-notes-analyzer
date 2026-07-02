import json
from datetime import date

from app.services.alleva_treatment_plan_aggregate import (
    AggregateBuildOptions,
    build_patient_treatment_plan_aggregate_result,
)


def test_aggregate_builder_links_aliases_and_flags_quality_without_phi():
    result = build_patient_treatment_plan_aggregate_result(
        clients_payload=[
            {
                'id': 'client-source-001',
                'leadId': 'lead-001',
                'clientId': 'client-001',
                'chartId': 'chart-001',
                'mrn': 'mrn-001',
                'uniqueId': 'unique-001',
                'luin': 'luin-001',
                'name': {'clientFullName': 'Jane Q Doe'},
                'status': 'Active',
                'isClient': True,
                'admissionDateTime': '2026-05-01T09:00:00Z',
                'levelOfCare': 'IOP',
                'facilityName': 'Synthetic Facility',
                'primaryClinicians': 'Synthetic Counselor',
            }
        ],
        treatment_plans_payload=[
            {
                'id': 'tp-old',
                'client': {'clientId': 'client-001'},
                'isInitialTP': True,
                'isActive': False,
                'isComplete': True,
                'startDate': '2026-05-01T10:00:00Z',
                'staffSignatureDate': '2026-05-01',
                'clientSignatureDate': '2026-05-01',
            },
            {
                'id': 'tp-current',
                'client': {'id': 'lead-001'},
                'isInitialTP': False,
                'isActive': True,
                'isComplete': True,
                'startDate': '2026-05-10T10:00:00Z',
                'staffSignatureDate': '2026-05-10',
                'clientSignatureDate': '2026-05-10',
                'reasonForAdmission': 'Synthetic admission reason requiring treatment planning',
                'problems': [
                    {
                        'description': 'Jane Q Doe synthetic narrative should not be returned.',
                        'behavioralDefinitions': [{'description': 'withdrawal cravings and isolation increase relapse risk'}],
                        'diagnoses': [{'code': 'F10.20', 'description': 'Jane Q Doe diagnosis text'}],
                        'goals': [
                            {
                                'description': 'Synthetic goal text',
                                'objectives': [
                                    {
                                        'description': 'Synthetic objective text',
                                        'interventions': [{'description': 'Synthetic intervention text'}],
                                    }
                                ],
                            }
                        ],
                    }
                ],
            },
        ],
        treatment_reviews_payload=[
            {
                'id': 'review-001',
                'client': {'luin': 'luin-001'},
                'createdDate': '2026-05-10T12:00:00Z',
                'staffSignatureDate': '2026-05-10',
                'clientSignatureDate': '2026-05-10',
                'nextReviewDueDate': '2026-07-01',
            }
        ],
        client_diagnoses_payload=[
            {'id': 'dx-001', 'clientId': 'client-001', 'code': 'F10.20', 'status': 'Active'},
            {'id': 'dx-002', 'clientId': 'client-001', 'code': 'F11.20', 'status': 'Active'},
        ],
        advanced_form_payloads=[
            {
                'id': 'form-001',
                'clientId': 'client-001',
                'sourceKey': 'tp-current',
                'formId': 'treatment-plan-review-grid',
                'capturedAt': '2026-05-10T12:00:00Z',
                'values': {
                    'signed': True,
                    'score': 4.5,
                    'reviewedAt': '2026-05-10T12:00:00Z',
                    'attachment': {'fileName': 'Jane Q Doe treatment plan.pdf', 'url': 'https://example.test/private'},
                    'note': 'Jane Q Doe free text should be hashed, not returned.',
                },
            }
        ],
        options=AggregateBuildOptions(today=date(2026, 6, 30)),
    )

    assert result.diagnostics['aggregate_count'] == 1
    aggregate = result.aggregates[0]
    assert aggregate['patient_key'] == 'lead:lead-001'
    assert aggregate['patient']['display_name'] is None
    assert aggregate['current_treatment_plan']['source_record_id'] == 'tp-current'
    assert aggregate['current_treatment_plan']['content_summary']['plan_field_count'] >= 3
    assert aggregate['current_treatment_plan']['content_summary']['problem_count'] == 1
    assert aggregate['current_treatment_plan']['content_summary']['diagnosis_count'] == 1
    assert aggregate['current_treatment_plan']['content_summary']['behavioral_definition_count'] == 1
    assert aggregate['current_treatment_plan']['content_summary']['goal_count'] == 1
    assert aggregate['current_treatment_plan']['content_summary']['objective_count'] == 1
    assert aggregate['current_treatment_plan']['content_summary']['intervention_count'] == 1
    assert aggregate['computed_status']['next_review_due_api'] == '2026-07-01'
    assert aggregate['computed_status']['next_review_due_computed'] == '2026-07-09'
    assert aggregate['computed_status']['status'] == 'Needs Review'
    plan_tree = aggregate['current_treatment_plan']['content_tree']
    assert any(field['source_path'] == 'reasonForAdmission' for field in plan_tree['plan_fields'])
    assert plan_tree['problems'][0]['behavioral_definitions'][0]['text'] == 'withdrawal cravings and isolation increase relapse risk'
    assert plan_tree['problems'][0]['goals'][0]['objectives'][0]['interventions'][0]['text'] == 'Synthetic intervention text'
    assert aggregate['current_treatment_plan']['content_structure'] == plan_tree
    assert {issue['code'] for issue in aggregate['data_quality']} >= {
        'active_client_diagnosis_missing_from_current_plan',
        'next_review_due_disagreement',
    }
    assert aggregate['advanced_form_captures'][0]['values']['attachment']['type'] == 'file_or_signature'
    assert aggregate['raw_sources'][0]['payload_hash']
    assert 'raw_payload' not in json.dumps(aggregate)
    serialized = json.dumps(aggregate)
    assert 'Jane Q Doe' not in serialized
    assert 'free text should be hashed' not in serialized
    assert 'treatment plan.pdf' not in serialized


def test_aggregate_builder_rejects_ambiguous_name_fallback_matches():
    result = build_patient_treatment_plan_aggregate_result(
        clients_payload=[
            {'id': 'client-a', 'clientId': 'client-a', 'name': {'clientFullName': 'Shared Synthetic'}, 'status': 'Active'},
            {'id': 'client-b', 'clientId': 'client-b', 'name': {'clientFullName': 'Shared Synthetic'}, 'status': 'Active'},
        ],
        treatment_plans_payload=[{'id': 'tp-ambiguous', 'clientName': 'Shared Synthetic', 'isActive': True}],
        options=AggregateBuildOptions(allow_name_fallback=True, today=date(2026, 6, 30)),
    )

    assert result.diagnostics['aggregate_count'] == 2
    assert result.diagnostics['unmatched_treatment_plan_count'] == 1
    assert result.diagnostics['unmatched_treatment_plans'][0]['reason'] == 'ambiguous_name_match'
    assert all(aggregate['current_treatment_plan'] is None for aggregate in result.aggregates)
