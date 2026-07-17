"""
Real backend integration for ScheduleReminderSkill ("backend integration
with scheduling APIs" in the problem statement's solution expectations).

Uses SQLite (stdlib, zero new dependency) rather than a third-party
calendar API on purpose: it's genuinely persistent (survives a server
restart, unlike the in-process dialogue_state), needs no OAuth/API key/
internet on demo day, and gives a real, inspectable audit trail of what
got scheduled -- exactly what's needed to demonstrate actual task
completion, not just a plausible-sounding sentence. Swapping in a real
calendar API later (Google Calendar, Outlook, etc.) means changing the
three functions below, not the skill or the dialogue layer that calls them.
"""
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List

_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".reminders.db"
)


@dataclass
class Reminder:
    id: int
    user_id: str
    subject: str
    time: str
    created_at: str


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS reminders ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "user_id TEXT NOT NULL, "
        "subject TEXT NOT NULL, "
        "time TEXT NOT NULL, "
        "created_at TEXT NOT NULL)"
    )
    return conn


def create_reminder(user_id: str, subject: str, time: str) -> Reminder:
    conn = _connect()
    try:
        created_at = datetime.now(timezone.utc).isoformat()
        cur = conn.execute(
            "INSERT INTO reminders (user_id, subject, time, created_at) VALUES (?, ?, ?, ?)",
            (user_id, subject, time, created_at),
        )
        conn.commit()
        return Reminder(id=cur.lastrowid, user_id=user_id, subject=subject, time=time, created_at=created_at)
    finally:
        conn.close()


def list_reminders(user_id: str) -> List[Reminder]:
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT id, user_id, subject, time, created_at FROM reminders WHERE user_id = ? ORDER BY id DESC",
            (user_id,),
        ).fetchall()
        return [Reminder(*row) for row in rows]
    finally:
        conn.close()


def delete_reminder(user_id: str, reminder_id: int) -> bool:
    conn = _connect()
    try:
        cur = conn.execute("DELETE FROM reminders WHERE id = ? AND user_id = ?", (reminder_id, user_id))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()
