import re
from typing import List, Optional

# Ordered most-specific-first so an unambiguous phrase is checked before a
# broader one that could collide with it (e.g. "that's wrong" must match
# "correct" the recovery action, not get swallowed by a loose "confirm"
# pattern). Deliberately rule-based, not an LLM call: this is the step a
# speak-and-listen-only user depends on to complete every interaction, so
# it needs to be instant, free, and to work identically on every backend
# profile (mock/local/hybrid/fast/hosted) -- not something that could be
# slow or degraded on a bad connection.
_PATTERNS = {
    "retry": [r"\bretry\b", r"\btry again\b", r"\bredo\b", r"\bonce more\b", r"\bagain\b"],
    "switch_modality": [
        r"\bswitch\b", r"\bchange mode\b", r"\bdifferent mode\b",
        r"\buse (the )?camera\b", r"\buse (the )?text\b", r"\buse (the )?voice\b", r"\buse (the )?mic\b",
    ],
    "correct": [
        r"\bthat'?s wrong\b", r"\bnot right\b", r"\bincorrect\b", r"\bfix (it|that)\b",
        r"\blet me (fix|edit|change)\b", r"\bedit (it|that)\b", r"\bchange (it|that)\b", r"\bno,? that'?s wrong\b",
    ],
    "confirm": [
        r"\byes\b", r"\byeah\b", r"\byep\b", r"\bconfirm\b", r"\bcorrect\b",
        r"\bsure\b", r"\bokay\b", r"\bok\b", r"\bright\b", r"\bgo ahead\b", r"\bproceed\b", r"\bthat'?s right\b",
    ],
}
_ORDER = ["retry", "switch_modality", "correct", "confirm"]


def match_recovery_intent(spoken_text: str, available_options: List[str]) -> Optional[str]:
    """
    Matches a short spoken reply (e.g. "yes", "try again", "that's wrong")
    against the recovery actions currently offered (confirm/correct/retry/
    switch_modality), so a voice-only user can complete the confirm/
    recover step without ever clicking a button. Returns None if nothing
    matches -- callers should leave the on-screen buttons available as the
    fallback, never silently guess.
    """
    if not spoken_text:
        return None
    lower = spoken_text.lower().strip()
    for action in _ORDER:
        if action not in available_options:
            continue
        for pattern in _PATTERNS[action]:
            if re.search(pattern, lower):
                return action
    return None
