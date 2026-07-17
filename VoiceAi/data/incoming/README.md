# data/incoming/

Drop real classroom files here, then run:

```bash
python scripts/import_classroom_data.py
```

Supported files:
- **Excel** (`.xlsx`/`.xls`) — student roster, attendance, marks, or class
  schedule. The importer guesses which is which from the filename and the
  column headers it finds (e.g. a file with a "date" and a "present/absent"
  style column is treated as attendance). It prints exactly which columns
  it mapped to which field, and which ones it couldn't figure out --
  **always check that report** before trusting the import.
- **PDF** (`.pdf`) — anything else (policies, circulars, syllabi). Text is
  extracted, chunked, and added to the RAG knowledge base for semantic
  search. Scanned/image-only PDFs won't extract any real text.

Nothing in this folder is committed to git except this file -- these are
real student records (names, attendance, marks), which is exactly the kind
of data the "privacy compliance essential" note in the problem statement
is about. Neither should the database this loads into
(`.student_records.db`, also gitignored).
