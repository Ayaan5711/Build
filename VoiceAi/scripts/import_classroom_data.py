#!/usr/bin/env python
"""
Reads every Excel/PDF file dropped in data/incoming/ (or a folder you pass
in) and imports it: Excel goes into the real SQLite student-records tables
(or data/class_schedule.json for a schedule sheet), PDFs go into the RAG
knowledge base. Prints a report for every file so a wrong guess in the
column-matching is visible immediately -- always read it, don't assume a
clean run means a correct import.

Usage:
    python scripts/import_classroom_data.py [folder]
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd

from src.integrations.excel_import import _detect_file_type, import_excel_file
from src.integrations.pdf_import import import_pdf_to_kb
from src.knowledge.rag import KnowledgeBase, seed_classroom_knowledge_base, seed_default_knowledge_base

# Students first so attendance/marks sheets that reference students by
# name can resolve against an already-known roster instead of
# auto-creating placeholder records (see excel_import.py's
# _resolve_student_id) -- not required for correctness, just avoids
# avoidable warnings in the report.
_TYPE_PRIORITY = {"students": 0, "schedule": 1, "attendance": 2, "marks": 3, "unknown": 4}


def _sort_key(path: str) -> int:
    if not path.lower().endswith((".xlsx", ".xls")):
        return 5
    try:
        df = pd.read_excel(path, nrows=5)
        return _TYPE_PRIORITY.get(_detect_file_type(path, df.columns), 4)
    except Exception:  # noqa: BLE001 -- sorting hint only, the real import will report the actual error
        return 4


def main() -> int:
    default_folder = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "incoming")
    folder = sys.argv[1] if len(sys.argv) > 1 else default_folder
    if not os.path.isdir(folder):
        print(f"No such folder: {folder}")
        return 1

    files = [
        os.path.join(folder, f)
        for f in sorted(os.listdir(folder))
        if f.lower().endswith((".xlsx", ".xls", ".pdf")) and not f.startswith(".")
    ]
    if not files:
        print(f"No .xlsx/.xls/.pdf files found in {folder}.")
        return 0

    files.sort(key=_sort_key)
    print(f"Found {len(files)} file(s) in {folder}\n")

    kb = KnowledgeBase()
    if kb.collection.count() == 0:
        seed_default_knowledge_base(kb)
        seed_classroom_knowledge_base(kb)

    excel_count, pdf_count = 0, 0
    for path in files:
        if path.lower().endswith((".xlsx", ".xls")):
            report = import_excel_file(path)
            excel_count += 1
        else:
            report = import_pdf_to_kb(path, kb)
            pdf_count += 1
        print(report.summary())
        print()

    print(f"Done -- {excel_count} Excel file(s), {pdf_count} PDF(s) processed.")
    print("Review any WARNING/ERROR lines above before trusting the import.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
