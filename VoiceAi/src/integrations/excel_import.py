"""
Turns "drop a file in a folder" into real imported data, without needing
to know the exact column names in advance. Two guesses are made, both
reported clearly rather than applied silently: (1) what KIND of file this
is (roster / attendance / marks / class schedule), from the filename and,
if that's ambiguous, from which columns are present; (2) which actual
column header means which canonical field, via a fuzzy synonym match.

Every import returns an ImportReport instead of just doing the work
silently -- exactly the same "never fail silently, always show what was
understood" principle used everywhere else in this codebase (the mock
ASR/vision fixes, NFR-03 fallback logging, the confirm-before-action
pattern). A wrong guess here would corrupt real student data, so the
report is not optional: always read it after an import.
"""
import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import pandas as pd

from src.integrations import student_records

_SCHEDULE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "class_schedule.json"
)


@dataclass
class ImportReport:
    file: str
    detected_type: str  # "students" | "attendance" | "marks" | "schedule" | "unknown"
    rows_seen: int = 0
    rows_imported: int = 0
    mapped_columns: Dict[str, str] = field(default_factory=dict)  # canonical field -> actual header
    unmapped_columns: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    def summary(self) -> str:
        lines = [f"{self.file}  ->  detected as: {self.detected_type}"]
        if self.detected_type == "unknown":
            lines.append("  Could not confidently identify this file -- no rows imported.")
            return "\n".join(lines)
        lines.append(f"  rows seen: {self.rows_seen}, rows imported: {self.rows_imported}")
        if self.mapped_columns:
            lines.append("  mapped columns:")
            for field_name, header in self.mapped_columns.items():
                lines.append(f"    {field_name:<12} <- {header!r}")
        if self.unmapped_columns:
            lines.append(f"  unmapped columns (ignored): {self.unmapped_columns}")
        for w in self.warnings:
            lines.append(f"  WARNING: {w}")
        for e in self.errors:
            lines.append(f"  ERROR: {e}")
        return "\n".join(lines)


# ---------------------------------------------------------- header matching --
def _normalize_header(h: str) -> str:
    h = str(h).strip().lower()
    h = re.sub(r"[_/\-.]+", " ", h)
    h = re.sub(r"\s+", " ", h)
    return h.strip()


# Synonym lists, checked in order -- first match wins. Deliberately plain
# substring/equality checks, not a fuzzy-distance library: these are short,
# predictable header strings (not free text), so simple and inspectable
# beats a dependency that could match something unexpected.
_SYNONYMS = {
    "student_id": ["student id", "studentid", "roll no", "roll number", "id", "admission no", "admission number", "enrollment no", "reg no", "registration no"],
    "name": ["name", "student name", "full name", "pupil name"],
    "class_name": ["class", "section", "grade", "std", "standard", "class section"],
    "date": ["date", "attendance date", "day"],
    "status": ["status", "attendance", "present absent", "p a"],
    "subject": ["subject", "course", "paper"],
    "exam": ["exam", "exam name", "test", "assessment", "term"],
    "score": ["score", "marks", "marks obtained", "obtained marks", "total"],
    "max_score": ["max marks", "total marks", "out of", "max score", "full marks"],
    "start_time": ["start time", "start", "from", "period start"],
    "end_time": ["end time", "end", "to", "period end"],
    "room": ["room", "venue", "location"],
}


def _find_column(normalized_to_original: Dict[str, str], field_name: str) -> Optional[str]:
    for synonym in _SYNONYMS.get(field_name, []):
        if synonym in normalized_to_original:
            return normalized_to_original[synonym]
    return None


def _map_columns(columns, wanted: List[str]) -> Dict[str, str]:
    normalized_to_original = {_normalize_header(c): c for c in columns}
    mapped = {}
    for field_name in wanted:
        found = _find_column(normalized_to_original, field_name)
        if found:
            mapped[field_name] = found
    return mapped


# --------------------------------------------------------------- dispatch --
def _detect_file_type(filename: str, columns) -> str:
    lower = os.path.basename(filename).lower()
    normalized_cols = {_normalize_header(c) for c in columns}

    if "attend" in lower:
        return "attendance"
    if any(k in lower for k in ("mark", "grade", "score", "exam", "midterm", "final")):
        return "marks"
    if "student" in lower and any(k in lower for k in ("master", "roster", "data", "list")):
        return "students"
    if any(k in lower for k in ("schedule", "timetable")) or "faculty" in lower:
        return "schedule"

    # Filename didn't say -- fall back to guessing from which columns exist.
    has_date = bool(_SYNONYMS["date"][0] in normalized_cols or any(s in normalized_cols for s in _SYNONYMS["date"]))
    has_status = any(s in normalized_cols for s in _SYNONYMS["status"])
    has_score = any(s in normalized_cols for s in _SYNONYMS["score"])
    has_time = any(s in normalized_cols for s in _SYNONYMS["start_time"])
    has_class_only = any(s in normalized_cols for s in _SYNONYMS["class_name"]) and not (has_date or has_score or has_time)

    if has_date and has_status:
        return "attendance"
    if has_score:
        return "marks"
    if has_time:
        return "schedule"
    if has_class_only:
        return "students"
    return "unknown"


