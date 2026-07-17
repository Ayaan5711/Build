from src.integrations.reminders_store import list_reminders
from src.skills.base import Skill, SkillResult


class ListRemindersSkill(Skill):
    """Companion to ScheduleReminderSkill -- lets a user (or a demo) verify
    a reminder actually got saved, not just that the assistant said it
    would. Real persistence you can check, not a claim you have to trust."""

    name = "list_reminders"
    description = "List the reminders that have already been scheduled for this user."
    keywords = ["list reminders", "my reminders", "what reminders", "show my reminders", "what did i schedule"]
    parameters = {}

    def run(self, params, ctx) -> SkillResult:
        user_memory = ctx.get("user_memory")
        user_id = getattr(user_memory, "user_id", None) or "demo-user"
        reminders = list_reminders(user_id)
        if not reminders:
            return SkillResult(True, "You don't have any reminders saved yet.", {"reminders": []})
        lines = [f"{r.subject} at {r.time}" for r in reminders]
        return SkillResult(True, "Your reminders: " + "; ".join(lines) + ".", {"reminders": lines})
