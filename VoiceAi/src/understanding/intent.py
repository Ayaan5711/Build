import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from src.input.vision import GestureResult
from src.llm import LLMBackend

INTENT_SYSTEM_PROMPT = (
    "You extract structured intent from an accessible transcript (and, if present, "
    "a sign/gesture's candidate intent). Identify the user's GOAL, not just the "
    "literal words. Do not translate word-for-word for code-mixed input -- capture "
    "meaning. Respond ONLY with JSON: {\"goal\": <string>, \"action_type\": <string>, "
    '"entities": {...}, "constraints": [...], "urgency": "low"|"normal"|"high", '
    '"missing_information": [...]}.'
)


@dataclass
class Intent:
    goal: str = "unknown"
    action_type: str = "unknown"
    entities: Dict = field(default_factory=dict)
    constraints: List[str] = field(default_factory=list)
    urgency: str = "normal"
    missing_information: List[str] = field(default_factory=list)


def extract_intent(accessible_text: str, sign_result: Optional[GestureResult], llm: LLMBackend) -> Intent:
    """
    FR-11: goal, action type, entities, constraints, urgency, and missing
    information -- deliberately richer than a plain intent label, since the
    PRD requires understanding what the user is trying to ACHIEVE, not just
    what they said. If a gesture was also captured, its candidate_intent is
    passed as extra context (e.g. thumbs_up -> "confirm").
    """
    payload = {
        "accessible_text": accessible_text,
        "sign_candidate_intent": sign_result.candidate_intent if sign_result else None,
    }
    raw = llm.complete(INTENT_SYSTEM_PROMPT, json.dumps(payload), task="intent")
    data = json.loads(raw)
    return Intent(
        goal=data.get("goal", "unknown"),
        action_type=data.get("action_type", "unknown"),
        entities=data.get("entities", {}),
        constraints=data.get("constraints", []),
        urgency=data.get("urgency", "normal"),
        missing_information=data.get("missing_information", []),
    )
