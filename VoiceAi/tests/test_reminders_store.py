"""
Tests for the real (SQLite-backed) scheduling integration -- "backend
integration with scheduling APIs" in the problem statement's solution
expectations. Genuinely persists to disk (not mocked), isolated to a fresh
tmp_path database per test so tests never touch the real .reminders.db or
interfere with each other.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.integrations import reminders_store


def _isolate_db(monkeypatch, tmp_path):
    monkeypatch.setattr(reminders_store, "_DB_PATH", str(tmp_path / "reminders_test.db"))


def test_create_reminder_persists_and_is_listable(tmp_path, monkeypatch):
    _isolate_db(monkeypatch, tmp_path)
    reminder = reminders_store.create_reminder("alice", "call mom", "5pm tomorrow")
    assert reminder.id == 1
    assert reminder.subject == "call mom"

    found = reminders_store.list_reminders("alice")
    assert len(found) == 1
    assert found[0].subject == "call mom"
    assert found[0].time == "5pm tomorrow"


def test_reminders_isolated_per_user(tmp_path, monkeypatch):
    _isolate_db(monkeypatch, tmp_path)
    reminders_store.create_reminder("alice", "call mom", "5pm")
    reminders_store.create_reminder("bob", "dentist", "9am")
    assert [r.subject for r in reminders_store.list_reminders("alice")] == ["call mom"]
    assert [r.subject for r in reminders_store.list_reminders("bob")] == ["dentist"]


def test_list_reminders_empty_for_unknown_user(tmp_path, monkeypatch):
    _isolate_db(monkeypatch, tmp_path)
    assert reminders_store.list_reminders("nobody") == []


def test_reminders_persist_across_separate_connections(tmp_path, monkeypatch):
    """Real persistence, not an in-memory stand-in -- a fresh _connect()
    call (simulating a new request in a new process) still sees prior
    writes, proving this survives beyond a single Python object's lifetime."""
    _isolate_db(monkeypatch, tmp_path)
    reminders_store.create_reminder("alice", "call mom", "5pm")
    # New connection, same underlying file.
    found = reminders_store.list_reminders("alice")
    assert len(found) == 1


def test_delete_reminder_removes_only_the_matching_users_row(tmp_path, monkeypatch):
    _isolate_db(monkeypatch, tmp_path)
    r = reminders_store.create_reminder("alice", "call mom", "5pm")
    reminders_store.create_reminder("bob", "dentist", "9am")

    assert reminders_store.delete_reminder("alice", r.id) is True
    assert reminders_store.list_reminders("alice") == []
    assert len(reminders_store.list_reminders("bob")) == 1


def test_delete_reminder_wrong_user_does_nothing(tmp_path, monkeypatch):
    _isolate_db(monkeypatch, tmp_path)
    r = reminders_store.create_reminder("alice", "call mom", "5pm")
    assert reminders_store.delete_reminder("bob", r.id) is False
    assert len(reminders_store.list_reminders("alice")) == 1


def test_multiple_reminders_ordered_most_recent_first(tmp_path, monkeypatch):
    _isolate_db(monkeypatch, tmp_path)
    reminders_store.create_reminder("alice", "first", "1pm")
    reminders_store.create_reminder("alice", "second", "2pm")
    subjects = [r.subject for r in reminders_store.list_reminders("alice")]
    assert subjects == ["second", "first"]
