"""
Real, date-aware class-schedule lookups for the classroom domain skill.

Deliberately NOT RAG content: "what classes do I have today" needs an
actual clock to answer correctly (today's real weekday), and semantic
document retrieval matches meaning, not dates -- a static RAG document
saying "Monday: Math, Science..." can't tell you what today is. This is
the same "real, not just plausible-sounding" bar as
src/integrations/reminders_store.py, just read-only: a small seeded
weekly timetable (data/class_schedule.json) plus real datetime math.
"""
import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Optional

_SCHEDULE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "class_schedule.json"
)


@dataclass
class ClassSession:
    day: str
    subject: str
    start_time: str  # "HH:MM", 24-hour
    end_time: str
    room: str = ""


def _load_schedule() -> List[ClassSession]:
    with open(_SCHEDULE_PATH) as f:
        data = json.load(f)
    return [ClassSession(**entry) for entry in data]


def classes_for_day(day_name: str) -> List[ClassSession]:
    return sorted((c for c in _load_schedule() if c.day == day_name), key=lambda c: c.start_time)


def classes_today(now: Optional[datetime] = None) -> List[ClassSession]:
    now = now or datetime.now()
    return classes_for_day(now.strftime("%A"))


def classes_tomorrow(now: Optional[datetime] = None) -> List[ClassSession]:
    now = now or datetime.now()
    return classes_for_day((now + timedelta(days=1)).strftime("%A"))


def next_class(now: Optional[datetime] = None) -> Optional[ClassSession]:
    """The next upcoming class from now -- today (if its start time hasn't
    passed yet) or the next day that has one, checking up to a week ahead
    so it wraps correctly over a weekend with no classes."""
    now = now or datetime.now()
    for offset in range(8):
        check = now + timedelta(days=offset)
        for c in classes_for_day(check.strftime("%A")):
            if offset > 0 or datetime.strptime(c.start_time, "%H:%M").time() > now.time():
                return c
    return None
