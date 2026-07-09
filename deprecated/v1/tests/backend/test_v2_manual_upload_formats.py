from __future__ import annotations

from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from test_v2_manual_upload import _auth_headers, _fresh_client


def _pdf_with_text(lines: tuple[str, ...]) -> bytes:
    stream_lines = ["BT", "/F1 12 Tf", "72 720 Td"]
    for index, line in enumerate(lines):
        if index:
            stream_lines.append("0 -18 Td")
        stream_lines.append(f"({_pdf_text(line)}) Tj")
    stream_lines.append("ET")
    stream = "\n".join(stream_lines).encode("latin-1")
    objects = (
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream",
    )
    pdf = b"%PDF-1.4\n"
    offsets: list[int] = []
    for object_number, body in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf += f"{object_number} 0 obj\n".encode("ascii") + body + b"\nendobj\n"
    xref_at = len(pdf)
    pdf += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode("ascii")
    for offset in offsets:
        pdf += f"{offset:010d} 00000 n \n".encode("ascii")
    pdf += f"trailer\n<< /Root 1 0 R /Size {len(objects) + 1} >>\nstartxref\n{xref_at}\n%%EOF\n".encode("ascii")
    return pdf


def _pdf_text(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _xlsx_with_rows(rows: tuple[tuple[str, str], ...]) -> bytes:
    from xml.sax.saxutils import escape

    row_xml = []
    for row_number, row in enumerate(rows, start=1):
        cells = []
        for column_number, value in enumerate(row):
            column_name = chr(ord("A") + column_number)
            cells.append(f'<c r="{column_name}{row_number}" t="inlineStr"><is><t>{escape(value)}</t></is></c>')
        row_xml.append(f'<row r="{row_number}">{"".join(cells)}</row>')
    sheet_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData>{"".join(row_xml)}</sheetData></worksheet>'
    )
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as workbook:
        workbook.writestr("[Content_Types].xml", '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
        workbook.writestr("xl/worksheets/sheet1.xml", sheet_xml)
    return output.getvalue()


def test_manual_pdf_file_upload_extracts_text_archives_and_downloads_with_pdf_filename(tmp_path: Path, monkeypatch) -> None:
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    pdf_bytes = _pdf_with_text(
        (
            "Patient ID: 916",
            "Current Level of Care: PHP",
            "Admission Date: 2026-06-02",
            "Intervention: PDF skills practice.",
        )
    )

    imported = client.post(
        "/api/v2/manual-uploads/treatment-plan-file",
        data={"patient_id": ""},
        files={"file": ("manual-treatment-plan.pdf", pdf_bytes, "application/pdf")},
        headers=headers,
    )

    assert imported.status_code == 201
    assert imported.json()["patient_id"] == "916"

    detail = client.get("/api/v2/treatment-plans/916", headers=headers)
    assert detail.status_code == 200
    snapshot = detail.json()["content_snapshot"]
    assert snapshot["problems"][0]["goals"][0]["objectives"][0]["interventions"][0]["intervention_description"] == "PDF skills practice."
    source_document = detail.json()["source_documents"][0]
    assert source_document["source_format"] == "pdf"
    assert source_document["content_type"] == "application/pdf"

    downloaded = client.get(source_document["download_url"], headers=headers)
    assert downloaded.status_code == 200
    assert downloaded.content == pdf_bytes
    assert downloaded.headers["content-disposition"].endswith('.pdf"')


def test_manual_xlsx_file_upload_reads_labeled_cells_archives_and_downloads_with_xlsx_filename(tmp_path: Path, monkeypatch) -> None:
    client = _fresh_client(tmp_path, monkeypatch)
    headers = _auth_headers(client)
    xlsx_bytes = _xlsx_with_rows(
        (
            ("Patient ID", "917"),
            ("Current Level of Care", "IOP"),
            ("Admission Date", "2026-06-05"),
            ("Intervention", "Spreadsheet refusal skills practice."),
        )
    )

    imported = client.post(
        "/api/v2/manual-uploads/treatment-plan-file",
        data={"patient_id": ""},
        files={
            "file": (
                "manual-treatment-plan.xlsx",
                xlsx_bytes,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
        headers=headers,
    )

    assert imported.status_code == 201
    assert imported.json()["patient_id"] == "917"

    detail = client.get("/api/v2/treatment-plans/917", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["current_level_of_care"] == "IOP"
    snapshot = detail.json()["content_snapshot"]
    assert snapshot["problems"][0]["goals"][0]["objectives"][0]["interventions"][0]["intervention_description"] == "Spreadsheet refusal skills practice."
    source_document = detail.json()["source_documents"][0]
    assert source_document["source_format"] == "xlsx"
    assert source_document["content_type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    downloaded = client.get(source_document["download_url"], headers=headers)
    assert downloaded.status_code == 200
    assert downloaded.content == xlsx_bytes
    assert downloaded.headers["content-disposition"].endswith('.xlsx"')
