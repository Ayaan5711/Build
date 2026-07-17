"""
Ingests a PDF's text into the RAG knowledge base -- policies, circulars,
syllabi: unstructured prose that's genuinely a good fit for semantic
search, unlike the structured Excel data (see excel_import.py, which
explains why that data goes into SQLite instead of here).

Scanned/image-only PDFs won't extract any real text -- pypdf reads text
that's actually encoded in the PDF, it doesn't OCR. If extraction comes
back empty, that's the likely cause; OCR is out of scope for now.
"""
import os
from dataclasses import dataclass, field
from typing import List

from pypdf import PdfReader

from src.knowledge.rag import KnowledgeBase

# Keeps each RAG chunk a reasonable retrieval unit -- large enough to carry
# real context, small enough that a match doesn't drag in an entire page of
# unrelated content alongside the relevant sentence.
_CHUNK_MAX_WORDS = 350


@dataclass
class PDFImportReport:
    file: str
    pages: int = 0
    chunks_added: int = 0
    warnings: List[str] = field(default_factory=list)

    def summary(self) -> str:
        lines = [f"{self.file}  ->  {self.pages} page(s), {self.chunks_added} chunk(s) added to the knowledge base"]
        for w in self.warnings:
            lines.append(f"  WARNING: {w}")
        return "\n".join(lines)


def _chunk_page_text(text: str, max_words: int = _CHUNK_MAX_WORDS) -> List[str]:
    words = text.split()
    if not words:
        return []
    return [" ".join(words[i : i + max_words]) for i in range(0, len(words), max_words)]


def import_pdf_to_kb(path: str, kb: KnowledgeBase) -> PDFImportReport:
    filename = os.path.basename(path)
    report = PDFImportReport(file=filename)
    try:
        reader = PdfReader(path)
    except Exception as e:  # noqa: BLE001 -- report the failure, don't crash the whole batch
        report.warnings.append(f"Could not open PDF: {e}")
        return report

    report.pages = len(reader.pages)
    entries = []
    for page_num, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception as e:  # noqa: BLE001
            report.warnings.append(f"Page {page_num}: could not extract text ({e}).")
            continue
        chunks = _chunk_page_text(text)
        for part_num, chunk in enumerate(chunks, start=1):
            title = f"{filename} (page {page_num})" if len(chunks) == 1 else f"{filename} (page {page_num}, part {part_num})"
            entries.append(
                {
                    "id": f"{filename}-p{page_num}-{part_num}",
                    "source": filename,
                    "title": title,
                    "content": chunk,
                }
            )

    if not entries:
        report.warnings.append("No extractable text found -- likely a scanned/image-only PDF (OCR not supported).")
        return report

    kb.seed(entries)
    report.chunks_added = len(entries)
    return report
