from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Final
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.v2.services.manual_file_types import ManualFileParseError

MAX_EXTRACTED_TEXT_CHARS: Final = 96 * 1024
XLSX_MAIN_NS: Final = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
XLSX_WORKSHEET_PREFIX: Final = "xl/worksheets/"


@dataclass(frozen=True, slots=True)
class ExtractedManualFile:
    raw_text: str
    source_format: str


def extract_manual_file(raw_bytes: bytes, filename: str) -> ExtractedManualFile:
    suffix = Path(filename).suffix.lower()
    match suffix:
        case ".txt":
            return ExtractedManualFile(raw_text=_decode_text_upload(raw_bytes), source_format="text")
        case ".md":
            return ExtractedManualFile(raw_text=_decode_text_upload(raw_bytes), source_format="markdown")
        case ".csv":
            return ExtractedManualFile(raw_text=_decode_text_upload(raw_bytes), source_format="csv")
        case ".tsv":
            return ExtractedManualFile(raw_text=_decode_text_upload(raw_bytes), source_format="tsv")
        case ".pdf":
            return ExtractedManualFile(raw_text=_extract_pdf_text(raw_bytes), source_format="pdf")
        case ".xlsx":
            return ExtractedManualFile(raw_text=_extract_xlsx_text(raw_bytes), source_format="xlsx")
        case _:
            raise ManualFileParseError("Supported manual treatment-plan files are .txt, .md, .csv, .tsv, .pdf, and .xlsx.")


def _decode_text_upload(raw_bytes: bytes) -> str:
    try:
        text = raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ManualFileParseError("Manual text, Markdown, CSV, and TSV treatment-plan files must be UTF-8.") from exc
    return _bounded_non_empty_text(text, "Manual treatment-plan file is empty.")


def _extract_pdf_text(raw_bytes: bytes) -> str:
    try:
        reader = PdfReader(BytesIO(raw_bytes))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
    except PdfReadError as exc:
        raise ManualFileParseError("Manual PDF treatment-plan file could not be read.") from exc
    return _bounded_non_empty_text(text, "Manual PDF treatment-plan file did not contain extractable text.")


def _extract_xlsx_text(raw_bytes: bytes) -> str:
    try:
        with ZipFile(BytesIO(raw_bytes)) as workbook:
            text = _xlsx_rows_to_labeled_text(_xlsx_rows(workbook))
    except BadZipFile as exc:
        raise ManualFileParseError("Manual XLSX treatment-plan file could not be read.") from exc
    except ElementTree.ParseError as exc:
        raise ManualFileParseError("Manual XLSX treatment-plan file contains invalid worksheet XML.") from exc
    return _bounded_non_empty_text(text, "Manual XLSX treatment-plan file must include labeled treatment-plan fields.")


def _bounded_non_empty_text(text: str, empty_message: str) -> str:
    stripped = text.strip()
    if not stripped:
        raise ManualFileParseError(empty_message)
    if len(stripped) > MAX_EXTRACTED_TEXT_CHARS:
        raise ManualFileParseError("Manual treatment-plan extracted text is limited to 96 KiB for the local desktop beta.")
    return stripped


def _xlsx_rows(workbook: ZipFile) -> tuple[tuple[str, ...], ...]:
    shared_strings = _xlsx_shared_strings(workbook)
    rows: list[tuple[str, ...]] = []
    worksheet_names = sorted(
        name for name in workbook.namelist() if name.startswith(XLSX_WORKSHEET_PREFIX) and name.endswith(".xml")
    )
    for worksheet_name in worksheet_names:
        root = ElementTree.fromstring(workbook.read(worksheet_name))
        for row in root.findall(f".//{XLSX_MAIN_NS}sheetData/{XLSX_MAIN_NS}row"):
            cells = tuple(_xlsx_cell_text(cell, shared_strings).strip() for cell in row.findall(f"{XLSX_MAIN_NS}c"))
            if any(cells):
                rows.append(cells)
    return tuple(rows)


def _xlsx_shared_strings(workbook: ZipFile) -> tuple[str, ...]:
    try:
        raw_xml = workbook.read("xl/sharedStrings.xml")
    except KeyError:
        return ()
    root = ElementTree.fromstring(raw_xml)
    return tuple("".join(text.text or "" for text in item.iter(f"{XLSX_MAIN_NS}t")) for item in root.findall(f"{XLSX_MAIN_NS}si"))


def _xlsx_cell_text(cell: ElementTree.Element, shared_strings: tuple[str, ...]) -> str:
    cell_type = cell.attrib.get("t", "")
    match cell_type:
        case "inlineStr":
            return "".join(text.text or "" for text in cell.iter(f"{XLSX_MAIN_NS}t"))
        case "s":
            index_text = _xlsx_cell_value(cell)
            if not index_text:
                return ""
            try:
                index = int(index_text)
            except ValueError as exc:
                raise ManualFileParseError("Manual XLSX treatment-plan file contains an invalid shared string reference.") from exc
            if 0 <= index < len(shared_strings):
                return shared_strings[index]
            return ""
        case _:
            return _xlsx_cell_value(cell)


def _xlsx_cell_value(cell: ElementTree.Element) -> str:
    value = cell.find(f"{XLSX_MAIN_NS}v")
    return value.text if value is not None and value.text is not None else ""


def _xlsx_rows_to_labeled_text(rows: tuple[tuple[str, ...], ...]) -> str:
    cleaned = tuple(tuple(cell for cell in row if cell) for row in rows)
    if not cleaned:
        return ""
    if all(len(row) == 2 for row in cleaned):
        return "\n".join(f"{row[0]}: {row[1]}" for row in cleaned)
    if len(cleaned) >= 2:
        headers = cleaned[0]
        values = cleaned[1]
        return "\n".join(f"{header}: {value}" for header, value in zip(headers, values, strict=False) if header and value)
    return ""
