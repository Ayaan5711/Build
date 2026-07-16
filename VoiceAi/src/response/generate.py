import json
from dataclasses import dataclass
from typing import List, Optional

from src.analysis.accessibility_report import AccessibilityReport
from src.knowledge.rag import RetrievedSnippet
from src.llm import LLMBackend
from src.understanding.intent import Intent

RESPONSE_SYSTEM_PROMPT = (
    "You generate the final user-facing response for an accessibility-first voice "
    "assistant (FR-13). Combine the accessible transcript, the extracted intent, "
    "the accessibility support that was applied, and any retrieved knowledge "
    "snippets into ONE clear, plain-language response. Do not invent facts not "
    "present in the retrieved context. Keep it concise -- one to three sentences. "
    "If a domain skill already produced a result, incorporate it naturally."
)


@dataclass
class GroundedResponse:
    text: str
    used_context: List[str]


def generate_grounded_response(
    accessible_text: str,
    intent: Intent,
    retrieved_context: List[RetrievedSnippet],
    accessibility_report: AccessibilityReport,
    llm: LLMBackend,
    skill_output: Optional[str] = None,
) -> GroundedResponse:
    """
    FR-13: the single synthesis step of the whole pipeline -- everything
    upstream (ASR, disfluency cleanup, language/accent analysis, intent,
    RAG, and any domain skill invoked for FR-20) feeds into one grounded,
    plain-language answer instead of a raw templated string.
    """
    payload = {
        "accessible_transcript": accessible_text,
        "intent": {
            "goal": intent.goal,
            "action_type": intent.action_type,
            "entities": intent.entities,
        },
        "support_applied": accessibility_report.support_applied,
        "retrieved_context": [{"title": s.title, "content": s.content} for s in retrieved_context],
        "skill_output": skill_output,
    }
    raw = llm.complete(RESPONSE_SYSTEM_PROMPT, json.dumps(payload), task="response")
    return GroundedResponse(text=raw.strip(), used_context=[s.title for s in retrieved_context])
