"""
Tests for the real, date-aware class-schedule lookups (src/integrations/
class_schedule.py) and the skill wrapping them. Deliberately not RAG-based
-- "what classes do I have today" needs an actual clock, which semantic
document retrieval can't provide; these tests pin specific fake "now"
values so the date logic itself is verified deterministically.
"""
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.integrations import class_schedule
from src.skills.class_schedule import ClassScheduleSkill


def _dt(*, weekday_name, hour, minute):
    """Build a real datetime that falls on the given weekday name (walks
    forward from a known Monday) at the given time -- avoids relying on
    whatever day the test happens to run on."""
    # 2024-01-01 was a Monday.
    base = datetime(2024, 1, 1)
    weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    offset = weekdays.index(weekday_name)
    return base.replace(hour=hour, minute=minute) + timedelta(days=offset)


def test_classes_today_matches_seeded_monday_schedule():
    monday = _dt(weekday_name="Monday", hour=8, minute=0)
    sessions = class_schedule.classes_today(now=monday)
    assert [s.subject for s in sessions] == ["Mathematics", "Science", "English"]


def test_classes_tomorrow_from_monday_is_tuesday():
    monday = _dt(weekday_name="Monday", hour=8, minute=0)
    sessions = class_schedule.classes_tomorrow(now=monday)
    assert [s.subject for s in sessions] == ["History", "Mathematics"]


def test_classes_tomorrow_from_friday_is_saturday_with_no_classes():
    friday = _dt(weekday_name="Friday", hour=8, minute=0)
    assert class_schedule.classes_tomorrow(now=friday) == []


def test_next_class_later_same_day():
    # Monday 09:30 -- Mathematics (09:00) has started, Science (10:30) hasn't.
    monday_mid_morning = _dt(weekday_name="Monday", hour=9, minute=30)
    nxt = class_schedule.next_class(now=monday_mid_morning)
    assert nxt.subject == "Science"


def test_next_class_rolls_over_to_next_day_after_last_class():
    # Monday 15:00 -- every Monday class is over; next one is Tuesday's first.
    monday_evening = _dt(weekday_name="Monday", hour=15, minute=0)
    nxt = class_schedule.next_class(now=monday_evening)
    assert nxt.subject == "History"


def test_next_class_rolls_over_a_weekend():
    friday_evening = _dt(weekday_name="Friday", hour=18, minute=0)
    nxt = class_schedule.next_class(now=friday_evening)
    assert nxt.subject == "Mathematics"  # Monday's first class


# ------------------------------------------------------------- skill layer --
def test_skill_reads_when_param_when_a_real_llm_supplies_it():
    result = ClassScheduleSkill().run({"when": "next"}, {})
    assert result.success
    assert "class" in result.output.lower()


def test_skill_falls_back_to_query_text_under_mock_style_params():
    """The mock planner never extracts a clean 'when' param -- it always
    hands back {"query": text, "message": text} -- so the skill must parse
    the raw text itself to stay correct under the free/offline profile."""
    result = ClassScheduleSkill().run({"query": "show tomorrow's schedule", "message": "show tomorrow's schedule"}, {})
    assert result.success
    assert "tomorrow" in result.output.lower()


def test_skill_defaults_to_today_with_no_recognizable_time_word():
    result = ClassScheduleSkill().run({"query": "what classes do I have", "message": "what classes do I have"}, {})
    assert "today" in result.output.lower()
