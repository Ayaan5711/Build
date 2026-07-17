"""
Real SQLite-backed storage for the classroom roster, attendance, and marks
data (real student records provided as Excel files by the team's seniors).
Same pattern as reminders_store.py / assignments_store.py -- stdlib
sqlite3, genuinely persists -- consolidated into one file since these three
tables are relationally linked (attendance and marks both reference
student_id) rather than independent domains.

Two write paths feed the same tables: scripts/import_classroom_data.py
(bulk, from Excel) and src/skills/mark_attendance.py (one row at a time,
via voice, mid-conversation). Both go through the functions below, so
there's exactly one source of truth regardless of how a row got there.

Contains real student PII (names, attendance, marks) -- the database file
(.student_records.db) is gitignored, same as .reminders.db/.assignments.db.
"""
import os
import sqlite3
from dataclasses import dataclass
from typing import List, Optional

_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".student_records.db"
)


@dataclass
class Student:
    student_id: str
    name: str
    class_name: str


@dataclass
class AttendanceRecord:
    id: int
    student_id: str
    date: str  # ISO "YYYY-MM-DD"
    status: str  # "present" | "absent"


@dataclass
class MarkRecord:
    id: int
    student_id: str
    subject: str
    exam: str
    score: float
    max_score: Optional[float]


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS students ("
        "student_id TEXT PRIMARY KEY, "
        "name TEXT NOT NULL, "
        "class_name TEXT NOT NULL)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS attendance ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "student_id TEXT NOT NULL, "
        "date TEXT NOT NULL, "
        "status TEXT NOT NULL, "
        "UNIQUE(student_id, date))"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS marks ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "student_id TEXT NOT NULL, "
        "subject TEXT NOT NULL, "
        "exam TEXT NOT NULL, "
        "score REAL NOT NULL, "
        "max_score REAL, "
        "UNIQUE(student_id, subject, exam))"
    )
    return conn


# ---------------------------------------------------------------- students --
def upsert_student(student_id: str, name: str, class_name: str) -> Student:
    """Insert or update -- re-importing the same roster (e.g. a corrected
    Excel file) updates existing students instead of duplicating them."""
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO students (student_id, name, class_name) VALUES (?, ?, ?) "
            "ON CONFLICT(student_id) DO UPDATE SET name=excluded.name, class_name=excluded.class_name",
            (student_id, name, class_name),
        )
        conn.commit()
        return Student(student_id, name, class_name)
    finally:
        conn.close()


def get_student_by_name(name: str, class_name: Optional[str] = None) -> Optional[Student]:
    """Case-insensitive, partial-match lookup -- voice input won't spell a
    name exactly as it's stored in the roster (e.g. "Priya" should find
    "Priya Sharma"). Returns the first match if more than one; ambiguous
    names are a known limitation, see README."""
    conn = _connect()
    try:
        query = "SELECT student_id, name, class_name FROM students WHERE lower(name) LIKE ?"
        params = [f"%{name.strip().lower()}%"]
        if class_name:
            query += " AND lower(class_name) = ?"
            params.append(class_name.strip().lower())
        row = conn.execute(query, params).fetchone()
        return Student(*row) if row else None
    finally:
        conn.close()


def list_students(class_name: Optional[str] = None) -> List[Student]:
    conn = _connect()
    try:
        if class_name:
            rows = conn.execute(
                "SELECT student_id, name, class_name FROM students WHERE lower(class_name) = ? ORDER BY name",
                (class_name.strip().lower(),),
            ).fetchall()
        else:
            rows = conn.execute("SELECT student_id, name, class_name FROM students ORDER BY name").fetchall()
        return [Student(*row) for row in rows]
    finally:
        conn.close()


# -------------------------------------------------------------- attendance --
def mark_attendance(student_id: str, date: str, status: str) -> AttendanceRecord:
    """Upsert -- re-marking the same student on the same date updates the
    existing row instead of creating a duplicate, so a spoken correction
    ("actually mark them present") just works."""
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO attendance (student_id, date, status) VALUES (?, ?, ?) "
            "ON CONFLICT(student_id, date) DO UPDATE SET status=excluded.status",
            (student_id, date, status),
        )
        conn.commit()
        row = conn.execute(
            "SELECT id, student_id, date, status FROM attendance WHERE student_id = ? AND date = ?",
            (student_id, date),
        ).fetchone()
        return AttendanceRecord(*row)
    finally:
        conn.close()


def absentees_on(date: str) -> List[Student]:
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT s.student_id, s.name, s.class_name FROM attendance a "
            "JOIN students s ON s.student_id = a.student_id "
            "WHERE a.date = ? AND a.status = 'absent' ORDER BY s.name",
            (date,),
        ).fetchall()
        return [Student(*row) for row in rows]
    finally:
        conn.close()


def attendance_for_student(student_id: str) -> List[AttendanceRecord]:
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT id, student_id, date, status FROM attendance WHERE student_id = ? ORDER BY date DESC",
            (student_id,),
        ).fetchall()
        return [AttendanceRecord(*row) for row in rows]
    finally:
        conn.close()


# ------------------------------------------------------------------ marks --
def upsert_mark(student_id: str, subject: str, exam: str, score: float, max_score: Optional[float] = None) -> MarkRecord:
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO marks (student_id, subject, exam, score, max_score) VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(student_id, subject, exam) DO UPDATE SET score=excluded.score, max_score=excluded.max_score",
            (student_id, subject, exam, score, max_score),
        )
        conn.commit()
        row = conn.execute(
            "SELECT id, student_id, subject, exam, score, max_score FROM marks "
            "WHERE student_id = ? AND subject = ? AND exam = ?",
            (student_id, subject, exam),
        ).fetchone()
        return MarkRecord(*row)
    finally:
        conn.close()


def marks_for_student(student_id: str, exam: Optional[str] = None) -> List[MarkRecord]:
    conn = _connect()
    try:
        if exam:
            rows = conn.execute(
                "SELECT id, student_id, subject, exam, score, max_score FROM marks "
                "WHERE student_id = ? AND lower(exam) = ? ORDER BY subject",
                (student_id, exam.strip().lower()),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, student_id, subject, exam, score, max_score FROM marks WHERE student_id = ? ORDER BY exam, subject",
                (student_id,),
            ).fetchall()
        return [MarkRecord(*row) for row in rows]
    finally:
        conn.close()
