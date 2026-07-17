"""
Tests for the real SQLite-backed classroom roster/attendance/marks store
(src/integrations/student_records.py) -- mirrors tests/test_reminders_store.py's
approach: a fresh tmp_path database per test, genuine persistence verified.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.integrations import student_records


def _isolate_db(monkeypatch, tmp_path):
    monkeypatch.setattr(student_records, "_DB_PATH", str(tmp_path / "students_test.db"))


# ---------------------------------------------------------------- students --
def test_upsert_and_list_students(tmp_path, monkeypatch):
    _isolate_db(monkeypatch, tmp_path)
    student_records.upsert_student("S001", "Priya Sharma", "8B")
    student_records.upsert_student("S002", "Rohan Verma", "8B")
    students = student_records.list_students()
    assert [s.name for s in students] == ["Priya Sharma", "Rohan Verma"]  # alphabetical


def test_upsert_student_updates_existing_row_not_duplicates(tmp_path, monkeypatch):
    _isolate_db(monkeypatch, tmp_path)
    student_records.upsert_student("S001", "Priya Sharma", "8B")
    student_records.upsert_student("S001", "Priya Sharma", "9A")  # corrected class
    students = student_records.list_students()
    assert len(students) == 1
    assert students[0].class_name == "9A"


def test_get_student_by_name_is_case_insensitive_partial_match(tmp_path, monkeypatch):
    _isolate_db(monkeypatch, tmp_path)
    student_records.upsert_student("S001", "Priya Sharma", "8B")
    assert student_records.get_student_by_name("priya").student_id == "S001"
    assert student_records.get_student_by_name("SHARMA").student_id == "S001"
    assert student_records.get_student_by_name("nobody") is None


def test_list_students_filtered_by_class(tmp_path, monkeypatch):
    _isolate_db(monkeypatch, tmp_path)
    student_records.upsert_student("S001", "Priya Sharma", "8B")
    student_records.upsert_student("S002", "Ayesha Khan", "9A")
    assert [s.name for s in student_records.list_students(class_name="8B")] == ["Priya Sharma"]


# -------------------------------------------------------------- attendance --
def test_mark_attendance_and_query_absentees(tmp_path, monkeypatch):
    _isolate_db(monkeypatch, tmp_path)
    student_records.upsert_student("S001", "Priya Sharma", "8B")
    student_records.upsert_student("S002", "Rohan Verma", "8B")
    student_records.mark_attendance("S001", "2026-07-01", "present")
    student_records.mark_attendance("S002", "2026-07-01", "absent")

    absentees = student_records.absentees_on("2026-07-01")
    assert [s.name for s in absentees] == ["Rohan Verma"]


def test_mark_attendance_upserts_a_correction_not_a_duplicate(tmp_path, monkeypatch):
    _isolate_db(monkeypatch, tmp_path)
    student_records.upsert_student("S001", "Priya Sharma", "8B")
    student_records.mark_attendance("S001", "2026-07-01", "absent")
    student_records.mark_attendance("S001", "2026-07-01", "present")  # correction

    records = student_records.attendance_for_student("S001")
    assert len(records) == 1
    assert records[0].status == "present"


def test_absentees_on_empty_date_returns_empty_list(tmp_path, monkeypatch):
    _isolate_db(monkeypatch, tmp_path)
    assert student_records.absentees_on("2026-01-01") == []


# ------------------------------------------------------------------ marks --
def test_upsert_and_query_marks(tmp_path, monkeypatch):
    _isolate_db(monkeypatch, tmp_path)
    student_records.upsert_student("S001", "Priya Sharma", "8B")
    student_records.upsert_mark("S001", "Math", "Midterm", 78, 100)
    student_records.upsert_mark("S001", "Science", "Midterm", 85, 100)

    marks = student_records.marks_for_student("S001")
    assert len(marks) == 2
    assert {m.subject for m in marks} == {"Math", "Science"}


def test_marks_filtered_by_exam(tmp_path, monkeypatch):
    _isolate_db(monkeypatch, tmp_path)
    student_records.upsert_student("S001", "Priya Sharma", "8B")
    student_records.upsert_mark("S001", "Math", "Midterm", 78, 100)
    student_records.upsert_mark("S001", "Math", "Final", 88, 100)

    midterm_only = student_records.marks_for_student("S001", exam="Midterm")
    assert len(midterm_only) == 1
    assert midterm_only[0].score == 78


def test_upsert_mark_updates_existing_score_not_duplicates(tmp_path, monkeypatch):
    _isolate_db(monkeypatch, tmp_path)
    student_records.upsert_student("S001", "Priya Sharma", "8B")
    student_records.upsert_mark("S001", "Math", "Midterm", 60, 100)
    student_records.upsert_mark("S001", "Math", "Midterm", 78, 100)  # corrected score

    marks = student_records.marks_for_student("S001")
    assert len(marks) == 1
    assert marks[0].score == 78