def import_excel_file(path: str) -> ImportReport:
    filename = os.path.basename(path)
    try:
        df = pd.read_excel(path)
    except Exception as e:  # noqa: BLE001 -- report the failure, don't crash the whole batch
        report = ImportReport(file=filename, detected_type="unknown")
        report.errors.append(f"Could not read file: {e}")
        return report

    file_type = _detect_file_type(filename, df.columns)
    if file_type == "students":
        return _import_students(df, filename)
    if file_type == "attendance":
        return _import_attendance(df, filename)
    if file_type == "marks":
        return _import_marks(df, filename)
    if file_type == "schedule":
        return _import_schedule(df, filename)

    report = ImportReport(file=filename, detected_type="unknown")
    report.warnings.append(f"Columns found: {list(df.columns)} -- none matched a known pattern confidently enough to guess.")
    return report


def _unmapped(columns, mapped: Dict[str, str]) -> List[str]:
    mapped_originals = set(mapped.values())
    return [c for c in columns if c not in mapped_originals]


# ---------------------------------------------------------------- students --
def _import_students(df: pd.DataFrame, filename: str) -> ImportReport:
    report = ImportReport(file=filename, detected_type="students", rows_seen=len(df))
    mapped = _map_columns(df.columns, ["student_id", "name", "class_name"])
    report.mapped_columns = mapped
    report.unmapped_columns = _unmapped(df.columns, mapped)

    if "name" not in mapped:
        report.errors.append("No 'name' column found -- cannot import any rows without it.")
        return report
    if "student_id" not in mapped:
        report.warnings.append("No student ID column found -- using the student's name as their ID instead.")

    for _, row in df.iterrows():
        name = str(row[mapped["name"]]).strip()
        if not name or name.lower() == "nan":
            continue
        student_id = str(row[mapped["student_id"]]).strip() if "student_id" in mapped else name
        class_name = str(row[mapped["class_name"]]).strip() if "class_name" in mapped else "unspecified"
        student_records.upsert_student(student_id, name, class_name)
        report.rows_imported += 1
    return report


# -------------------------------------------------------------- attendance --
_PRESENT_VALUES = {"present", "p", "1", "yes", "y", "true"}
_ABSENT_VALUES = {"absent", "a", "0", "no", "n", "false"}


def _normalize_status(raw) -> Optional[str]:
    val = str(raw).strip().lower()
    if val in _PRESENT_VALUES:
        return "present"
    if val in _ABSENT_VALUES:
        return "absent"
    return None


def _import_attendance(df: pd.DataFrame, filename: str) -> ImportReport:
    report = ImportReport(file=filename, detected_type="attendance", rows_seen=len(df))
    mapped = _map_columns(df.columns, ["student_id", "name", "date", "status"])
    report.mapped_columns = mapped
    report.unmapped_columns = _unmapped(df.columns, mapped)

    if "date" not in mapped or "status" not in mapped:
        report.errors.append("Need both a date column and a present/absent status column -- neither found confidently.")
        return report
    if "student_id" not in mapped and "name" not in mapped:
        report.errors.append("No student ID or name column found -- cannot tell whose attendance this is.")
        return report

    unresolved_names = set()
    for _, row in df.iterrows():
        status = _normalize_status(row[mapped["status"]])
        if status is None:
            report.warnings.append(f"Unrecognized status value {row[mapped['status']]!r} -- row skipped.")
            continue
        date_val = pd.to_datetime(row[mapped["date"]], errors="coerce")
        if pd.isna(date_val):
            report.warnings.append(f"Unparseable date {row[mapped['date']]!r} -- row skipped.")
            continue
        date_str = date_val.strftime("%Y-%m-%d")

        student_id = _resolve_student_id(row, mapped, unresolved_names)
        if student_id is None:
            continue
        student_records.mark_attendance(student_id, date_str, status)
        report.rows_imported += 1

    if unresolved_names:
        report.warnings.append(
            f"{len(unresolved_names)} student name(s) not found in the roster -- created as new students "
            f"using their name as the ID: {sorted(unresolved_names)}. Import the roster file first to avoid this."
        )
    return report


