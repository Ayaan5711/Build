"""
End-to-end smoke tests using mock backends only (no network, no model
weights, no mic/camera hardware). Verifies the plumbing across every PRD
pipeline stage. Swap backends to local/ollama/event for real runs; this
suite intentionally stays on mock so it always passes offline.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.analysis.accent_noise import analyze_accent_noise_confidence
from src.analysis.disfluency import detect_stammering
from src.analysis.language import detect_language_mix
from src.input.merge import merge_inputs
from src.input.microphone import MockASRBackend, Transcript
from src.input.vision import GestureResult, MockVisionBackend
from src.knowledge.personalization import UserMemory
from src.knowledge.rag import KnowledgeBase, seed_default_knowledge_base
from src.llm import get_llm_backend
from src.integrations import reminders_store
from src.pipeline import run_pipeline
from src.skills import get_skills
from src.understanding import dialogue_state
from src.understanding.simplify import needs_simplification, simplify_instructions


def test_full_pipeline_via_text_override(tmp_path):
    result = run_pipeline(text_override="B-b-b-book appointment tomorrow", user_id=f"test-{tmp_path.name}")
    assert "Book appointment tomorrow" in result.accessible_transcript.text or "book appointment tomorrow" in result.accessible_transcript.text.lower()
    assert result.disfluency_report.has_disfluency
    assert "speech_impairment" in result.accessibility_report.barriers_detected
    assert result.final_response.text
    assert result.recovery_options is not None


def test_guided_reminder_dialogue_paces_across_three_real_turns(tmp_path, monkeypatch):
    """End-to-end for the "Simplified Voice Interaction for Users with
    Cognitive Challenges" problem statement: setting a reminder is
    genuinely paced -- one plain question at a time across three separate
    run_pipeline() calls (each standing in for a separate /api/run request
    a real user would make) -- not a single-shot "give me everything at
    once" utterance. Also proves the reminder is really persisted, not
    just claimed."""
    monkeypatch.setattr(reminders_store, "_DB_PATH", str(tmp_path / "reminders.db"))
    user_id = f"guided-{tmp_path.name}"
    dialogue_state.reset_all()
    try:
        turn1 = run_pipeline(text_override="B-b-b-book appointment tomorrow", user_id=user_id)
        assert turn1.agent_result.clarification == "What should I remind you about?"
        assert turn1.final_response.text == "What should I remind you about?"
        assert "confirm" not in turn1.recovery_options.options

        turn2 = run_pipeline(text_override="calling the dentist", user_id=user_id)
        assert turn2.agent_result.clarification == "When should I remind you? For example, 'tomorrow at 5pm'."
        assert "confirm" not in turn2.recovery_options.options

        turn3 = run_pipeline(text_override="tomorrow at 3pm", user_id=user_id)
        assert turn3.agent_result.clarification is None
        assert "calling the dentist" in turn3.final_response.text
        assert "tomorrow at 3pm" in turn3.final_response.text
        assert turn3.agent_result.skills_used == ["schedule_reminder"]
        assert "confirm" in turn3.recovery_options.options

        saved = reminders_store.list_reminders(user_id)
        assert len(saved) == 1
        assert saved[0].subject == "calling the dentist"
        assert saved[0].time == "tomorrow at 3pm"
    finally:
        dialogue_state.clear_pending_task(user_id)


def test_guided_dialogue_is_isolated_per_user(tmp_path, monkeypatch):
    """Two different users mid-reminder-setup at the same time must not
    cross-talk -- server.py currently uses one shared user_id for the
    whole demo, but the underlying mechanism itself must still be
    per-user-correct."""
    monkeypatch.setattr(reminders_store, "_DB_PATH", str(tmp_path / "reminders.db"))
    user_a, user_b = f"a-{tmp_path.name}", f"b-{tmp_path.name}"
    dialogue_state.reset_all()
    try:
        run_pipeline(text_override="book appointment", user_id=user_a)
        run_pipeline(text_override="book appointment", user_id=user_b)
        assert dialogue_state.get_pending_task(user_a).asked_slot == "subject"
        assert dialogue_state.get_pending_task(user_b).asked_slot == "subject"

        run_pipeline(text_override="user a's subject", user_id=user_a)
        # user_b's pending task must be untouched by user_a's turn -- still
        # waiting on "subject", never received user a's answer.
        assert dialogue_state.get_pending_task(user_b).asked_slot == "subject"
        assert "subject" not in dialogue_state.get_pending_task(user_b).filled_slots
        assert dialogue_state.get_pending_task(user_a).filled_slots.get("subject") == "user a's subject"
    finally:
        dialogue_state.clear_pending_task(user_a)
        dialogue_state.clear_pending_task(user_b)


def test_mock_asr_known_fixture_still_works(tmp_path):
    """The sample fixture (data/sample_audio/example1.wav -> example1.txt)
    must keep working normally -- this fix only changes behavior for real
    recordings that have no matching fixture."""
    fixture_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "sample_audio", "example1.wav"
    )
    result = MockASRBackend().transcribe(fixture_path)
    assert "book" in result.text.lower()
    assert result.confidence == 0.75


def test_mock_asr_real_recording_gives_honest_placeholder_not_a_crash(tmp_path):
    """A real recorded/uploaded clip (e.g. a browser mic recording saved to
    a random temp path) has no matching .txt fixture. This must NOT raise
    (which used to trigger the NFR-03 cached-scenario fallback and show an
    unrelated canned demo response regardless of what was actually said --
    a real bug found via live testing) -- it must return a clear message
    telling the user to switch ASR_BACKEND."""
    fake_path = os.path.join(str(tmp_path), "some_random_recording_12345.wav")
    with open(fake_path, "wb") as f:
        f.write(b"not a real wav, just a stand-in for a browser recording")
    result = MockASRBackend().transcribe(fake_path)
    assert "mock ASR" in result.text
    assert "ASR_BACKEND" in result.text
    assert result.confidence == 0.0


def test_pipeline_records_per_stage_timings(tmp_path):
    result = run_pipeline(text_override="Book a meeting", user_id=f"test-timing-{tmp_path.name}")
    assert result.total_ms >= 0
    assert result.timings_ms  # non-empty
    # Every timed stage should be present and non-negative.
    for stage, ms in result.timings_ms.items():
        assert ms >= 0, f"{stage} had negative timing"
    assert "final response (response LLM)" in result.timings_ms


def test_detect_stammering_flags_repeated_syllables():
    ctx = merge_inputs(transcript=Transcript(text="Call Ka-ka-ka-Kiran", confidence=0.9))
    report = detect_stammering(ctx)
    assert report.has_disfluency
    assert report.repeated_syllables


def test_detect_stammering_clean_input_has_no_disfluency():
    ctx = merge_inputs(transcript=Transcript(text="Book a meeting at five", confidence=0.9))
    report = detect_stammering(ctx)
    assert not report.has_disfluency


def test_detect_language_mix_flags_code_switching():
    ctx = merge_inputs(transcript=Transcript(text="Kal meeting ache at 5 PM", confidence=0.9))
    report = detect_language_mix(ctx)
    assert report.code_mixed
    assert "bn" in report.languages_detected


def test_detect_language_mix_english_only():
    ctx = merge_inputs(transcript=Transcript(text="Book a meeting tomorrow", confidence=0.9))
    report = detect_language_mix(ctx)
    assert not report.code_mixed
    assert report.languages_detected == ["en"]


def test_accent_noise_low_confidence_triggers_clarifying_question():
    ctx = merge_inputs(transcript=Transcript(text="eleven", confidence=0.3))
    llm = get_llm_backend("reasoning")
    report = analyze_accent_noise_confidence(ctx, llm=llm)
    assert report.is_low_confidence
    assert report.clarifying_question == "Did you mean floor 11?"


def test_accent_noise_high_confidence_no_clarification_needed():
    ctx = merge_inputs(transcript=Transcript(text="Book a meeting", confidence=0.95))
    report = analyze_accent_noise_confidence(ctx, llm=get_llm_backend("reasoning"))
    assert not report.is_low_confidence
    assert report.clarifying_question is None


def test_needs_simplification_flags_long_ivr_instruction():
    long_text = "press one then go to three then enter your account number then confirm your identity please"
    assert needs_simplification(long_text)
    short_text = "book a meeting"
    assert not needs_simplification(short_text)


def test_simplify_instructions_breaks_into_steps():
    llm = get_llm_backend("cleanup")
    long_text = "press one then go to three then enter your account number then confirm your identity please"
    result = simplify_instructions(long_text, llm)
    assert result.was_simplified
    assert len(result.steps) > 1


def test_gesture_mock_backend_maps_to_candidate_intent():
    backend = MockVisionBackend()
    result_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "sample_gestures", "thumbs_up.json"
    )
    gesture_result = backend.interpret(result_path)
    assert gesture_result.gesture == "thumbs_up"
    assert gesture_result.candidate_intent == "confirm"


def test_gesture_mock_backend_real_capture_gives_no_gesture_not_a_crash(tmp_path):
    """A real captured frame (e.g. a browser camera snapshot saved to a
    random temp path) has no matching .json fixture. This must NOT raise
    (which used to trigger the NFR-03 cached-scenario fallback and show an
    unrelated canned demo response regardless of the actual gesture -- the
    same failure shape the mock ASR backend had, found via live browser
    testing of the redesigned frontend's gesture path) -- it must honestly
    report no gesture detected instead."""
    fake_path = os.path.join(str(tmp_path), "some_random_capture_12345.jpg")
    with open(fake_path, "wb") as f:
        f.write(b"not a real jpeg, just a stand-in for a browser camera capture")
    result = MockVisionBackend().interpret(fake_path)
    assert result.gesture is None
    assert result.confidence == 0.0
    assert result.candidate_intent is None


def test_merge_inputs_prefers_voice_but_carries_sign():
    transcript = Transcript(text="confirm", confidence=0.9)
    sign = GestureResult(gesture="thumbs_up", confidence=0.8, candidate_intent="confirm")
    ctx = merge_inputs(transcript=transcript, sign_result=sign)
    assert ctx.modality == "voice+sign"
    assert ctx.sign_result.gesture == "thumbs_up"


def test_merge_inputs_sign_only():
    sign = GestureResult(gesture="open_palm", confidence=0.8, candidate_intent="request_help")
    ctx = merge_inputs(transcript=None, sign_result=sign)
    assert ctx.modality == "sign"
    assert ctx.text == "request_help"


def test_rag_retrieval_finds_pas901_content(tmp_path):
    kb = KnowledgeBase(collection_name=f"test_kb_{tmp_path.name}")
    seed_default_knowledge_base(kb)
    results = kb.retrieve("what is PAS 901", k=1)
    assert results
    assert "PAS 901" in results[0].content or "PAS" in results[0].source


def test_personalization_correction_applied(tmp_path):
    from src.transcript.normalize import normalize_transcript

    memory = UserMemory(user_id=f"test-personalize-{tmp_path.name}")
    memory.add_correction("Ka-ka-Kiran", "Kiran")
    known = memory.get_known_corrections()
    llm = get_llm_backend("cleanup")
    result = normalize_transcript("Call Ka-ka-Kiran", llm, known_corrections=known)
    assert "Kiran" in result.text
    assert "Ka-ka-Kiran" not in result.text


def test_skill_registry_discovers_all_skills():
    skills = get_skills()
    assert "faq_lookup" in skills
    assert "schedule_reminder" in skills
    assert "general_help" in skills


def test_new_skill_can_be_added_without_touching_orchestrator():
    """Proves the FR-20 extensibility claim: a new match-day domain skill
    is one new file, zero changes to the pipeline/orchestrator."""
    new_skill_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src", "skills", "_temp_demo_skill.py"
    )
    with open(new_skill_path, "w") as f:
        f.write(
            "from src.skills.base import Skill, SkillResult\n\n"
            "class TempDemoSkill(Skill):\n"
            "    name = 'temp_demo'\n"
            "    description = 'temporary skill for the extensibility test'\n"
            "    keywords = ['banana']\n"
            "    def run(self, params, ctx):\n"
            "        return SkillResult(True, 'temp demo ran', {})\n"
        )
    try:
        import src.skills as skills_pkg

        skills_pkg._registry.clear()
        skills = get_skills()
        assert "temp_demo" in skills
    finally:
        os.remove(new_skill_path)
        import src.skills as skills_pkg

        skills_pkg._registry.clear()


def test_cached_fallback_scenario_used_when_pipeline_fails(monkeypatch):
    """NFR-03: if a live backend call blows up, the pipeline must fall back
    to a cached demo scenario instead of crashing the whole app."""
    import src.pipeline as pipeline_module

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated genailab.tcs.in outage")

    monkeypatch.setattr(pipeline_module, "_run_pipeline_live", _boom)
    result = run_pipeline(text_override="B-b-b-book appointment tomorrow")
    assert result.used_fallback_cache
    assert "Book appointment tomorrow" in result.accessible_transcript.text


def test_pipeline_raises_when_fallback_disabled(monkeypatch):
    import src.pipeline as pipeline_module

    monkeypatch.setattr(pipeline_module.config, "FALLBACK_TO_CACHED_SCENARIOS", False)

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated outage")

    monkeypatch.setattr(pipeline_module, "_run_pipeline_live", _boom)
    try:
        run_pipeline(text_override="hello")
        assert False, "expected RuntimeError to propagate when fallback disabled"
    except RuntimeError:
        pass
