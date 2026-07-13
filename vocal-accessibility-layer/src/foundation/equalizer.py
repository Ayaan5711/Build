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


def equalize(raw_text: str, llm: LLMBackend) -> EqualizerResult:
    clean_text = llm.complete(EQUALIZER_SYSTEM_PROMPT, raw_text, task="equalizer").strip()
    return EqualizerResult(clean_text=clean_text, corrections_made=clean_text != raw_text.strip())
