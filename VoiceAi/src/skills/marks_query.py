from src.integrations import student_records
from src.skills.base import Skill, SkillResult


class MarksQuerySkill(Skill):
    """Real, per-student marks lookup against the SQLite marks table
    (loaded from marks_midterm.xlsx-style files via
    scripts/import_classroom_data.py)."""

    name = "marks_query"
    description = "Look up a student's marks/scores, optionally filtered to one exam."
    keywords = ["what did", "score in", "marks in", "grade in", "how did", "midterm score"]
    parameters = {"student_name": "string", "exam": "string"}
    required_slots = {
        "student_name": "Which student's marks would you like?",
    }

    def run(self, params, ctx) -> SkillResult:
        name = str(params.get("student_name", "")).strip()
        exam = str(params.get("exam", "")).strip() or None
        if not name:
            return SkillResult(False, "I need a student's name to look up marks.", {})

        student = student_records.get_student_by_name(name)
        if not student:
            return SkillResult(False, f"I don't have any record of a student named {name}.", {})

        marks = student_records.marks_for_student(student.student_id, exam=exam)
        if not marks:
            scope = f" for {exam}" if exam else ""
            return SkillResult(True, f"No marks on record for {student.name}{scope}.", {"marks": []})

        lines = [f"{m.subject}: {m.score}" + (f"/{m.max_score}" if m.max_score else "") for m in marks]
        return SkillResult(True, f"{student.name}'s marks: " + "; ".join(lines) + ".", {"marks": lines})
