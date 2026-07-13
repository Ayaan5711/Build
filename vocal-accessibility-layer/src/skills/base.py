from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class SkillResult:
    success: bool
    output: str
    data: Dict[str, Any] = field(default_factory=dict)


class Skill:
    """
    A single pluggable capability. Adding a new match-day use case means
    dropping one new file in this folder that subclasses Skill -- nothing
    in the foundation layer, orchestrator, or guardrail needs to change.
    """

    name: str = ""
    description: str = ""
    # Only used by the offline MockLLMBackend's simple keyword router; real
    # LLM backends route by description + extracted intent instead.
    keywords: List[str] = []
    parameters: Dict[str, str] = {}

    def run(self, params: Dict[str, Any], memory) -> SkillResult:
        raise NotImplementedError

    def schema(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "keywords": self.keywords,
            "parameters": self.parameters,
        }
