import json
from dataclasses import dataclass, field
from typing import List

from src.llm import LLMBackend

SIMPLIFY_SYSTEM_PROMPT = (
    "You reduce cognitive load for a voice assistant user (FR-08). Given a complex, "
    "multi-step instruction (e.g. IVR-style: 'press one, then go to three, then "
    "enter account number'), break it into short, plain-language steps, one action "
    "per step, presented one at a time rather than all in one long instruction. "
    'Respond ONLY with JSON: {"steps": [<string>, ...]}.'
)

# Instructions longer than this many words are treated as complex enough to
# warrant step-by-step breakdown -- short instructions are left as-is so we
# don't over-simplify a one-line request.
_COMPLEXITY_WORD_THRESHOLD = 12


@dataclass
class SimplifiedSteps:
    steps: List[str] = field(default_factory=list)
    was_simplified: bool = False


def needs_simplification(text: str) -> bool:
    return len(text.split()) > _COMPLEXITY_WORD_THRESHOLD or text.lower().count(" then ") >= 2


def simplify_instructions(text: str, llm: LLMBackend) -> SimplifiedSteps:
    """
    FR-08: breaks complex multi-step instructions into short, confirmable
    steps. Only triggers when the instruction actually looks complex
    (see needs_simplification) -- a short request stays a short request,
    consistent with "Simplify" meaning natural conversation, not forcing
    structure onto everything.
    """
    if not needs_simplification(text):
        return SimplifiedSteps(steps=[text], was_simplified=False)
    raw = llm.complete(SIMPLIFY_SYSTEM_PROMPT, text, task="simplify")
    data = json.loads(raw)
    steps = data.get("steps") or [text]
    return SimplifiedSteps(steps=steps, was_simplified=True)
