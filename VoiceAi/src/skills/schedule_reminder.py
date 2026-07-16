from src.skills.base import Skill, SkillResult


class ScheduleReminderSkill(Skill):
    name = "schedule_reminder"
    description = "Schedule a meeting or reminder at a given time."
    keywords = ["schedule", "remind", "meeting", "appointment", "book"]
    parameters = {"time": "string", "subject": "string"}

    def run(self, params, ctx) -> SkillResult:
        time = params.get("time", "an unspecified time")
        subject = params.get("subject", "your reminder")
        return SkillResult(True, f"Scheduled '{subject}' for {time}.", {"time": time, "subject": subject})
