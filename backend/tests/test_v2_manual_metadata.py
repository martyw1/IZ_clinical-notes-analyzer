from __future__ import annotations

import base64
import hashlib
import json

import pytest
from cryptography.fernet import Fernet

from app.v2.services.clinical_snapshot_codec import AggregateSnapshot, ClinicalSnapshotCodec

from app.v2.services.manual_binder import (
    ManualBinderFile,
    ManualBinderRequest,
    aggregate_from_manual_binder,
)
from app.v2.services.manual_file_parser import aggregate_from_manual_file


def test_manual_characterization_keeps_explicit_dates_and_generated_identity() -> None:
    # Given: legacy labeled clinical fields with a generated source identity.
    raw = b"MRN: META-001\nAdmission Date: 2026-01-02\nSignature Date: 2026-01-03"
    expected_hash = hashlib.sha256(b"META-001|" + raw).hexdigest()

    # When: the existing single-file parser receives the source.
    result = aggregate_from_manual_file(raw, "", "synthetic.txt")

    # Then: clinical dates and source-derived identity retain their existing meaning.
    assert result.aggregate.patient_display_label == "MRN META-001"
    assert result.aggregate.patient_full_name == ""
    assert result.aggregate.admission_date == "2026-01-02"
    assert result.aggregate.content_snapshot.signatures[0].signature_datetime == "2026-01-03"
    assert result.aggregate.content_snapshot.plan_id == f"manual-META-001-{expected_hash[:8]}"
    assert result.aggregate.content_snapshot.content_hash == expected_hash


def test_manual_characterization_retains_binder_source_bytes_and_checksums() -> None:
    # Given: two existing sources whose original bytes must be retained.
    sources = (b"MRN: META-002\nAdmission Date: 2026-01-02", b"MRN: META-002\nGoal: Synthetic")
    files = tuple(ManualBinderFile(raw, "synthetic.txt") for raw in sources)

    # When: the source binder is parsed.
    result = aggregate_from_manual_binder(ManualBinderRequest(files, "", False))

    # Then: no original source bytes or checksums are rewritten.
    assert {item.raw_bytes for item in result.sources} == set(sources)
    assert {item.sha256 for item in result.sources} == {hashlib.sha256(raw).hexdigest() for raw in sources}


def test_manual_characterization_does_not_extract_combined_signature_prose() -> None:
    # Given: prose mentions dates without a supported signature-date label.
    raw = b"MRN: META-003\nCompletion and signature: Completed 2026-02-03, signed 2026-02-04"

    # When: the source is parsed.
    aggregate = aggregate_from_manual_file(raw, "", "synthetic.txt").aggregate

    # Then: absent explicit clinical dates remain unknown.
    assert aggregate.admission_date == "Unknown"
    assert aggregate.date_clock_anchor == "Unknown"
    assert aggregate.date_clock_due_date == "Unknown"
    assert aggregate.content_snapshot.signatures[0].signature_datetime == ""


@pytest.mark.parametrize("name_key,service_key", [("patient_name", "service_date"), ("patient_full_name", "serviceDate")])
@pytest.mark.parametrize("suffix", [".txt", ".csv", ".tsv"])
def test_explicit_metadata_aliases_are_plan_local_and_name_is_separate(name_key: str, service_key: str, suffix: str) -> None:
    # Given: explicit metadata uses supported aliases in each existing text/table format.
    fields = ("MRN", name_key, service_key, "original_plan_reference", "signature_datetime")
    values = ("META-004", "SYNTHETIC-NAME-PRIVATE-004", "2026-03-04", "ORIGINAL-PLAN-2026-01-09", "2026-03-05")
    delimiter = "\t" if suffix == ".tsv" else ","
    text = "\n".join(f"{key}: {value}" for key, value in zip(fields, values, strict=True)) if suffix == ".txt" else (
        delimiter.join(fields) + "\n" + delimiter.join(values)
    )

    # When: explicit metadata is parsed into a manual source.
    result = aggregate_from_manual_file(text.encode(), "", "synthetic" + suffix)

    # Then: private identity travels separately and optional dates never become clinical anchors or IDs.
    snapshot = result.aggregate.content_snapshot
    assert result.patient_full_name == values[1]
    assert snapshot.service_date == values[2]
    assert snapshot.original_plan_reference == values[3]
    assert snapshot.signatures[0].signature_datetime == values[4]
    assert result.aggregate.admission_date == "Unknown"
    assert result.aggregate.date_clock_anchor == "Unknown"
    assert snapshot.plan_id.startswith("manual-META-004-")
    assert snapshot.plan_id != values[3]
    assert values[1] not in result.aggregate.model_dump_json()


