import json
from dataclasses import dataclass

from src.llm import LLMBackend

CAPTION_SYSTEM_PROMPT = (
    "You generate visual equivalents for spoken/AI-generated content, for users "
    "who cannot rely on voice-only output (FR-17). Given an accessible transcript, "
    "produce: a short caption (verbatim-ish, for live captioning), a one-line "
    "summary, and a plain-language preview of the action about to be taken. "
    'Respond ONLY with JSON: {"caption": <string>, "summary": <string>, '
    '"action_preview": <string>}.'
)


@dataclass
class VisualEquivalent:
    caption: str
    summary: str
    action_preview: str


def generate_caption_summary_action_preview(accessible_text: str, llm: LLMBackend) -> VisualEquivalent:
    """FR-17: every voice output/interaction gets a visual equivalent --
    caption, summary, and action preview -- so hearing-impaired users, or
    anyone in a situation where audio isn't practical, aren't excluded."""
    raw = llm.complete(CAPTION_SYSTEM_PROMPT, accessible_text, task="caption")
    data = json.loads(raw)
    return VisualEquivalent(
        caption=data.get("caption", accessible_text),
        summary=data.get("summary", accessible_text),
        action_preview=data.get("action_preview", f"About to act on: {accessible_text}"),
    )
