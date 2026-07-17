"""
Real backend integration for CreateAssignmentSkill, mirroring
reminders_store.py exactly (same SQLite-stdlib, zero-new-dependency,
genuinely-persists-across-a-restart approach). Two independent skills get
two independent stores/tables rather than sharing one generic "tasks"
table -- keeps each domain's schema honest (a reminder has a subject/time;
an assignment has a chapter/due_date/class) instead of forcing them into a
lowest-common-denominator shape.
"""
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List

_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".assignments.db"
)


@dataclass
class Assignment:
    id: int
    user_id: str
    chapter: str
    due_date: str
    class_name: str
    created_at: str


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS assignments ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "user_id TEXT NOT NULL, "
        "chapter TEXT NOT NULL, "
        "due_date TEXT NOT NULL, "
        "class_name TEXT NOT NULL, "
        "created_at TEXT NOT NULL)"
    )
    return conn


def create_assignment(user_id: str, chapter: str, due_date: str, class_name: str) -> Assignment:
    conn = _connect()
    try:
        created_at = datetime.now(timezone.utc).isoformat()
        cur = conn.execute(
            "INSERT INTO assignments (user_id, chapter, due_date, class_name, created_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, chapter, due_date, class_name, created_at),
        )
        conn.commit()
        return Assignment(cur.lastrowid, user_id, chapter, due_date, class_name, created_at)
    finally:
        conn.close()


def list_assignments(user_id: str) -> List[Assignment]:
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT id, user_id, chapter, due_date, class_name, created_at FROM assignments WHERE user_id = ? ORDER BY id DESC",
            (user_id,),
        ).fetchall()
        return [Assignment(*row) for row in rows]
    finally:
        conn.close()
