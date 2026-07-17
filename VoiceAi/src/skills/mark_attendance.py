from datetime import date

from src.integrations import student_records
from src.skills.base import Skill, SkillResult


class MarkAttendanceSkill(Skill):
    """Live, voice-driven attendance update -- writes into the exact same
    student_records tables the bulk Excel importer populates (see
    scripts/import_classroom_data.py), so a teacher can add or correct
    today's attendance mid-conversation instead of only ever bulk-importing
    a file after the fact. Reuses the paced-dialogue mechanism (two
    required slots) rather than any new machinery."""

    name = "mark_attendance"
    description = "Mark a student present or absent for a given date (defaults to today)."
    keywords = ["mark absent", "mark present", "mark attendance", "attendance for"]
    parameters = {"student_name": "string", "status": "string", "date": "string"}
    required_slots = {
        "student_name": "Which student?",
        "status": "Should I mark them present or absent?",
    }

    def run(self, params, ctx) -> SkillResult:
        name = str(params.get("student_name", "")).strip()
        status = self._parse_status(str(params.get("status", "")))
        date_str = str(params.get("date", "")).strip() or date.today().isoformat()

        if not name:
            return SkillResult(False, "I need a student's name to mark attendance.", {})
        if status is None:
            return SkillResult(False, "I need to know whether to mark them present or absent.", {})

        student = student_records.get_student_by_name(name)
        if student:
            student_id, display_name = student.student_id, student.name
        else:
            # Not in the roster yet -- create a minimal record rather than
            # silently dropping a real attendance mark (same reasoning as
            # excel_import.py's _resolve_student_id fallback).
            student_id, display_name = name, name
            student_records.upsert_student(student_id, name, "unspecified")

        student_records.mark_attendance(student_id, date_str, status)
        return SkillResult(
            True,
            f"Marked {display_name} {status} for {date_str}.",
            {"student_id": student_id, "date": date_str, "status": status},
        )

    @staticmethod
    def _parse_status(raw: str):
        lower = raw.lower()
        if any(w in lower for w in ("absent", "away", "missing", "not here", "not present")):
            return "absent"
        if any(w in lower for w in ("present", "here", "came", "in class")):
            return "present"
        return None
