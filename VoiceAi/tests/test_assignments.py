"""
Tests for the assignment domain: real SQLite persistence
(src/integrations/assignments_store.py) and the two skills wrapping it,
mirroring tests/test_reminders_store.py and tests/test_reminder_skills.py.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.integrations import assignments_store
from src.skills.assignment import CreateAssignmentSkill
from src.skills.list_assignments import ListAssignmentsSkill


class _FakeUserMemory:
    def __init__(self, user_id):
        self.user_id = user_id


def _isolate_db(monkeypatch, tmp_path):
    monkeypatch.setattr(assignments_store, "_DB_PATH", str(tmp_path / "assignments_test.db"))


# --------------------------------------------------------- store layer --
def test_create_assignment_persists_and_is_listable(tmp_path, monkeypatch):
    _isolate_db(monkeypatch, tmp_path)
    a = assignments_store.create_assignment("teacher1", "Chapter 5", "next Monday", "Class 8B")
    assert a.id == 1
    found = assignments_store.list_assignments("teacher1")
    assert len(found) == 1
    assert found[0].chapter == "Chapter 5"
    assert found[0].class_name == "Class 8B"


def test_assignments_isolated_per_user(tmp_path, monkeypatch):
    _isolate_db(monkeypatch, tmp_path)
    assignments_store.create_assignment("teacher1", "Chapter 5", "Monday", "8B")
    assignments_store.create_assignment("teacher2", "Chapter 2", "Tuesday", "9A")
    assert [a.chapter for a in assignments_store.list_assignments("teacher1")] == ["Chapter 5"]
    assert [a.chapter for a in assignments_store.list_assignments("teacher2")] == ["Chapter 2"]


def test_list_assignments_empty_for_unknown_user(tmp_path, monkeypatch):
    _isolate_db(monkeypatch, tmp_path)
    assert assignments_store.list_assignments("nobody") == []


# --------------------------------------------------------- skill layer --
def test_create_assignment_skill_persists_a_real_row(tmp_path, monkeypatch):
    _isolate_db(monkeypatch, tmp_path)
    ctx = {"user_memory": _FakeUserMemory("teacher1")}
    result = CreateAssignmentSkill().run({"chapter": "Chapter 5", "class_name": "8B", "due_date": "Monday"}, ctx)
    assert result.success
    assert "Chapter 5" in result.output
    assert len(assignments_store.list_assignments("teacher1")) == 1


def test_create_assignment_skill_falls_back_to_placeholders_when_blank(tmp_path, monkeypatch):
    _isolate_db(monkeypatch, tmp_path)
    ctx = {"user_memory": _FakeUserMemory("teacher1")}
    result = CreateAssignmentSkill().run({}, ctx)
    assert result.success
    assert "the assignment" in result.output
    assert "your class" in result.output


def test_list_assignments_skill_reports_none_when_empty(tmp_path, monkeypatch):
    _isolate_db(monkeypatch, tmp_path)
    ctx = {"user_memory": _FakeUserMemory("teacher1")}
    result = ListAssignmentsSkill().run({}, ctx)
    assert result.success
    assert "haven't created any" in result.output


def test_list_assignments_skill_reports_saved_assignments(tmp_path, monkeypatch):
    _isolate_db(monkeypatch, tmp_path)
    ctx = {"user_memory": _FakeUserMemory("teacher1")}
    CreateAssignmentSkill().run({"chapter": "Chapter 5", "class_name": "8B", "due_date": "Monday"}, ctx)
    result = ListAssignmentsSkill().run({}, ctx)
    assert "Chapter 5" in result.output
    assert "8B" in result.output


# ------------------------------------------------- required_slots contract --
def test_create_assignment_declares_three_required_slots_in_order():
    skill = CreateAssignmentSkill()
    assert list(skill.required_slots.keys()) == ["chapter", "class_name", "due_date"]
    assert skill.missing_slots({}) == ["chapter", "class_name", "due_date"]
    assert skill.missing_slots({"chapter": "Chapter 5"}) == ["class_name", "due_date"]
    assert skill.missing_slots({"chapter": "Chapter 5", "class_name": "8B", "due_date": "Monday"}) == []
