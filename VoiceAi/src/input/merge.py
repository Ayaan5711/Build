from dataclasses import dataclass
from typing import Optional

from src.input.microphone import Transcript
from src.input.vision import GestureResult


@dataclass
class InputContext:
    """Unified view of whatever modality(ies) the user actually used this
    turn (FR-15, Multimodal Fallback) -- voice, sign/gesture, or both."""

    text: str
    confidence: float
    transcript: Optional[Transcript]
    sign_result: Optional[GestureResult]
    modality: str  # "voice" | "sign" | "voice+sign" | "text"


def merge_inputs(transcript: Optional[Transcript] = None, sign_result: Optional[GestureResult] = None) -> InputContext:
    if transcript and sign_result and sign_result.gesture:
        # Both present: sign confirms/qualifies the spoken utterance --
        # surface both, text stays the transcript (primary channel), the
        # gesture's candidate_intent is carried through in sign_result for
        # downstream intent extraction to consider.
        return InputContext(
            text=transcript.text,
            confidence=min(transcript.confidence, sign_result.confidence),
            transcript=transcript,
            sign_result=sign_result,
            modality="voice+sign",
        )
    if transcript:
        return InputContext(
            text=transcript.text,
            confidence=transcript.confidence,
            transcript=transcript,
            sign_result=None,
            modality="voice",
        )
    if sign_result and sign_result.gesture:
        return InputContext(
            text=sign_result.candidate_intent or sign_result.gesture,
            confidence=sign_result.confidence,
            transcript=None,
            sign_result=sign_result,
            modality="sign",
        )
    return InputContext(text="", confidence=0.0, transcript=None, sign_result=None, modality="none")