def _resolve_student_id(row, mapped: Dict[str, str], unresolved_names: set) -> Optional[str]:
    """Prefer an explicit ID column; fall back to looking up (or, failing
    that, creating) a student by name -- attendance/marks sheets often
    list students by name only, and dropping the row entirely would
    silently lose real data."""
    if "student_id" in mapped:
        sid = str(row[mapped["student_id"]]).strip()
        if sid and sid.lower() != "nan":
            return sid
    if "name" in mapped:
        name = str(row[mapped["name"]]).strip()
        if not name or name.lower() == "nan":
            return None
        existing = student_records.get_student_by_name(name)
        if existing:
            return existing.student_id
        student_records.upsert_student(name, name, "unspecified")
        unresolved_names.add(name)
        return name
    return None


# ------------------------------------------------------------------ marks --
def _import_marks(df: pd.DataFrame, filename: str) -> ImportReport:
    report = ImportReport(file=filename, detected_type="marks", rows_seen=len(df))
    mapped = _map_columns(df.columns, ["student_id", "name", "subject", "exam", "score", "max_score"])
    report.mapped_columns = mapped
    report.unmapped_columns = _unmapped(df.columns, mapped)

    if "score" not in mapped:
        report.errors.append("No score/marks column found -- cannot import without it.")
        return report
    if "student_id" not in mapped and "name" not in mapped:
        report.errors.append("No student ID or name column found -- cannot tell whose marks these are.")
        return report

    # Exam name often isn't its own column -- it's the whole file
    # (marks_midterm.xlsx). Fall back to a cleaned-up filename.
    default_exam = re.sub(r"[_\-]+", " ", os.path.splitext(filename)[0]).strip().title()
    if "exam" not in mapped:
        report.warnings.append(f"No exam-name column found -- using the filename instead: {default_exam!r}.")

    unresolved_names = set()
    for _, row in df.iterrows():
        try:
            score = float(row[mapped["score"]])
        except (ValueError, TypeError):
            report.warnings.append(f"Unparseable score {row[mapped['score']]!r} -- row skipped.")
            continue
        max_score = None
        if "max_score" in mapped:
            try:
                max_score = float(row[mapped["max_score"]])
            except (ValueError, TypeError):
                pass
        subject = str(row[mapped["subject"]]).strip() if "subject" in mapped else "unspecified"
        exam = str(row[mapped["exam"]]).strip() if "exam" in mapped else default_exam

        student_id = _resolve_student_id(row, mapped, unresolved_names)
        if student_id is None:
            continue
        student_records.upsert_mark(student_id, subject, exam, score, max_score)
        report.rows_imported += 1

    if unresolved_names:
        report.warnings.append(
            f"{len(unresolved_names)} student name(s) not found in the roster -- created as new students: {sorted(unresolved_names)}."
        )
    return report


# --------------------------------------------------------------- schedule --
def _import_schedule(df: pd.DataFrame, filename: str) -> ImportReport:
    """Writes to data/class_schedule.json, the exact format
    src/integrations/class_schedule.py already reads (real datetime-aware
    "today"/"tomorrow"/"next class" lookups) -- overwrites the seeded demo
    timetable with the real one, no other code needs to change."""
    import json

    report = ImportReport(file=filename, detected_type="schedule", rows_seen=len(df))
    mapped = _map_columns(df.columns, ["subject", "start_time", "end_time", "room"])
    # "day" isn't in _SYNONYMS (it'd collide with "date"'s synonym list --
    # a schedule's day column is a weekday name, not a calendar date) --
    # matched directly instead.
    day_col = next((c for c in df.columns if _normalize_header(c) in ("day", "weekday")), None)
    if day_col:
        mapped["day"] = day_col
    report.mapped_columns = mapped
    report.unmapped_columns = _unmapped(df.columns, mapped)

    required = ["day", "subject", "start_time", "end_time"]
    missing = [f for f in required if f not in mapped]
    if missing:
        report.errors.append(f"Missing required column(s) for a schedule: {missing}.")
        return report

    sessions = []
    for _, row in df.iterrows():
        day = str(row[mapped["day"]]).strip().title()
        subject = str(row[mapped["subject"]]).strip()
        start = _format_time(row[mapped["start_time"]])
        end = _format_time(row[mapped["end_time"]])
        if not (day and subject and start and end):
            report.warnings.append(f"Incomplete row skipped: day={day!r} subject={subject!r} start={start!r} end={end!r}")
            continue
        room = str(row[mapped["room"]]).strip() if "room" in mapped else ""
        sessions.append({"day": day, "subject": subject, "start_time": start, "end_time": end, "room": room})
        report.rows_imported += 1

    if sessions:
        with open(_SCHEDULE_PATH, "w") as f:
            json.dump(sessions, f, indent=2)
    return report


def _format_time(raw) -> Optional[str]:
    """Excel often stores times as datetime.time or pandas Timestamp
    objects, not plain strings -- normalize to "HH:MM" either way."""
    try:
        parsed = pd.to_datetime(str(raw))
        return parsed.strftime("%H:%M")
    except Exception:  # noqa: BLE001
        return None
