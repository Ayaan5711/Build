from dataclasses import dataclass, field
from typing import List


@dataclass
class TransparencyReport:
    asr_confidence: float
    corrections_made: bool
    languages_detected: List[str] = field(default_factory=lambda: ["en"])
    skill_invoked: str = ""
    guardrail_approved: bool = True
    guardrail_reason: str = ""

    def badges(self) -> List[str]:
        badges = [f"Speech recognized by AI (confidence: {self.asr_confidence:.0%})"]
        if self.corrections_made:
            badges.append("Disfluency corrected")
        if len(self.languages_detected) > 1 or (self.languages_detected and self.languages_detected[0] != "en"):
            badges.append(f"Languages detected: {', '.join(self.languages_detected)}")
        if self.skill_invoked:
            badges.append(f"Action: {self.skill_invoked}")
        badges.append("Verified" if self.guardrail_approved else f"Needs confirmation ({self.guardrail_reason})")
        return badges
