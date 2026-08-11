from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from fastapi import FastAPI
from fastapi.routing import APIRoute


ROUTE_FAMILIES: Final = {
    "public_runtime": frozenset(
        {
            ("GET", "/api/health"),
            ("GET", "/health"),
            ("GET", "/api/readiness"),
            ("GET", "/api/version"),
            ("GET", "/api/api-configuration/sample-openapi.json"),
        }
    ),
    "authentication_self": frozenset(
        {
            ("POST", "/api/auth/login"),
            ("GET", "/api/users/me"),
            ("POST", "/api/users/me/change-password"),
        }
    ),
    "access_administration": frozenset(
        {
            ("GET", "/api/users"),
            ("POST", "/api/users"),
            ("PATCH", "/api/users/{user_id}"),
            ("POST", "/api/users/{user_id}/reset-password"),
            ("GET", "/api/facilities"),
            ("PUT", "/api/users/{user_id}/facilities/{facility_id}"),
            ("PUT", "/api/patient-assignments/{patient_id}/{counselor_username}"),
        }
    ),
    "admin_configuration": frozenset(
        {
            ("GET", "/api/settings"),
            ("PATCH", "/api/settings"),
            ("GET", "/api/api-configuration"),
            ("PATCH", "/api/api-configuration"),
            ("POST", "/api/api-configuration/pull-definitions"),
            ("POST", "/api/api-configuration/test-connectivity"),
            ("POST", "/api/api-configuration/test-operation"),
            ("POST", "/api/v2/api-harness/jobs"),
            ("GET", "/api/v2/api-harness/jobs"),
            ("GET", "/api/v2/api-harness/jobs/{job_id}"),
            ("POST", "/api/v2/api-harness/jobs/{job_id}/cancel"),
            ("GET", "/api/v2/api-harness/jobs/{job_id}/artifacts"),
            ("GET", "/api/v2/api-harness/jobs/{job_id}/artifacts/{artifact_id}"),
            ("GET", "/api/v2/api-harness/jobs/{job_id}/preview"),
            ("POST", "/api/v2/alleva-sync/run"),
            ("GET", "/api/v2/alleva-sync/jobs/{job_id}"),
            ("GET", "/api/v2/alleva-sync-last-run"),
            ("POST", "/api/v2/alleva-sync/jobs/{job_id}/resume"),
            ("POST", "/api/v2/patient-roster/pull"),
            ("GET", "/api/v2/patient-roster/jobs/latest"),
            ("GET", "/api/v2/patient-roster/jobs/{job_id}"),
        }
    ),
    "audit": frozenset({("GET", "/api/audit/logs"), ("GET", "/api/audit/verify")}),
    "workflow_definition": frozenset(
        {
            ("GET", "/api/workflow-definitions"),
            ("POST", "/api/workflow-definitions"),
            ("POST", "/api/workflow-definitions/{profile_id}/versions/{version_id}/publish"),
        }
    ),
    "patient_read": frozenset(
        {
            ("GET", "/api/v2/navigation"),
            ("GET", "/api/v2/dashboard"),
            ("GET", "/api/v2/treatment-plans"),
            ("GET", "/api/v2/treatment-plans/{patient_id}"),
            ("GET", "/api/v2/treatment-plans/{patient_id}/{treatment_plan_id}"),
            ("GET", "/api/v2/patients/{patient_id}"),
            ("GET", "/api/v2/patient-roster"),
            ("GET", "/api/v2/treatment-plan-roster"),
        }
    ),
    "patient_manager": frozenset(
        {
            ("POST", "/api/v2/treatment-plans/{patient_id}/manager-actions"),
            ("POST", "/api/v2/treatment-plans/{patient_id}/evaluations/refresh"),
            ("POST", "/api/v2/manual-uploads/treatment-plan-aggregate"),
            ("POST", "/api/v2/manual-uploads/treatment-plan-file"),
            ("DELETE", "/api/v2/treatment-plans/{patient_id}/source-documents/{source_file_id}"),
            ("GET", "/api/v2/treatment-plans/{patient_id}/source-documents/{source_file_id}/download"),
            ("GET", "/api/v2/exports/{patient_id}/checklist-evidence.csv"),
            ("GET", "/api/v2/exports/treatment-plans.csv"),
        }
    ),
    "correction": frozenset(
        {
            ("GET", "/api/v2/corrections"),
            ("POST", "/api/v2/treatment-plans/{patient_id}/correction-submissions"),
        }
    ),
}


@dataclass(frozen=True, slots=True)
class RouteClassificationError(RuntimeError):
    reason: str

    def __str__(self) -> str:
        return self.reason


def assert_routes_classified(api: FastAPI) -> None:
    classified = frozenset(route for routes in ROUTE_FAMILIES.values() for route in routes)
    actual = frozenset(
        (method, route.path)
        for route in api.routes
        if isinstance(route, APIRoute)
        for method in route.methods
    )
    unclassified = actual - classified
    if unclassified:
        raise RouteClassificationError("Unclassified API route is denied by default")
