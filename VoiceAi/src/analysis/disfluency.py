import re
from dataclasses import dataclass, field
from typing import List

from src.input.merge import InputContext

FILLER_WORDS = {"um", "uh", "erm", "hmm", "like", "you know", "i mean"}


@dataclass
class DisfluencyReport:
    has_disfluency: bool
    repeated_syllables: List[str] = field(default_factory=list)
    repeated_words: List[str] = field(default_factory=list)
    filler_words_found: List[str] = field(default_factory=list)
    long_pause_markers: int = 0


def _find_repeated_syllable_words(text: str) -> List[str]:
    """
    Finds hyphen-joined words where the leading fragments repeat the same
    (short) syllable, e.g. "Ka-ka-ka-Kiran" or "B-b-b-book" or "M-m-m-my".
    A pure same-length backreference regex only catches single-character
    repeats ("M-m-m-my"); this also catches multi-character syllables
    ("Ka-ka-ka-...") and prefix-completions where the final fragment is a
    full word starting with the repeated syllable ("...-book", "...-Kiran"
    doesn't match here since "Kiran" doesn't start with "ka", but 3 prior
    repeats are still enough to flag it).
    """
    hits = []
    for word in re.findall(r"[\w-]+", text):
        fragments = word.split("-")
        if len(fragments) < 2:
            continue
        repeat_count = 1
        for i in range(1, len(fragments)):
            prev, curr = fragments[i - 1].lower(), fragments[i].lower()
            if curr == prev or curr.startswith(prev) or prev.startswith(curr):
                repeat_count += 1
            else:
                break
        if repeat_count >= 2:
            hits.append(word)
    return hits


def detect_stammering(input_context: InputContext) -> DisfluencyReport:
    """
    Rule-based disfluency detector (FR-03) -- deliberately not an LLM call,
    so it's fast, deterministic, and independently testable (Member 3's
    `detect_stammering()` deliverable per the PRD team-roles table).
    Flags: repeated syllables ("B-b-b-book", "Ka-ka-ka-Kiran"), repeated
    words ("the the"), filler words, and "..." pause markers if present.
    """
    text = input_context.text
    if not text:
        return DisfluencyReport(has_disfluency=False)

    repeated_syllables = _find_repeated_syllable_words(text)

    words = re.findall(r"[\w']+", text.lower())
    repeated_words = []
    for i in range(1, len(words)):
        if words[i] == words[i - 1] and words[i] not in repeated_words:
            repeated_words.append(words[i])

    lower_text = text.lower()
    fillers_found = [f for f in FILLER_WORDS if re.search(rf"\b{re.escape(f)}\b", lower_text)]

    long_pause_markers = text.count("...") + text.count("--")

    has_disfluency = bool(repeated_syllables or repeated_words or fillers_found or long_pause_markers)
    return DisfluencyReport(
        has_disfluency=has_disfluency,
        repeated_syllables=repeated_syllables,
        repeated_words=repeated_words,
        filler_words_found=fillers_found,
        long_pause_markers=long_pause_markers,
    )
