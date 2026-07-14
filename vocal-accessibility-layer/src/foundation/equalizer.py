import json
from dataclasses import dataclass

from src.llm import LLMBackend

EQUALIZER_SYSTEM_PROMPT = (
    "You are a speech normalizer for an accessibility system. The input "
    "transcript may contain stutters, false starts, and filler words. "
    "Output ONLY the corrected, fluent sentence. Preserve the original "
    "meaning and any names or numbers exactly. Do not add information "
    "that wasn't said."
)


@dataclass
class EqualizerResult:
    clean_text: str
    corrections_made: bool


def equalize(raw_text: str, llm: LLMBackend, known_corrections: dict = None) -> EqualizerResult:
    """
    known_corrections is the per-user correction history from Memory (e.g.
    {"So-soumesh": "Soumesh"}) -- this is the personalization loop: once a
    user confirms a fix once, it's applied automatically next time instead
    of relying on the LLM to guess it again.
    """
    system_prompt = EQUALIZER_SYSTEM_PROMPT
    if known_corrections:
        system_prompt += "\nKnown correct spellings for this user: " + json.dumps(known_corrections)
    clean_text = llm.complete(system_prompt, raw_text, task="equalizer", context=known_corrections).strip()
    return EqualizerResult(clean_text=clean_text, corrections_made=clean_text != raw_text.strip())
