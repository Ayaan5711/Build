"""
Tests for the fuzzy-matching Excel importer (src/integrations/excel_import.py).
Every test writes a real .xlsx file (via pandas, to tmp_path -- no
committed binary fixtures) with deliberately nonstandard column headers,
mirroring what a real school's spreadsheet is likely to look like, then
verifies both the ImportReport and the resulting rows in student_records.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd

from src.integrations import excel_import, student_records


def _isolate(monkeypatch, tmp_path):
    monkeypatch.setattr(student_records, "_DB_PATH", str(tmp_path / "students_test.db"))
    monkeypatch.setattr(excel_import, "_SCHEDULE_PATH", str(tmp_path / "schedule_test.json"))


# --------------------------------------------------------- header matching --
def test_normalize_header_handles_underscores_hyphens_case():
    assert excel_import._normalize_header("Student_ID") == "student id"
    assert excel_import._normalize_header("student-id") == "student id"
    assert excel_import._normalize_header("  Roll No  ") == "roll no"


def test_detect_file_type_from_filename_takes_priority():
    assert excel_import._detect_file_type("attendance_july.xlsx", ["Roll No", "Score"]) == "attendance"
    assert excel_import._detect_file_type("marks_midterm.xlsx", []) == "marks"
    assert excel_import._detect_file_type("student_master.xlsx", []) == "students"
    assert excel_import._detect_file_type("faculty_class_schedule.xlsx", []) == "schedule"


def test_detect_file_type_falls_back_to_column_signature():
    # Ambiguous filename, but the columns give it away.
    assert excel_import._detect_file_type("july_data.xlsx", ["Roll No", "Date", "Status"]) == "attendance"
    assert excel_import._detect_file_type("results.xlsx", ["Roll No", "Marks Obtained"]) == "marks"
    assert excel_import._detect_file_type("weekly.xlsx", ["Subject", "Start Time", "End Time"]) == "schedule"
    assert excel_import._detect_file_type("roster.xlsx", ["Name", "Class"]) == "students"
    assert excel_import._detect_file_type("mystery.xlsx", ["Foo", "Bar"]) == "unknown"


# --------------------------------------------------------------- students --
def test_import_students_with_nonstandard_headers(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    path = tmp_path / "student_master.xlsx"
    pd.DataFrame(
        {"Roll No": ["S001", "S002"], "Student Name": ["Priya Sharma", "Rohan Verma"], "Class/Section": ["8B", "8B"]}
    ).to_excel(path, index=False)

    report = excel_import.import_excel_file(str(path))
    assert report.detected_type == "students"
    assert report.rows_imported == 2
    assert report.mapped_columns == {"student_id": "Roll No", "name": "Student Name", "class_name": "Class/Section"}
    assert not report.errors

    students = student_records.list_students()
    assert {s.name for s in students} == {"Priya Sharma", "Rohan Verma"}


def test_import_students_without_id_column_uses_name_as_id(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    path = tmp_path / "student_data.xlsx"
    pd.DataFrame({"Name": ["Priya Sharma"], "Class": ["8B"]}).to_excel(path, index=False)

    report = excel_import.import_excel_file(str(path))
    assert report.rows_imported == 1
    assert any("no student id column" in w.lower() for w in report.warnings)
    assert student_records.get_student_by_name("Priya").student_id == "Priya Sharma"


def test_import_students_missing_name_column_is_a_hard_error(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    path = tmp_path / "student_master.xlsx"
    pd.DataFrame({"Roll No": ["S001"], "Class": ["8B"]}).to_excel(path, index=False)

    report = excel_import.import_excel_file(str(path))
    assert report.rows_imported == 0
    assert report.errors


# -------------------------------------------------------------- attendance --
def test_import_attendance_with_pa_status_values(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    student_records.upsert_student("S001", "Priya Sharma", "8B")
    student_records.upsert_student("S002", "Rohan Verma", "8B")

    path = tmp_path / "attendance_july.xlsx"
    pd.DataFrame(
        {
            "Roll No": ["S001", "S002", "S001"],
            "Attendance Date": ["2026-07-01", "2026-07-01", "2026-07-02"],
            "Present/Absent": ["P", "A", "Absent"],
        }
    ).to_excel(path, index=False)

    report = excel_import.import_excel_file(str(path))
    assert report.detected_type == "attendance"
    assert report.rows_imported == 3

    assert [s.name for s in student_records.absentees_on("2026-07-01")] == ["Rohan Verma"]
    assert [s.name for s in student_records.absentees_on("2026-07-02")] == ["Priya Sharma"]


def test_import_attendance_by_name_creates_student_if_unknown(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    path = tmp_path / "attendance_july.xlsx"
    pd.DataFrame({"Student Name": ["Ayesha Khan"], "Date": ["2026-07-01"], "Status": ["Absent"]}).to_excel(path, index=False)

    report = excel_import.import_excel_file(str(path))
    assert report.rows_imported == 1
    assert any("not found in the roster" in w for w in report.warnings)
    assert student_records.get_student_by_name("Ayesha") is not None


def test_import_attendance_skips_unrecognized_status_with_a_warning(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    student_records.upsert_student("S001", "Priya Sharma", "8B")
    path = tmp_path / "attendance_july.xlsx"
    pd.DataFrame({"Roll No": ["S001"], "Date": ["2026-07-01"], "Status": ["maybe"]}).to_excel(path, index=False)

    report = excel_import.import_excel_file(str(path))
    assert report.rows_imported == 0
    assert any("unrecognized status" in w.lower() for w in report.warnings)


def test_import_attendance_missing_required_columns_is_a_hard_error(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    path = tmp_path / "attendance_july.xlsx"
    pd.DataFrame({"Roll No": ["S001"]}).to_excel(path, index=False)

    report = excel_import.import_excel_file(str(path))
    assert report.rows_imported == 0
    assert report.errors


# ------------------------------------------------------------------ marks --
def test_import_marks_uses_filename_as_exam_when_no_exam_column(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    student_records.upsert_student("S001", "Priya Sharma", "8B")
    path = tmp_path / "marks_midterm.xlsx"
    pd.DataFrame({"Roll No": ["S001"], "Subject": ["Math"], "Marks Obtained": [78], "Total Marks": [100]}).to_excel(
        path, index=False
    )

    report = excel_import.import_excel_file(str(path))
    assert report.rows_imported == 1
    assert any("using the filename instead" in w for w in report.warnings)

    marks = student_records.marks_for_student("S001")
    assert marks[0].exam == "Marks Midterm"
    assert marks[0].score == 78
    assert marks[0].max_score == 100


def test_import_marks_skips_unparseable_score(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    student_records.upsert_student("S001", "Priya Sharma", "8B")
    path = tmp_path / "marks_midterm.xlsx"
    pd.DataFrame({"Roll No": ["S001"], "Subject": ["Math"], "Marks Obtained": ["absent"]}).to_excel(path, index=False)

    report = excel_import.import_excel_file(str(path))
    assert report.rows_imported == 0
    assert any("unparseable score" in w.lower() for w in report.warnings)


def test_import_marks_wide_format_imports_each_subject_column(tmp_path, monkeypatch):
    """Real bug found on the user's own machine: a real marks sheet had no
    single 'Subject' column, only one score column per subject
    (Mathematics/Physics/...) plus a Total/Average/Grade summary -- the
    per-subject columns used to be silently discarded as "unmapped
    columns (ignored)", so a query like "what did Priya score in the math
    midterm" had no data to answer from. Each subject column must become
    its own mark row; Average/Grade must NOT be mistaken for subjects."""
    _isolate(monkeypatch, tmp_path)
    student_records.upsert_student("S001", "Priya Sharma", "8B")
    path = tmp_path / "marks_midterm.xlsx"
    pd.DataFrame(
        {
            "Roll No": ["S001"],
            "Name": ["Priya Sharma"],
            "Mathematics": [78],
            "Physics": [85],
            "Chemistry": [90],
            "Total": [253],
            "Average": [84.3],
            "Grade": ["A"],
        }
    ).to_excel(path, index=False)

    report = excel_import.import_excel_file(str(path))
    assert report.detected_type == "marks"
    assert not report.errors

    marks = {m.subject: m.score for m in student_records.marks_for_student("S001")}
    assert marks["Mathematics"] == 78
    assert marks["Physics"] == 85
    assert marks["Chemistry"] == 90
    assert marks["Total"] == 253
    assert "Average" not in marks
    assert "Grade" not in marks
    for m in student_records.marks_for_student("S001"):
        assert m.exam == "Marks Midterm"


def test_import_marks_wide_format_skips_blank_subject_cells_without_dropping_the_row(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    student_records.upsert_student("S001", "Priya Sharma", "8B")
    path = tmp_path / "marks_midterm.xlsx"
    pd.DataFrame({"Roll No": ["S001"], "Mathematics": [78], "Physics": [None]}).to_excel(path, index=False)

    report = excel_import.import_excel_file(str(path))
    marks = {m.subject: m.score for m in student_records.marks_for_student("S001")}
    assert marks["Mathematics"] == 78
    assert "Physics" not in marks


def test_import_schedule_maps_course_name_column_to_subject(tmp_path, monkeypatch):
    """Real bug found on the user's own machine: a real faculty schedule
    sheet used 'Course Name' instead of 'Subject' -- the synonym list only
    matched a bare 'Course' header exactly, so every row was rejected with
    "Missing required column(s) for a schedule: ['subject']" despite
    day/start/end/room all mapping fine."""
    _isolate(monkeypatch, tmp_path)
    path = tmp_path / "faculty_class_schedule.xlsx"
    pd.DataFrame(
        {
            "Day": ["Monday"],
            "Course Name": ["Physics"],
            "Course Code": ["PHY101"],
            "Start Time": ["09:00"],
            "End Time": ["10:00"],
            "Room": ["Lab 1"],
        }
    ).to_excel(path, index=False)

    report = excel_import.import_excel_file(str(path))
    assert not report.errors
    assert report.rows_imported == 1
    assert report.mapped_columns["subject"] == "Course Name"

    import json

    with open(excel_import._SCHEDULE_PATH) as f:
        written = json.load(f)
    assert written[0]["subject"] == "Physics"


# --------------------------------------------------------------- schedule --
def test_import_schedule_writes_to_isolated_schedule_path(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    path = tmp_path / "faculty_class_schedule.xlsx"
    pd.DataFrame(
        {
            "Day": ["Monday", "Tuesday"],
            "Subject": ["Physics", "Biology"],
            "Start Time": ["09:00", "10:00"],
            "End Time": ["10:00", "11:00"],
            "Room": ["Lab 1", "Lab 3"],
        }
    ).to_excel(path, index=False)

    report = excel_import.import_excel_file(str(path))
    assert report.detected_type == "schedule"
    assert report.rows_imported == 2

    import json

    with open(excel_import._SCHEDULE_PATH) as f:
        written = json.load(f)
    assert written == [
        {"day": "Monday", "subject": "Physics", "start_time": "09:00", "end_time": "10:00", "room": "Lab 1"},
        {"day": "Tuesday", "subject": "Biology", "start_time": "10:00", "end_time": "11:00", "room": "Lab 3"},
    ]


def test_import_schedule_reusable_by_class_schedule_reader(tmp_path, monkeypatch):
    """The whole point of writing this exact JSON shape -- confirm the
    already-built, real date-aware class_schedule.py can read it back with
    zero changes."""
    _isolate(monkeypatch, tmp_path)
    path = tmp_path / "faculty_class_schedule.xlsx"
    pd.DataFrame(
        {"Day": ["Monday"], "Subject": ["Physics"], "Start Time": ["09:00"], "End Time": ["10:00"], "Room": ["Lab 1"]}
    ).to_excel(path, index=False)
    excel_import.import_excel_file(str(path))

    from src.integrations import class_schedule

    monkeypatch.setattr(class_schedule, "_SCHEDULE_PATH", excel_import._SCHEDULE_PATH)
    from datetime import datetime

    monday = datetime(2024, 1, 1, 8, 0)  # a real Monday
    sessions = class_schedule.classes_today(now=monday)
    assert [s.subject for s in sessions] == ["Physics"]


# --------------------------------------------------------------- unknown --
def test_unrecognized_file_reports_unknown_and_imports_nothing(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    path = tmp_path / "random_notes.xlsx"
    pd.DataFrame({"Foo": [1], "Bar": [2]}).to_excel(path, index=False)

    report = excel_import.import_excel_file(str(path))
    assert report.detected_type == "unknown"
    assert report.rows_imported == 0


def test_unreadable_file_reports_the_real_error_not_just_unknown(tmp_path, monkeypatch):
    """Real bug found on the user's own machine: every one of 5 real
    spreadsheets (including ones with unambiguous filenames like
    'Attendance_July.xlsx', which the filename check alone should have
    caught) reported "detected as: unknown / Could not confidently
    identify this file" with no further detail -- because
    ImportReport.summary() returned early for detected_type == "unknown"
    without ever printing report.errors, silently hiding the real reason
    (pd.read_excel() failing on the actual file) behind a message that
    implied a column-matching failure instead."""
    _isolate(monkeypatch, tmp_path)
    path = tmp_path / "attendance_july.xlsx"
    path.write_bytes(b"not a real xlsx file, just garbage bytes")

    report = excel_import.import_excel_file(str(path))
    assert report.detected_type == "unknown"
    assert report.errors
    assert "Could not read file" in report.summary()
    assert report.errors[0] in report.summary()
