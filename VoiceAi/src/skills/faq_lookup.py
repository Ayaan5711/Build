from src.skills.base import Skill, SkillResult


class FAQLookupSkill(Skill):
    name = "faq_lookup"
    description = "Answer a factual question by searching the FAQ / knowledge base."
    keywords = ["what", "when", "where", "how", "faq", "?"]
    parameters = {"query": "string"}

    def run(self, params, ctx) -> SkillResult:
        kb = ctx["knowledge_base"]
        query = params.get("query", "")
        hits = kb.retrieve(query, k=1)
        if hits:
            return SkillResult(True, hits[0].content, {"matches": [h.title for h in hits]})
        return SkillResult(False, "I don't have an answer for that yet.", {"matches": []})
