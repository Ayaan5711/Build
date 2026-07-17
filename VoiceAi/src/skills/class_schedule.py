from src.integrations import class_schedule
from src.skills.base import Skill, SkillResult


def _format_sessions(sessions) -> str:
    if not sessions:
        return "no classes"
    return "; ".join(f"{c.subject} {c.start_time}-{c.end_time} in {c.room}" for c in sessions)


class ClassScheduleSkill(Skill):
    """Answers "what classes today/tomorrow" and "when's my next class"
    against a real seeded weekly timetable + real datetime math (see
    src/integrations/class_schedule.py) -- not a static RAG guess."""

    name = "class_schedule"
    description = "Answer questions about today's or tomorrow's class schedule, or when the next class is."
    # Deliberately no bare "schedule" or "class" here -- both collide with
    # ScheduleReminderSkill's "book"/"meeting"/"appointment" territory
    # under the mock backend's plain substring keyword router ("schedule a
    # reminder" vs "show my schedule" are opposite intents that share a
    # word). Compound phrases keep the two skills unambiguous under mock;
    # a real LLM backend disambiguates by actual meaning instead.
    keywords = ["classes", "next class", "class schedule", "tomorrow's schedule", "today's schedule", "my schedule", "timetable"]
    parameters = {"when": "string"}  # "today" | "tomorrow" | "next"

    def run(self, params, ctx) -> SkillResult:
        # Prefer a real LLM's extracted "when" param; fall back to reading
        # the raw query/message the mock planner always supplies instead
        # (src/llm.py's MockLLMBackend never extracts named fields), so
        # "show tomorrow's schedule" is answered correctly under both.
        raw = str(params.get("when") or params.get("query") or params.get("message") or "").lower()

        if "tomorrow" in raw:
            sessions = class_schedule.classes_tomorrow()
            return SkillResult(True, f"Tomorrow's classes: {_format_sessions(sessions)}.", {"count": len(sessions)})

        if "next" in raw:
            nxt = class_schedule.next_class()
            if not nxt:
                return SkillResult(True, "You don't have any more classes scheduled this week.", {})
            return SkillResult(
                True,
                f"Your next class is {nxt.subject} at {nxt.start_time} in {nxt.room}.",
                {"subject": nxt.subject, "start_time": nxt.start_time, "room": nxt.room},
            )

        sessions = class_schedule.classes_today()
        return SkillResult(True, f"Today's classes: {_format_sessions(sessions)}.", {"count": len(sessions)})
