from src.integrations.reminders_store import create_reminder
from src.skills.base import Skill, SkillResult


class ScheduleReminderSkill(Skill):
    name = "schedule_reminder"
    description = "Schedule a reminder or meeting at a given time. Persisted so it can be looked up later (list_reminders)."
    keywords = ["schedule", "remind", "meeting", "appointment", "book"]
    parameters = {"time": "string", "subject": "string"}

    # Declared in the order they should be asked -- subject first ("what"),
    # then time ("when"). If the planner already extracted both from one
    # utterance, neither question gets asked; the paced dialogue only
    # kicks in for whatever's actually missing (see agent.py).
    required_slots = {
        "subject": "What should I remind you about?",
        "time": "When should I remind you? For example, 'tomorrow at 5pm'.",
    }

    def run(self, params, ctx) -> SkillResult:
        subject = str(params.get("subject", "")).strip() or "your reminder"
        time = str(params.get("time", "")).strip() or "an unspecified time"
        user_memory = ctx.get("user_memory")
        user_id = getattr(user_memory, "user_id", None) or "demo-user"
        reminder = create_reminder(user_id=user_id, subject=subject, time=time)
        return SkillResult(
            True,
            f"Saved. I'll remind you about \"{reminder.subject}\" at {reminder.time}.",
            {"id": reminder.id, "subject": reminder.subject, "time": reminder.time},
        )
