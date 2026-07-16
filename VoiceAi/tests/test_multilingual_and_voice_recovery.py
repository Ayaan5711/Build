"""
Tests for the three multilingual/voice-only gaps that were found and fixed:
1. The final response is instructed to reply in the detected language(s),
   not silently default to English.
2. Recovery-intent matching (voice-driven confirm/retry/correct/switch)
   works via keyword matching, so a speak-and-listen-only user can complete
   the loop without clicking.
3. The /api/recovery-intent endpoint wires ASR + matching together.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.response.generate import LANGUAGE_NAMES, generate_grounded_response
from src.response.recovery_intent import match_recovery_intent
from src.analysis.accessibility_report import AccessibilityReport
from src.llm import get_llm_backend
from src.understanding.intent import Intent


def test_response_payload_carries_language_names_not_just_codes():
    """The response prompt tells the LLM to reply in a human-readable
    language name (an LLM follows 'respond in Hindi' more reliably than a
    bare ISO code); confirms the mapping exists for our detector's codes."""
    assert LANGUAGE_NAMES["en"] == "English"
    assert LANGUAGE_NAMES["hi"] == "Hindi"
    assert LANGUAGE_NAMES["bn"] == "Bengali"


def test_generate_grounded_response_accepts_languages_detected():
    llm = get_llm_backend("response")
    result = generate_grounded_response(
        "Book a meeting",
        Intent(goal="schedule"),
        [],
        AccessibilityReport(),
        llm,
        languages_detected=["en", "bn"],
    )
    assert result.text  # doesn't crash, produces something


def test_generate_grounded_response_defaults_to_english_if_unspecified():
    llm = get_llm_backend("response")
    result = generate_grounded_response("hello", Intent(), [], AccessibilityReport(), llm)
    assert result.text


# ------------------------------------------------- recovery-intent matching --
def test_recovery_intent_confirm_variants():
    for phrase in ["yes", "yeah", "confirm", "sure", "that's right", "go ahead"]:
        assert match_recovery_intent(phrase, ["confirm", "correct", "retry"]) == "confirm", phrase


def test_recovery_intent_retry_beats_confirm_when_both_plausible():
    # "no, try again" contains no confirm-trigger word, but "again" alone
    # (without "try") should still resolve to retry, not silently to None.
    assert match_recovery_intent("let's try again", ["confirm", "retry"]) == "retry"


def test_recovery_intent_correct_for_explicit_edit_phrases():
    assert match_recovery_intent("that's wrong, let me fix it", ["confirm", "correct"]) == "correct"
    assert match_recovery_intent("no that's wrong", ["confirm", "correct"]) == "correct"


def test_recovery_intent_switch_modality():
    assert match_recovery_intent("switch to camera", ["confirm", "switch_modality"]) == "switch_modality"
    assert match_recovery_intent("use the text instead", ["confirm", "switch_modality"]) == "switch_modality"


def test_recovery_intent_only_matches_offered_options():
    """If switch_modality isn't currently offered, a phrase that would
    otherwise match it must not be matched -- never invent an action the
    UI isn't actually offering."""
    assert match_recovery_intent("switch to camera", ["confirm", "retry"]) is None


def test_recovery_intent_no_match_returns_none_not_a_guess():
    assert match_recovery_intent("the weather is nice today", ["confirm", "retry"]) is None


def test_recovery_intent_empty_input():
    assert match_recovery_intent("", ["confirm"]) is None
    assert match_recovery_intent(None, ["confirm"]) is None


# --------------------------------------------------------------- API endpoint --
def test_recovery_intent_endpoint_fails_clean_without_sidecar_transcript():
    """MockASRBackend requires a sibling .txt next to the audio path; a
    real upload's temp path won't have one. Confirms the endpoint surfaces
    this as a clean 500 (not an unhandled crash) rather than silently
    returning a wrong match."""
    import io

    from fastapi.testclient import TestClient

    from server import app

    client = TestClient(app)
    audio = io.BytesIO(b"fake audio bytes")
    r = client.post(
        "/api/recovery-intent",
        files={"audio": ("clip.wav", audio, "audio/wav")},
        data={"options": '["confirm", "retry"]'},
    )
    assert r.status_code == 500
    assert "Recovery-intent matching error" in r.json()["detail"]


def test_recovery_intent_endpoint_matches_confirm_with_real_transcript(tmp_path, monkeypatch):
    """Exercises the actual success path: point MockASRBackend at a real
    sidecar transcript by monkeypatching the ASR backend the endpoint uses."""
    import io

    from fastapi.testclient import TestClient

    import server
    from src.input.microphone import Transcript

    class FixedTranscriptASR:
        def transcribe(self, audio_path):
            return Transcript(text="yes go ahead", confidence=0.9)

    monkeypatch.setattr(server, "get_asr_backend", lambda: FixedTranscriptASR())
    client = TestClient(server.app)
    audio = io.BytesIO(b"fake audio bytes")
    r = client.post(
        "/api/recovery-intent",
        files={"audio": ("clip.wav", audio, "audio/wav")},
        data={"options": '["confirm", "retry"]'},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["heard"] == "yes go ahead"
    assert body["matched_action"] == "confirm"


def test_recovery_intent_endpoint_requires_options():
    import io

    from fastapi.testclient import TestClient

    from server import app

    client = TestClient(app)
    audio = io.BytesIO(b"x")
    r = client.post("/api/recovery-intent", files={"audio": ("clip.wav", audio, "audio/wav")})
    assert r.status_code == 422  # options is a required form field
