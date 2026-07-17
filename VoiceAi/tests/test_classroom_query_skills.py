"""
Tests for the three classroom skills that read/write real student_records
data: MarkAttendanceSkill (paced dialogue, writes), AttendanceQuerySkill
and MarksQuerySkill (read-only). Also locks in the best-match-length
keyword-routing fix (src/llm.py's MockLLMBackend._agent_step) that was
needed once these skills' natural "what"/"how" phrasing started competing
with faq_lookup's bare single-word keywords.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.integrations import student_records
from src.skills.attendance_query import AttendanceQuerySkill
from src.skills.mark_attendance import MarkAttendanceSkill
from src.skills.marks_query import MarksQuerySkill


def _isolate(monkeypatch, tmp_path):
    monkeypatch.setattr(student_records, "_DB_PATH", str(tmp_path / "students_test.db"))


class _FakeUserMemory:
    def __init__(self, user_id):
        self.user_id = user_id


# --------------------------------------------------------- MarkAttendance --
def test_mark_attendance_skill_creates_record_for_known_student(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    student_records.upsert_student("S001", "Priya Sharma", "8B")

    result = MarkAttendanceSkill().run({"student_name": "Priya", "status": "absent", "date": "2026-07-01"}, {})
    assert result.success
    assert "Priya Sharma" in result.output
    assert "absent" in result.output

    absentees = student_records.absentees_on("2026-07-01")
    assert [s.name for s in absentees] == ["Priya Sharma"]


def test_mark_attendance_skill_creates_student_if_unknown(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    result = MarkAttendanceSkill().run({"student_name": "New Student", "status": "present"}, {})
    assert result.success
    assert student_records.get_student_by_name("New Student") is not None


def test_mark_attendance_skill_defaults_date_to_today(tmp_path, monkeypatch):
    from datetime import date

    _isolate(monkeypatch, tmp_path)
    student_records.upsert_student("S001", "Priya Sharma", "8B")
    MarkAttendanceSkill().run({"student_name": "Priya", "status": "present"}, {})
    today = date.today().isoformat()
    assert student_records.attendance_for_student("S001")[0].date == today


def test_mark_attendance_skill_requires_a_name():
    result = MarkAttendanceSkill().run({"status": "absent"}, {})
    assert not result.success


def test_mark_attendance_skill_requires_a_recognizable_status(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    student_records.upsert_student("S001", "Priya Sharma", "8B")
    result = MarkAttendanceSkill().run({"student_name": "Priya", "status": "maybe"}, {})
    assert not result.success


def test_mark_attendance_declares_two_required_slots_in_order():
    skill = MarkAttendanceSkill()
    assert list(skill.required_slots.keys()) == ["student_name", "status"]
    assert skill.missing_slots({}) == ["student_name", "status"]
    assert skill.missing_slots({"student_name": "Priya"}) == ["status"]


# ------------------------------------------------------------- Attendance --
def test_attendance_query_skill_lists_todays_absentees(tmp_path, monkeypatch):
    from datetime import date

    _isolate(monkeypatch, tmp_path)
    student_records.upsert_student("S001", "Priya Sharma", "8B")
    student_records.mark_attendance("S001", date.today().isoformat(), "absent")

    result = AttendanceQuerySkill().run({"query": "who's absent today"}, {})
    assert result.success
    assert "Priya Sharma" in result.output


def test_attendance_query_skill_handles_yesterday(tmp_path, monkeypatch):
    from datetime import date, timedelta

    _isolate(monkeypatch, tmp_path)
    student_records.upsert_student("S001", "Priya Sharma", "8B")
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    student_records.mark_attendance("S001", yesterday, "absent")

    result = AttendanceQuerySkill().run({"query": "who was absent yesterday"}, {})
    assert "Priya Sharma" in result.output


def test_attendance_query_skill_reports_none_absent(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    result = AttendanceQuerySkill().run({"query": "show absent students"}, {})
    assert result.success
    assert "No students marked absent" in result.output


# ------------------------------------------------------------------ Marks --
def test_marks_query_skill_reports_all_marks(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    student_records.upsert_student("S001", "Priya Sharma", "8B")
    student_records.upsert_mark("S001", "Math", "Midterm", 78, 100)

    result = MarksQuerySkill().run({"student_name": "Priya"}, {})
    assert result.success
    assert "Math" in result.output
    assert "78" in result.output


def test_marks_query_skill_filters_by_exam(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    student_records.upsert_student("S001", "Priya Sharma", "8B")
    student_records.upsert_mark("S001", "Math", "Midterm", 78, 100)
    student_records.upsert_mark("S001", "Math", "Final", 88, 100)

    result = MarksQuerySkill().run({"student_name": "Priya", "exam": "Midterm"}, {})
    assert "78" in result.output
    assert "88" not in result.output


def test_marks_query_skill_unknown_student(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    result = MarksQuerySkill().run({"student_name": "Nobody"}, {})
    assert not result.success


def test_marks_query_declares_one_required_slot():
    assert list(MarksQuerySkill().required_slots.keys()) == ["student_name"]


# ------------------------------------------------- keyword-routing regression --
def test_marks_and_attendance_keywords_beat_faq_lookups_generic_words():
    """Real bug found while adding these skills: faq_lookup's bare "what"/
    "how" keywords substring-match almost any question, and used to always
    win under first-match-wins routing regardless of a more specific
    skill's own keyword. Locks in the fix: longest-matching-keyword wins."""
    from src.llm import MockLLMBackend
    import json

    tools = [
        {"name": "faq_lookup", "keywords": ["what", "when", "where", "how", "faq", "?"]},
        {"name": "marks_query", "keywords": ["what did", "score in", "marks in", "grade in", "how did"]},
        {"name": "attendance_query", "keywords": ["absent students", "who is absent", "who's absent"]},
    ]
    payload = {"user_request": "what did Priya score in the math midterm", "available_tools": tools, "observations_so_far": []}
    decision = json.loads(MockLLMBackend()._agent_step(json.dumps(payload)))
    assert decision["skill"] == "marks_query"

    payload2 = {"user_request": "who's absent today", "available_tools": tools, "observations_so_far": []}
    decision2 = json.loads(MockLLMBackend()._agent_step(json.dumps(payload2)))
    assert decision2["skill"] == "attendance_query"
