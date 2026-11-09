"""Import Alleva staff and client clinician assignments."""
import hashlib
from collections import Counter
from urllib.parse import urlsplit

from sqlalchemy import select, text
from sqlalchemy.dialects.sqlite import insert

from app.v2.models import ImportedCounselor, ImportedClinicianFacility, ImportedClinicianDirectoryRecord
from app.v2.services.imported_counselors import PrimaryCounselorEvidence, save_primary_counselor


def _id(value):
    if isinstance(value, bool):
        return ""
    return str(value).strip() if isinstance(value, (str, int)) else ""


def _text(value):
    return value.strip() if isinstance(value, str) else ""


def _facility_id(value):
    """Only explicit positive IDs or facility resource links; never facility names."""
    if isinstance(value, dict):
        return _facility_id(value.get("id")) or _facility_id(value.get("route")) or _facility_id(value.get("href"))
    raw = _id(value)
    if raw.isdecimal():
        return str(int(raw)) if int(raw) > 0 else ""
    parsed = urlsplit(raw)
    parts = parsed.path.strip("/").split("/")
    if not parsed.scheme and not parsed.netloc and len(parts) == 2 and parts[0] == "facilities":
        return _facility_id(parts[1])
    return ""


def _primary_staff_id(reference):
    if isinstance(reference, str):
        parsed = urlsplit(reference)
        parts = parsed.path.strip("/").split("/")
        return parts[1] if not parsed.scheme and not parsed.netloc and len(parts) == 2 and parts[0] == "users" else ""
    if not isinstance(reference, dict):
        return ""
    staff_id = _id(reference.get("id"))
    route = _text(reference.get("route"))
    if route and _primary_staff_id(route) != staff_id:
        return ""
    return staff_id


def _staff_display_name(user):
    name = user.get("name")
    if not isinstance(name, dict):
        return ""
    return " ".join(filter(None, (_text(name.get("first")), _text(name.get("last")))))


def _name_key(value: str) -> str:
    return " ".join(value.casefold().split())


def persist_alleva_clinicians(db, staff, clients, observed_at, connection_identity, *, staff_complete=True):
    """Snapshot observation time orders assignments because Client has no modified timestamp.

    Map vendor facilities through already reconciled clients. Retain only staff names,
    IDs, roles and verified local facility links; retain incomplete directory records for admin review. Discard other user profile fields.
    """
    counts = {"staff_returned": len(staff), "staff_imported": 0, "staff_missing_display_fields": 0,
              "staff_unmapped_facility": 0, "staff_ambiguous_id": 0, "assignments_linked": 0,
              "assignments_unresolved": 0, "clients_without_primary_link": 0,
              "assignments_linked_by_name": 0, "clients_with_multiple_clinician_names": 0}
    patient_rows = {str(row.source_patient_id): (row.id, row.facility_id) for row in db.execute(text(
        "SELECT id,facility_id,source_patient_id FROM patients WHERE source_system='alleva_rest_api' AND source_patient_id IS NOT NULL"
    ))}
    facilities = {}
    for client in clients:
        patient = patient_rows.get(_id(client.get("id")))
        if patient:
            facilities.setdefault(_facility_id(client.get("facilityId")) or _facility_id(client.get("facility")), set()).add(patient[1])
    by_id = {}
    for user in staff:
        by_id.setdefault(_id(user.get("id")), []).append(user)
    name_counts = Counter(_name_key(_staff_display_name(user)) for user in staff)
    resolved_by_name = {}
    resolved = {}
    for staff_id, candidates in by_id.items():
        if not staff_id or len(candidates) != 1:
            counts["staff_ambiguous_id"] += len(candidates)
            continue
        user = candidates[0]
        display = _staff_display_name(user)
        facility = user.get("facility")
        vendor_facility = _facility_id(facility)
        local_facilities = facilities.get(vendor_facility, set()) if vendor_facility else set()
        if not display:
            counts["staff_missing_display_fields"] += 1
            continue
        if not local_facilities:
            counts["staff_unmapped_facility"] += 1
        scope = "alleva-staff:" + hashlib.sha256((connection_identity + ":" + _text(user.get("tenant"))).encode()).hexdigest()
        evidence = PrimaryCounselorEvidence(scope, staff_id, display)
        db.execute(insert(ImportedCounselor).values(source_scope=scope, staff_id=staff_id, display_name=display)
            .on_conflict_do_update(index_elements=["source_scope", "staff_id"], set_={"display_name": display}))
        counselor_id = db.scalar(select(ImportedCounselor.id).where(ImportedCounselor.source_scope == scope, ImportedCounselor.staff_id == staff_id))
        facility_status = "mapped" if local_facilities else "unmapped" if vendor_facility else "missing"
        db.execute(insert(ImportedClinicianDirectoryRecord).values(counselor_id=counselor_id,
            source_role=_text(user.get("role")), facility_status=facility_status)
            .on_conflict_do_update(index_elements=["counselor_id"], set_={"source_role": _text(user.get("role")), "facility_status": facility_status}))
        for facility_id in local_facilities:
            db.execute(insert(ImportedClinicianFacility).values(counselor_id=counselor_id, facility_id=facility_id, source_role=_text(user.get("role")))
                .on_conflict_do_update(index_elements=["counselor_id", "facility_id"], set_={"source_role": _text(user.get("role"))}))
        counts["staff_imported"] += 1
        resolved[staff_id] = evidence
        name_key = _name_key(display)
        if staff_complete and name_counts[name_key] == 1:
            resolved_by_name[name_key] = evidence
    for client in clients:
        patient = patient_rows.get(_id(client.get("id")))
        if patient is None:
            continue
        reference = client.get("primaryClinician")
        supplied_names = _text(client.get("primaryClinicians"))
        evidence = resolved.get(_primary_staff_id(reference))
        # An explicit but unresolved reference must not be replaced by a name match.
        if reference is None and supplied_names:
            if any(separator in supplied_names for separator in (",", ";", "|", "\n", "\r")):
                counts["clients_with_multiple_clinician_names"] += 1
            else:
                evidence = resolved_by_name.get(_name_key(supplied_names))
                if evidence:
                    counts["assignments_linked_by_name"] += 1
        if evidence:
            counts["assignments_linked"] += 1
        else:
            counts["assignments_unresolved" if reference or supplied_names else "clients_without_primary_link"] += 1
            # A refreshed missing or contradictory relationship clears the current assignment.
            scope = "alleva-staff:" + hashlib.sha256(connection_identity.encode()).hexdigest()
            evidence = PrimaryCounselorEvidence(scope, "", "")
        save_primary_counselor(db, patient[0], evidence, observed_at)

    return counts
