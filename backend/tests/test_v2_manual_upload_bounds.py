from __future__ import annotations

from io import BytesIO
import pytest
from fastapi import UploadFile
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from app.v2.api import manual_binder_routes
from app.v2.services import manual_file_extractors
from app.v2.services.manual_binder import ManualBinderLimits
from app.v2.services.manual_file_types import ManualFileParseError


class RecordingStream(BytesIO):
    def __init__(self, content: bytes) -> None:
        super().__init__(content)
        self.read_sizes: list[int] = []

    def read(self, size: int = -1) -> bytes:
        self.read_sizes.append(size)
        return super().read(size)


def test_binder_reads_only_remaining_total_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: a binder whose second file exceeds the remaining total allowance.
    monkeypatch.setattr(manual_binder_routes, "DEFAULT_BINDER_LIMITS", ManualBinderLimits(40, 10, 12))
    first = RecordingStream(b"1234567890")
    second = RecordingStream(b"1234567890")
    uploads = (UploadFile(first, filename="synthetic-a.txt"), UploadFile(second, filename="synthetic-b.txt"))

    # When: the file reader enforces the cumulative limit.
    with pytest.raises(ManualFileParseError) as error:
        manual_binder_routes._read_binder_files(uploads)

    # Then: it reads only the remaining budget plus one overflow byte.
    assert error.value.status_code == 413
    assert first.read_sizes == [11]
    assert second.read_sizes == [3]


class SyntheticPdfPage:
    def __init__(self, text: str) -> None:
        self.text = text
        self.calls = 0

    def extract_text(self) -> str:
        self.calls += 1
        return self.text


class SyntheticPdfReader:
    def __init__(self, pages: list[SyntheticPdfPage]) -> None:
        self.pages = pages


def test_pdf_stops_before_extracting_later_pages_when_text_limit_exceeded(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: a small extraction budget exceeded before the final synthetic page.
    pages = [SyntheticPdfPage("12345"), SyntheticPdfPage("67890"), SyntheticPdfPage("must not be extracted")]
    monkeypatch.setattr(manual_file_extractors, "MAX_EXTRACTED_TEXT_CHARS", 10)
    monkeypatch.setattr(manual_file_extractors, "PdfReader", lambda stream: SyntheticPdfReader(pages))

    # When: PDF extraction reaches the first overflowing page.
    with pytest.raises(ManualFileParseError):
        manual_file_extractors.extract_manual_file(b"synthetic PDF", "synthetic.pdf")

    # Then: subsequent expensive page extraction never runs.
    assert [page.calls for page in pages] == [1, 1, 0]


def test_pdf_preserves_join_and_strip_semantics_at_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: boundary-sized content with blank pages and surrounding whitespace.
    pages = [SyntheticPdfPage("  A  "), SyntheticPdfPage(""), SyntheticPdfPage(" B  ")]
    monkeypatch.setattr(manual_file_extractors, "MAX_EXTRACTED_TEXT_CHARS", 7)
    monkeypatch.setattr(manual_file_extractors, "PdfReader", lambda stream: SyntheticPdfReader(pages))

    # When: text is extracted.
    result = manual_file_extractors.extract_manual_file(b"synthetic PDF", "synthetic.pdf")

    # Then: interior whitespace is preserved and only the document edges are trimmed.
    assert result.raw_text == "A  \n\n B"


def test_pdf_extracts_real_text_document_without_truncation() -> None:
    # Given: a real two-page PDF containing synthetic text.
    output = BytesIO()
    writer = PdfWriter()
    for text in ("Patient ID: SYNTHETIC-BOUNDARY", "Intervention: Synthetic practice."):
        page = writer.add_blank_page(width=612, height=792)
        font = DictionaryObject({
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        })
        page[NameObject("/Resources")] = DictionaryObject({
            NameObject("/Font"): DictionaryObject({NameObject("/F1"): font}),
        })
        content = DecodedStreamObject()
        content.set_data(f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode("ascii"))
        page[NameObject("/Contents")] = content
    writer.write(output)

    # When: the actual PDF parser extracts the document.
    result = manual_file_extractors.extract_manual_file(output.getvalue(), "synthetic.pdf")

    # Then: both pages remain available to the deterministic field parser.
    assert result.raw_text == "Patient ID: SYNTHETIC-BOUNDARY\nIntervention: Synthetic practice."
