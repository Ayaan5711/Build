import json
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from src.llm import LLMBackend
from src.skills import get_skills

ORCHESTRATOR_SYSTEM_PROMPT = (
    "You are a routing agent for a voice accessibility assistant. Given the "
    "user's normalized request and a list of available skills, choose the "
    "single best skill to handle it and extract its required parameters. "
    'Respond ONLY with JSON: {"skill": <name or null>, "params": {...}, '
    '"clarify": <question string or null>}. Set "skill" to null and fill '
    '"clarify" if the request is ambiguous or no skill fits.'
)


@dataclass
class OrchestrationResult:
    skill_name: Optional[str]
    params: Dict[str, Any] = field(default_factory=dict)
    clarify: Optional[str] = None


def orchestrate(intent: str, entities: dict, clean_text: str, llm: LLMBackend) -> OrchestrationResult:
    skills = get_skills()
    payload = {
        "clean_text": clean_text,
        "intent": intent,
        "entities": entities,
        "available_skills": [s.schema() for s in skills.values()],
    }
    raw = llm.complete(ORCHESTRATOR_SYSTEM_PROMPT, json.dumps(payload), task="orchestrate")
    data = json.loads(raw)
    return OrchestrationResult(
        skill_name=data.get("skill"),
        params=data.get("params", {}),
        clarify=data.get("clarify"),
    )
