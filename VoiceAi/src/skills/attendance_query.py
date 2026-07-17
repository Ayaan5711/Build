from datetime import date, timedelta

from src.integrations import student_records
from src.skills.base import Skill, SkillResult


class AttendanceQuerySkill(Skill):
    """Real, queryable answer to "who's absent today" -- reads the same
    student_records tables the Excel importer and MarkAttendanceSkill
    write to. Replaces the earlier static seed_data/classroom_knowledge.json
    "absent students" placeholder now that there's real attendance data to
    query instead of a scripted-for-demo fact (see README's known
    limitations for why that was a deliberate placeholder, not an
    oversight, when it was first built)."""

    name = "attendance_query"
    description = "Look up which students are absent on a given day (defaults to today)."
    keywords = ["absent students", "who is absent", "who's absent", "attendance today", "show absent"]
    parameters = {"when": "string"}

    def run(self, params, ctx) -> SkillResult:
        raw = str(params.get("when") or params.get("query") or params.get("message") or "").lower()
        target = date.today()
        if "yesterday" in raw:
            target = target - timedelta(days=1)
        date_str = target.isoformat()

        absentees = student_records.absentees_on(date_str)
        if not absentees:
            return SkillResult(True, f"No students marked absent on {date_str}.", {"date": date_str, "absentees": []})
        names = [f"{s.name} ({s.class_name})" for s in absentees]
        return SkillResult(True, f"Absent on {date_str}: " + "; ".join(names) + ".", {"date": date_str, "absentees": names})
