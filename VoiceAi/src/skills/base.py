from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class SkillResult:
    success: bool
    output: str
    data: Dict[str, Any] = field(default_factory=dict)


class Skill:
    """
    A single pluggable domain action (FR-20, Domain-Aware Assistance).
    Adding a new match-day use case means dropping one new file in this
    folder that subclasses Skill -- nothing in the foundation pipeline
    (ASR, normalization, accessibility analysis, RAG) needs to change.
    A skill's output feeds into generate_grounded_response() as one more
    input, alongside RAG context -- it is not the final answer by itself.
    """

    name: str = ""
    description: str = ""
    keywords: List[str] = []  # used by the mock LLM's simple keyword router
    parameters: Dict[str, str] = {}

    def run(self, params: Dict[str, Any], ctx: Dict[str, Any]) -> SkillResult:
        """ctx carries shared resources, e.g. {"knowledge_base": KnowledgeBase,
        "user_memory": UserMemory} -- built once per pipeline run in pipeline.py."""
        raise NotImplementedError

    def schema(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "keywords": self.keywords,
            "parameters": self.parameters,
        }
