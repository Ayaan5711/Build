import json
from dataclasses import dataclass
from typing import Optional

from src import config
from src.input.merge import InputContext
from src.llm import LLMBackend

REASONING_SYSTEM_PROMPT = (
    "You support an accessibility-first voice assistant. The transcript below has "
    "low ASR confidence, possibly due to an accent, regional pronunciation, or "
    "background noise. If there's a plausible near-homophone the user likely meant "
    "(e.g. a number, a name, a place), suggest ONE short clarifying question like "
    '"Did you mean X?". Respond ONLY with JSON: {"clarifying_question": <string or null>}.'
)


@dataclass
class AccentNoiseReport:
    confidence: float
    is_low_confidence: bool
    clarifying_question: Optional[str] = None


def analyze_accent_noise_confidence(input_context: InputContext, llm: LLMBackend = None) -> AccentNoiseReport:
    """
    Surfaces ASR/gesture confidence and, when it's low, asks a reasoning
    model for a plausible clarifying question (FR-06) -- e.g. demo sample 3:
    "eleven" misheard in a regional accent -> "Did you mean floor 11?".
    Confidence itself already comes from the ASR/vision backend; this stage
    decides what to DO about low confidence, not re-measure it.
    """
    confidence = input_context.confidence
    is_low = confidence < config.CONFIDENCE_THRESHOLD

    if not is_low or not input_context.text:
        return AccentNoiseReport(confidence=confidence, is_low_confidence=is_low, clarifying_question=None)

    if llm is None:
        return AccentNoiseReport(confidence=confidence, is_low_confidence=True, clarifying_question=None)

    raw = llm.complete(REASONING_SYSTEM_PROMPT, input_context.text, task="clarify")
    try:
        data = json.loads(raw)
        question = data.get("clarifying_question")
    except (json.JSONDecodeError, AttributeError):
        question = None
    return AccentNoiseReport(confidence=confidence, is_low_confidence=True, clarifying_question=question)
