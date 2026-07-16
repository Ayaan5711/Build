from src.skills.base import Skill, SkillResult


class GeneralHelpSkill(Skill):
    """
    Graceful catch-all: when nothing else matches, acknowledge what was
    heard instead of failing silently (FR-16, Appendix B: never assume,
    always show what was understood).
    """

    name = "general_help"
    description = "Fallback for greetings, thanks, or anything with no specific matching skill."
    keywords = ["hi", "hello", "hey", "thanks", "thank you", "help"]
    parameters = {"message": "string"}

    def run(self, params, ctx) -> SkillResult:
        message = params.get("message", "")
        return SkillResult(
            True,
            f'I heard: "{message}". I don\'t have a specific action for that yet, but I\'m listening.',
            {},
        )
