from src.skills.base import Skill, SkillResult


class FAQLookupSkill(Skill):
    name = "faq_lookup"
    description = "Answer a factual question by searching the FAQ / knowledge base."
    keywords = ["what", "when", "where", "how", "faq", "?"]
    parameters = {"query": "string"}

    def run(self, params, memory) -> SkillResult:
        query = params.get("query", "")
        hits = memory.search_faq(query)
        if hits:
            return SkillResult(True, hits[0]["answer"], {"matches": hits})
        return SkillResult(False, "I don't have an answer for that yet.", {"matches": []})
