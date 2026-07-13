import json
from dataclasses import dataclass, field
from typing import Dict, List

from src.llm import LLMBackend

NORMALIZER_SYSTEM_PROMPT = (
    "You extract structured intent from a (possibly multilingual / "
    "code-switched) user utterance. Respond ONLY with JSON of the form "
    '{"intent": str, "entities": {...}, "languages_detected": [...], '
    '"clean_text": str}. Do not translate word-for-word; capture meaning.'
)


@dataclass
class NormalizedResult:
    intent: str
    entities: Dict = field(default_factory=dict)
    languages_detected: List[str] = field(default_factory=lambda: ["en"])
    clean_text: str = ""


def normalize(clean_text: str, llm: LLMBackend) -> NormalizedResult:
    raw = llm.complete(NORMALIZER_SYSTEM_PROMPT, clean_text, task="normalize")
    data = json.loads(raw)
    return NormalizedResult(
        intent=data.get("intent", "unknown"),
        entities=data.get("entities", {}),
        languages_detected=data.get("languages_detected", ["en"]),
        clean_text=data.get("clean_text", clean_text),
    )
