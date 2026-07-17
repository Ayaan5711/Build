from src.integrations.assignments_store import list_assignments
from src.skills.base import Skill, SkillResult


class ListAssignmentsSkill(Skill):
    """Companion to CreateAssignmentSkill -- proves an assignment actually
    got saved, not just claimed (same reasoning as ListRemindersSkill)."""

    name = "list_assignments"
    description = "List the assignments that have already been created."
    keywords = ["list assignments", "my assignments", "what assignments", "show assignments"]
    parameters = {}

    def run(self, params, ctx) -> SkillResult:
        user_memory = ctx.get("user_memory")
        user_id = getattr(user_memory, "user_id", None) or "demo-user"
        assignments = list_assignments(user_id)
        if not assignments:
            return SkillResult(True, "You haven't created any assignments yet.", {"assignments": []})
        lines = [f'{a.chapter} ({a.class_name}), due {a.due_date}' for a in assignments]
        return SkillResult(True, "Your assignments: " + "; ".join(lines) + ".", {"assignments": lines})