@pytest.mark.parametrize("reverse", [False, True])
def test_binder_metadata_conflicts_have_no_file_order_winner(reverse: bool) -> None:
    # Given: metadata conflicts in two files, including a date-like original reference.
    files = tuple(ManualBinderFile(
        f"MRN: META-005\npatient_name: SYNTHETIC-NAME-{index}\nservice_date: 2026-04-0{index}\n"
        f"original_plan_reference: PRIVATE-REFERENCE-2026-05-0{index}".encode(),
        f"private-filename-{index}.txt",
    ) for index in (1, 2))
    ordered = tuple(reversed(files)) if reverse else files

    # When: the binder is merged deterministically.
    result = aggregate_from_manual_binder(ManualBinderRequest(ordered, "", False))

    # Then: no conflicting optional value becomes a name/date/reference and warnings contain only field names.
    assert result.patient_full_name == ""
    assert result.aggregate.content_snapshot.service_date == ""
    assert result.aggregate.content_snapshot.original_plan_reference == ""
    assert result.aggregate.overall_status == "Conflicting Evidence"
    assert result.aggregate.admission_date == "Unknown"
    assert result.aggregate.content_snapshot.signatures[0].signature_datetime == ""
    warnings = " ".join(result.warnings)
    assert all(field in warnings for field in ("patient_full_name", "service_date", "original_plan_reference"))
    assert all(value not in warnings for value in ("SYNTHETIC-NAME", "PRIVATE-REFERENCE", "private-filename", "2026-04"))


def test_duplicate_name_alias_conflicts_in_one_source_are_not_overwritten() -> None:
    # Given: two supported name labels disagree inside one source.
    raw = b"MRN: META-006\npatient_name: SYNTHETIC-FIRST\npatient_full_name: SYNTHETIC-SECOND"

    # When: the single file is parsed.
    result = aggregate_from_manual_file(raw, "", "synthetic.txt")

    # Then: last-label selection is not used to assign identity.
    assert result.patient_full_name == ""
    assert result.aggregate.overall_status == "Conflicting Evidence"
    warnings = " ".join(result.aggregate.data_quality_warnings)
    assert "patient_full_name" in warnings
    assert "SYNTHETIC-FIRST" not in warnings and "SYNTHETIC-SECOND" not in warnings


def test_service_date_and_reference_suffix_do_not_supply_signature_or_admission_dates() -> None:
    # Given: dates occur only in optional metadata and unsupported combined prose.
    raw = (b"MRN: META-007\nserviceDate: 2026-06-01\noriginal_plan_reference: Plan-2026-06-02\n"
           b"Completion/signature: completed 2026-06-03; signed 2026-06-04")

    # When: the manual parser handles this source.
    result = aggregate_from_manual_file(raw, "", "synthetic.txt")

    # Then: service/reference are preserved without inventing clinical dates.
    assert result.aggregate.content_snapshot.service_date == "2026-06-01"
    assert result.aggregate.content_snapshot.original_plan_reference == "Plan-2026-06-02"
    assert result.aggregate.admission_date == "Unknown"
    assert result.aggregate.date_clock_anchor == "Unknown"
    assert result.aggregate.date_clock_due_date == "Unknown"
    assert result.aggregate.content_snapshot.signatures[0].signature_datetime == ""


def test_old_encrypted_aggregate_payload_decodes_with_empty_optional_metadata() -> None:
    # Given: an actual encrypted historical aggregate omits the newly optional keys.
    aggregate = aggregate_from_manual_file(b"MRN: META-008", "", "synthetic.txt").aggregate
    payload = aggregate.model_dump(mode="json")
    payload["content_snapshot"].pop("service_date", None)
    payload["content_snapshot"].pop("original_plan_reference", None)
    secret = "synthetic-codec-secret-for-metadata-test"
    key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest())
    encrypted = b"IZCNA1:" + Fernet(key).encrypt(json.dumps(payload).encode())
    original_hash = hashlib.sha256(encrypted).hexdigest()

    # When: the existing codec reads the legacy payload.
    decoded = ClinicalSnapshotCodec(secret).decode_plan(encrypted)

    # Then: compatible defaults apply without rewriting the old encrypted bytes or source identity.
    assert isinstance(decoded, AggregateSnapshot)
    assert decoded.aggregate.content_snapshot.service_date == ""
    assert decoded.aggregate.content_snapshot.original_plan_reference == ""
    assert decoded.aggregate.content_snapshot.plan_id == aggregate.content_snapshot.plan_id
    assert hashlib.sha256(encrypted).hexdigest() == original_hash


