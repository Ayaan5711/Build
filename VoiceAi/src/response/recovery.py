import json
from dataclasses import dataclass, field
from typing import List

from src import config
from src.analysis.accessibility_report import AccessibilityReport
from src.llm import LLMBackend

RECOVERY_SYSTEM_PROMPT = (
    "You decide whether a voice assistant should proceed automatically or ask the "
    "user to confirm/correct/retry/switch modality first (FR-16). Given confidence "
    "and any missing information, decide if confirmation is needed. Never let the "
    "system silently act on uncertain input. Respond ONLY with JSON: "
    '{"needs_confirmation": bool, "options": [...], "reason": <string>}.'
)


@dataclass
class RecoveryDecision:
    needs_confirmation: bool
    options: List[str] = field(default_factory=lambda: ["confirm"])
    reason: str = ""


def decide_recovery_or_confirmation(
    confidence: float,
    missing_slots: List[str],
    accessibility_report: AccessibilityReport,
    llm: LLMBackend,
) -> RecoveryDecision:
    """
    FR-16 / NFR-05: the system must never fail silently or act on uncertain
    input without asking. Available recovery options match the PRD's
    required UI vocabulary exactly: confirm, correct, retry, switch_modality.
    """
    payload = {
        "confidence": confidence,
        "missing_slots": missing_slots,
        "barriers_detected": accessibility_report.barriers_detected,
    }
    raw = llm.complete(RECOVERY_SYSTEM_PROMPT, json.dumps(payload), task="recovery")
    data = json.loads(raw)
    return RecoveryDecision(
        needs_confirmation=data.get("needs_confirmation", confidence < config.CONFIDENCE_THRESHOLD),
        options=data.get("options", ["confirm"]),
        reason=data.get("reason", ""),
    )
