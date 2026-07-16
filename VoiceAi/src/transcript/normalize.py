import json
from dataclasses import dataclass

from src.llm import LLMBackend

NORMALIZE_SYSTEM_PROMPT = (
    "You are a speech normalizer for an accessibility system. The input "
    "transcript may contain stutters, repeated syllables, filler words, or "
    "false starts. Output ONLY the corrected, fluent sentence. Preserve the "
    "original meaning and any names or numbers EXACTLY -- do not paraphrase "
    "and do not add information that wasn't said (Appendix B: preserve "
    "meaning during normalization)."
)


@dataclass
class AccessibleTranscript:
    text: str
    corrections_made: bool


def normalize_transcript(raw_text: str, llm: LLMBackend, known_corrections: dict = None) -> AccessibleTranscript:
    """
    FR-04: creates an accessible transcript without changing meaning
    (Member 4's normalize_transcript() deliverable). known_corrections is a
    per-user correction history (e.g. {"Ka-ka-Kiran": "Kiran"}) applied on
    top of the general cleanup -- the personalization loop.
    """
    system_prompt = NORMALIZE_SYSTEM_PROMPT
    if known_corrections:
        system_prompt += "\nKnown correct spellings for this user: " + json.dumps(known_corrections)
    clean_text = llm.complete(system_prompt, raw_text, task="cleanup", context=known_corrections).strip()
    return AccessibleTranscript(text=clean_text, corrections_made=clean_text != raw_text.strip())
