import re
from dataclasses import dataclass, field
from typing import List

from src.input.merge import InputContext

# Native-script Unicode ranges.
_DEVANAGARI = re.compile(r"[ऀ-ॿ]")  # Hindi, Marathi, etc.
_BENGALI = re.compile(r"[ঀ-৿]")

# Common function words seen in romanized Hindi/Bengali code-mixed speech
# (the kind ASR actually produces for code-switched utterances, e.g. "Kal
# meeting ache at 5 PM" / "mera appointment book kar do" from the team's
# own research notes). This is a deliberately small, extensible heuristic
# list, not a language model -- good enough to flag code-mixing for FR-05.
_ROMANIZED_HINDI = {"hai", "kar", "mera", "meri", "aur", "kya", "nahi", "karo", "kal", "abhi", "accha"}
_ROMANIZED_BENGALI = {"ache", "achhe", "kobe", "tumi", "ami", "bhalo", "korbo", "koro"}


@dataclass
class LanguageReport:
    languages_detected: List[str] = field(default_factory=lambda: ["en"])
    code_mixed: bool = False
    romanized_markers: List[str] = field(default_factory=list)


def detect_language_mix(input_context: InputContext) -> LanguageReport:
    """
    Rule-based language-mix detector (FR-05) -- checks native script ranges
    (Devanagari/Bengali) and a small romanized-keyword heuristic, since
    code-switched speech is usually transcribed in Latin script by ASR
    (e.g. "Kal meeting ache at 5 PM"). Deliberately rule-based rather than
    routed through the mock LLM, so it gives a real signal even with
    LLM_BACKEND=mock.
    """
    text = input_context.text
    if not text:
        return LanguageReport()

    languages = ["en"]
    markers = []

    if _DEVANAGARI.search(text):
        languages.append("hi")
        markers.append("devanagari_script")
    if _BENGALI.search(text):
        languages.append("bn")
        markers.append("bengali_script")

    words = set(re.findall(r"[a-zA-Z']+", text.lower()))
    hindi_hits = words & _ROMANIZED_HINDI
    bengali_hits = words & _ROMANIZED_BENGALI
    if hindi_hits:
        if "hi" not in languages:
            languages.append("hi")
        markers.extend(f"romanized_hindi:{w}" for w in sorted(hindi_hits))
    if bengali_hits:
        if "bn" not in languages:
            languages.append("bn")
        markers.extend(f"romanized_bengali:{w}" for w in sorted(bengali_hits))

    code_mixed = len(languages) > 1
    return LanguageReport(languages_detected=languages, code_mixed=code_mixed, romanized_markers=markers)
