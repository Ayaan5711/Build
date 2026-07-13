import json
from dataclasses import dataclass

from src.llm import LLMBackend

GUARDRAIL_SYSTEM_PROMPT = (
    "You are a safety verifier for a voice accessibility assistant. Given "
    "the ASR confidence and the action about to be taken, decide whether "
    "it's safe to proceed automatically or whether the user should confirm "
    'first. Respond ONLY with JSON: {"approved": bool, "reason": str}.'
)


@dataclass
class GuardrailResult:
    approved: bool
    reason: str


def check(confidence: float, action_summary: str, llm: LLMBackend) -> GuardrailResult:
    payload = {"confidence": confidence, "action": action_summary}
    raw = llm.complete(GUARDRAIL_SYSTEM_PROMPT, json.dumps(payload), task="guardrail")
    data = json.loads(raw)
    return GuardrailResult(approved=data.get("approved", False), reason=data.get("reason", ""))