@pytest.mark.parametrize("reverse", [False, True])
def test_case_only_reference_differences_are_conflicts_in_single_files_and_binders(reverse: bool) -> None:
    # Given: reference spelling distinguishes source records and must not be case-folded.
    values = ("PLAN-A", "plan-a") if not reverse else ("plan-a", "PLAN-A")
    files = tuple(ManualBinderFile(f"MRN: META-009\noriginal_plan_reference: {value}".encode(), "synthetic.txt") for value in values)
    text = "MRN: META-009\n" + "\n".join(f"original_plan_reference: {value}" for value in values)

    # When: the same conflicting references occur inside one source or across two sources.
    single = aggregate_from_manual_file(text.encode(), "", "synthetic.txt")
    binder = aggregate_from_manual_binder(ManualBinderRequest(files, "", False))

    # Then: both formats retain uncertainty, independent of input order.
    assert single.aggregate.content_snapshot.original_plan_reference == ""
    assert binder.aggregate.content_snapshot.original_plan_reference == ""
    assert single.aggregate.overall_status == binder.aggregate.overall_status == "Conflicting Evidence"


@pytest.mark.parametrize("reverse", [False, True])
def test_equivalent_name_spelling_is_deterministic_in_single_files_and_binders(reverse: bool) -> None:
    # Given: case-only name spelling variants represent the same explicitly labeled name.
    values = ("SYNTHETIC PERSON", "Synthetic Person") if not reverse else ("Synthetic Person", "SYNTHETIC PERSON")
    files = tuple(ManualBinderFile(f"MRN: META-010\npatient_name: {value}".encode(), "synthetic.txt") for value in values)
    text = "MRN: META-010\n" + "\n".join(f"patient_name: {value}" for value in values)

    # When: metadata is parsed either within one source or across a binder.
    single = aggregate_from_manual_file(text.encode(), "", "synthetic.txt")
    binder = aggregate_from_manual_binder(ManualBinderRequest(files, "", False))

    # Then: both use the same deterministic representative without conflict or file-order selection.
    assert single.patient_full_name == binder.patient_full_name == "SYNTHETIC PERSON"
    assert single.aggregate.overall_status == binder.aggregate.overall_status == "Needs Review"


def test_legacy_blank_clinical_labels_keep_existing_empty_value_semantics() -> None:
    # Given: a legacy single text source explicitly clears an earlier clinical date label.
    raw = b"MRN: META-011\nAdmission Date: 2026-01-01\nAdmission Date: \nSignature Date: "

    # When: the metadata-enabled parser reads the legacy source.
    aggregate = aggregate_from_manual_file(raw, "", "synthetic.txt").aggregate

    # Then: optional metadata support does not turn blank clinical fields into prior known values.
    assert aggregate.admission_date == ""
    assert aggregate.content_snapshot.signatures[0].signature_datetime == ""


def test_original_reference_preserves_internal_spacing_and_detects_distinct_values() -> None:
    # Given: reference identifiers contain potentially meaningful internal spacing.
    single_raw = b"MRN: META-012\noriginal_plan_reference:   PLAN  A   "
    files = (ManualBinderFile(single_raw, "synthetic.txt"), ManualBinderFile(b"MRN: META-012\noriginal_plan_reference: PLAN A", "other.txt"))

    # When: one explicit reference is parsed and then compared with a differently spaced binder reference.
    single = aggregate_from_manual_file(single_raw, "", "synthetic.txt")
    binder = aggregate_from_manual_binder(ManualBinderRequest(files, "", False))

    # Then: only surrounding whitespace is trimmed and distinct references remain conflicting.
    assert single.aggregate.content_snapshot.original_plan_reference == "PLAN  A"
    assert binder.aggregate.content_snapshot.original_plan_reference == ""
    assert binder.aggregate.overall_status == "Conflicting Evidence"
