"""
Unit tests for ScheduleReminderSkill and ListRemindersSkill in isolation
(not through the mock agent's keyword router, which is ambiguous for
list_reminders -- "what reminders" overlaps with faq_lookup's "what"
keyword; that's a pre-existing mock-router limitation, not something these
tests need to exercise).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.integrations import reminders_store
from src.skills.list_reminders import ListRemindersSkill
from src.skills.schedule_reminder import ScheduleReminderSkill


class _FakeUserMemory:
    def __init__(self, user_id):
        self.user_id = user_id


def _isolate_db(monkeypatch, tmp_path):
    monkeypatch.setattr(reminders_store, "_DB_PATH", str(tmp_path / "skill_test.db"))


def test_schedule_reminder_skill_persists_a_real_row(tmp_path, monkeypatch):
    _isolate_db(monkeypatch, tmp_path)
    ctx = {"user_memory": _FakeUserMemory("carol")}
    result = ScheduleReminderSkill().run({"subject": "call mom", "time": "5pm"}, ctx)
    assert result.success
    assert "call mom" in result.output
    assert "5pm" in result.output
    saved = reminders_store.list_reminders("carol")
    assert len(saved) == 1
    assert saved[0].subject == "call mom"


def test_schedule_reminder_skill_falls_back_to_placeholders_when_blank(tmp_path, monkeypatch):
    """Shouldn't normally happen (the agent paces for missing slots first),
    but the skill itself must still degrade honestly rather than crash if
    ever called with blanks directly."""
    _isolate_db(monkeypatch, tmp_path)
    ctx = {"user_memory": _FakeUserMemory("carol")}
    result = ScheduleReminderSkill().run({}, ctx)
    assert result.success
    assert "your reminder" in result.output
    assert "an unspecified time" in result.output


def test_schedule_reminder_skill_uses_demo_user_when_no_user_memory(tmp_path, monkeypatch):
    _isolate_db(monkeypatch, tmp_path)
    result = ScheduleReminderSkill().run({"subject": "x", "time": "y"}, {})
    assert result.success
    assert len(reminders_store.list_reminders("demo-user")) == 1


def test_list_reminders_skill_reports_none_when_empty(tmp_path, monkeypatch):
    _isolate_db(monkeypatch, tmp_path)
    ctx = {"user_memory": _FakeUserMemory("dave")}
    result = ListRemindersSkill().run({}, ctx)
    assert result.success
    assert "don't have any reminders" in result.output


def test_list_reminders_skill_reports_saved_reminders(tmp_path, monkeypatch):
    _isolate_db(monkeypatch, tmp_path)
    ctx = {"user_memory": _FakeUserMemory("dave")}
    ScheduleReminderSkill().run({"subject": "call mom", "time": "5pm"}, ctx)
    result = ListRemindersSkill().run({}, ctx)
    assert result.success
    assert "call mom" in result.output
    assert "5pm" in result.output
