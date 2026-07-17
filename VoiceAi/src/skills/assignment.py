from src.integrations.assignments_store import create_assignment
from src.skills.base import Skill, SkillResult


class CreateAssignmentSkill(Skill):
    """The flagship classroom example of a genuinely multi-field create
    action -- structurally identical to ScheduleReminderSkill (three
    required details instead of two), so it reuses the exact same paced,
    one-question-at-a-time dialogue mechanism (see
    src/understanding/dialogue_state.py) rather than any new machinery."""

    name = "create_assignment"
    description = "Create a class assignment for a chapter or topic, with a due date and class. Persisted so it can be looked up later (list_assignments)."
    keywords = ["create an assignment", "create assignment", "new assignment", "assignment for", "homework"]
    parameters = {"chapter": "string", "due_date": "string", "class_name": "string"}

    # Asked in this order: what, then who it's for, then when.
    required_slots = {
        "chapter": "Which chapter or topic is this assignment for?",
        "class_name": "Which class is this assignment for?",
        "due_date": "When is this assignment due?",
    }

    def run(self, params, ctx) -> SkillResult:
        chapter = str(params.get("chapter", "")).strip() or "the assignment"
        class_name = str(params.get("class_name", "")).strip() or "your class"
        due_date = str(params.get("due_date", "")).strip() or "an unspecified date"
        user_memory = ctx.get("user_memory")
        user_id = getattr(user_memory, "user_id", None) or "demo-user"
        assignment = create_assignment(user_id=user_id, chapter=chapter, due_date=due_date, class_name=class_name)
        return SkillResult(
            True,
            f'Created. Assignment on "{assignment.chapter}" for {assignment.class_name}, due {assignment.due_date}.',
            {"id": assignment.id, "chapter": assignment.chapter, "due_date": assignment.due_date, "class_name": assignment.class_name},
        )
