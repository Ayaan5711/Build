"""
Tests for PDF text extraction + RAG chunking (src/integrations/pdf_import.py).
Builds a minimal, valid single-page PDF by hand (no new dependency needed
just for test fixtures -- pypdf, already required for reading, is lenient
enough to read this back correctly).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.integrations import pdf_import
from src.knowledge.rag import KnowledgeBase


def _make_simple_pdf(path: str, text: str) -> None:
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 4 0 R >> >> /MediaBox [0 0 612 792] /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    stream = f"BT /F1 18 Tf 72 700 Td ({text}) Tj ET".encode("latin-1")
    objects.append(b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream")

    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref_start = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for off in offsets[1:]:
        out += f"{off:010} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_start}\n%%EOF".encode()

    with open(path, "wb") as f:
        f.write(bytes(out))


def _kb(tmp_path, name):
    return KnowledgeBase(collection_name=f"pdf_test_{name}")


def test_import_pdf_extracts_text_into_kb(tmp_path):
    path = str(tmp_path / "policy.pdf")
    _make_simple_pdf(path, "Attendance policy: students must attend 75 percent of classes")

    kb = _kb(tmp_path, "basic")
    report = pdf_import.import_pdf_to_kb(path, kb)

    assert report.pages == 1
    assert report.chunks_added == 1
    assert not report.warnings

    hits = kb.retrieve("attendance policy", k=1)
    assert hits
    assert "75 percent" in hits[0].content


def test_import_pdf_chunk_title_includes_page_number(tmp_path):
    path = str(tmp_path / "handbook.pdf")
    _make_simple_pdf(path, "Some handbook content")

    kb = _kb(tmp_path, "title")
    pdf_import.import_pdf_to_kb(path, kb)

    hits = kb.retrieve("handbook content", k=1)
    assert "page 1" in hits[0].title.lower()
    assert hits[0].source == "handbook.pdf"


def test_chunk_page_text_splits_long_text_into_multiple_chunks():
    long_text = " ".join(f"word{i}" for i in range(1000))
    chunks = pdf_import._chunk_page_text(long_text, max_words=300)
    assert len(chunks) == 4  # 1000 / 300 -> 4 chunks
    assert all(len(c.split()) <= 300 for c in chunks)


def test_chunk_page_text_empty_string_produces_no_chunks():
    assert pdf_import._chunk_page_text("") == []
    assert pdf_import._chunk_page_text("   ") == []


def test_import_nonexistent_pdf_reports_error_not_crash(tmp_path):
    kb = _kb(tmp_path, "missing")
    report = pdf_import.import_pdf_to_kb(str(tmp_path / "does_not_exist.pdf"), kb)
    assert report.chunks_added == 0
    assert report.warnings
