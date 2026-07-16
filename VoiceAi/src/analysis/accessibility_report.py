import json
from dataclasses import dataclass, field, asdict
from typing import List, Optional

from src.analysis.accent_noise import AccentNoiseReport
from src.analysis.disfluency import DisfluencyReport
from src.analysis.language import LanguageReport
from src.input.vision import GestureResult
from src.llm import LLMBackend

REASONING_SYSTEM_PROMPT = (
    "You analyze accessibility barriers for a voice assistant, in the style of "
    "PAS 901:2025. Given signals about disfluency, language mixing, ASR "
    "confidence, and sign/gesture use, identify which barrier categories are "
    "present and what support was applied. Be supportive, never diagnostic -- "
    "describe processing challenges, not the person. Respond ONLY with JSON: "
    '{"barriers_detected": [...], "support_applied": [...], "notes": <string>}.'
)


@dataclass
class AccessibilityReport:
    barriers_detected: List[str] = field(default_factory=lambda: ["none_detected"])
    support_applied: List[str] = field(default_factory=lambda: ["no support needed"])
    notes: str = "supportive assistance, not a diagnosis"


def analyze_accessibility(
    disfluency_report: DisfluencyReport,
    language_report: LanguageReport,
    accent_noise_report: AccentNoiseReport,
    sign_result: Optional[GestureResult],
    llm: LLMBackend,
) -> AccessibilityReport:
    """
    Synthesizes every upstream signal into the structured barrier report
    required by FR-09 -- this is the "Accessibility AI Engineer" deliverable
    per the PRD's team-roles table. Responsible-AI framing (Appendix B):
    describes processing challenges and support applied, never a diagnosis
    or a ranking of the user.
    """
    payload = {
        "disfluency_report": asdict(disfluency_report),
        "language_report": asdict(language_report),
        "accent_noise_report": asdict(accent_noise_report),
        "sign_result": asdict(sign_result) if sign_result else None,
    }
    raw = llm.complete(REASONING_SYSTEM_PROMPT, json.dumps(payload), task="accessibility_report")
    data = json.loads(raw)
    return AccessibilityReport(
        barriers_detected=data.get("barriers_detected", ["none_detected"]),
        support_applied=data.get("support_applied", ["no support needed"]),
        notes=data.get("notes", "supportive assistance, not a diagnosis"),
    )
