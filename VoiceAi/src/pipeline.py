import json
import os
from dataclasses import dataclass, field
from typing import Optional

from src import config
from src.analysis.accent_noise import AccentNoiseReport, analyze_accent_noise_confidence
from src.analysis.accessibility_report import AccessibilityReport, analyze_accessibility
from src.analysis.disfluency import DisfluencyReport, detect_stammering
from src.analysis.language import LanguageReport, detect_language_mix
from src.input.merge import InputContext, merge_inputs
from src.input.microphone import get_asr_backend
from src.input.vision import get_vision_backend
from src.knowledge.personalization import UserMemory
from src.knowledge.rag import KnowledgeBase, RetrievedSnippet, rag_retrieve
from src.llm import get_llm_backend
from src.response.generate import GroundedResponse, generate_grounded_response
from src.response.recovery import RecoveryDecision, decide_recovery_or_confirmation
from src.skills import get_skills, select_skill
from src.skills.base import SkillResult
from src.transcript.normalize import AccessibleTranscript, normalize_transcript
from src.transcript.visual_equivalent import VisualEquivalent, generate_caption_summary_action_preview
from src.understanding.intent import Intent, extract_intent
from src.understanding.simplify import SimplifiedSteps, simplify_instructions

_DEMO_SCENARIOS_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "demo_scenarios.json")


@dataclass
class PipelineResult:
    original_input: InputContext
    disfluency_report: DisfluencyReport
    language_report: LanguageReport
    accent_noise_report: AccentNoiseReport
    accessible_transcript: AccessibleTranscript
    visual_equivalent: VisualEquivalent
    accessibility_report: AccessibilityReport
    simplified_steps: SimplifiedSteps
    intent: Intent
    retrieved_context: list
    skill_result: Optional[SkillResult]
    final_response: GroundedResponse
    recovery_options: RecoveryDecision
    used_fallback_cache: bool = False
    fallback_reason: str = ""


def run_pipeline(
    audio_path: Optional[str] = None,
    image_path: Optional[str] = None,
    text_override: Optional[str] = None,
    user_id: str = "demo-user",
) -> PipelineResult:
    """
    Wires the full Appendix A pseudocode flow end to end. text_override
    lets the dev/text input mode (and the notebook) skip live ASR while
    still exercising every downstream stage.
    """
    try:
        return _run_pipeline_live(audio_path, image_path, text_override, user_id)
    except Exception as e:  # noqa: BLE001 -- deliberate: NFR-03 resilience
        if config.FALLBACK_TO_CACHED_SCENARIOS:
            fallback = _load_cached_scenario(text_override or "")
            if fallback:
                fallback.used_fallback_cache = True
                fallback.fallback_reason = f"Live pipeline failed ({e}); showing cached scenario output."
                return fallback
        raise


def _run_pipeline_live(
    audio_path: Optional[str],
    image_path: Optional[str],
    text_override: Optional[str],
    user_id: str,
) -> PipelineResult:
    asr = get_asr_backend()
    vision = get_vision_backend()
    user_memory = UserMemory(user_id)
    kb = KnowledgeBase()
    ctx = {"knowledge_base": kb, "user_memory": user_memory}

    if text_override is not None:
        from src.input.microphone import Transcript

        transcript = Transcript(text=text_override, confidence=1.0)
    elif audio_path:
        transcript = asr.transcribe(audio_path)
    else:
        transcript = None

    sign_result = vision.interpret(image_path) if image_path else None
    input_context = merge_inputs(transcript=transcript, sign_result=sign_result)

    language_report = detect_language_mix(input_context)
    disfluency_report = detect_stammering(input_context)

    reasoning_llm = get_llm_backend("reasoning")
    accent_noise_report = analyze_accent_noise_confidence(input_context, llm=reasoning_llm)

    cleanup_llm = get_llm_backend("cleanup")
    known_corrections = user_memory.get_known_corrections()
    accessible_transcript = normalize_transcript(input_context.text, cleanup_llm, known_corrections=known_corrections)

    caption_llm = get_llm_backend("caption")
    visual_equivalent = generate_caption_summary_action_preview(accessible_transcript.text, caption_llm)

    accessibility_report = analyze_accessibility(
        disfluency_report, language_report, accent_noise_report, sign_result, reasoning_llm
    )

    simplified_steps = simplify_instructions(accessible_transcript.text, cleanup_llm)

    intent_llm = get_llm_backend("intent")
    intent = extract_intent(accessible_transcript.text, sign_result, intent_llm)

    retrieved_context = rag_retrieve(accessible_transcript.text, kb, k=3)

    skill_result = None
    routing = select_skill(accessible_transcript.text, cleanup_llm)
    skill_name = routing.get("skill")
    if skill_name:
        skill = get_skills().get(skill_name)
        if skill:
            skill_result = skill.run(routing.get("params", {}), ctx)

    response_llm = get_llm_backend("response")
    final_response = generate_grounded_response(
        accessible_transcript.text,
        intent,
        retrieved_context,
        accessibility_report,
        response_llm,
        skill_output=skill_result.output if skill_result else None,
    )

    recovery_options = decide_recovery_or_confirmation(
        input_context.confidence, intent.missing_information, accessibility_report, reasoning_llm
    )

    return PipelineResult(
        original_input=input_context,
        disfluency_report=disfluency_report,
        language_report=language_report,
        accent_noise_report=accent_noise_report,
        accessible_transcript=accessible_transcript,
        visual_equivalent=visual_equivalent,
        accessibility_report=accessibility_report,
        simplified_steps=simplified_steps,
        intent=intent,
        retrieved_context=retrieved_context,
        skill_result=skill_result,
        final_response=final_response,
        recovery_options=recovery_options,
    )


def _load_cached_scenario(text: str) -> Optional[PipelineResult]:
    """NFR-03: if live backends fail entirely, fall back to a precomputed
    scenario output so the demo survives an API/network outage. Matches by
    simple keyword overlap against the 10 PRD demo samples."""
    if not os.path.exists(_DEMO_SCENARIOS_PATH):
        return None
    with open(_DEMO_SCENARIOS_PATH) as f:
        scenarios = json.load(f)

    text_lower = text.lower()
    best = None
    best_score = 0
    for scenario in scenarios:
        score = sum(1 for kw in scenario.get("match_keywords", []) if kw in text_lower)
        if score > best_score:
            best_score = score
            best = scenario
    if best is None and scenarios:
        best = scenarios[0]
    if best is None:
        return None

    return _scenario_to_result(best)


def _scenario_to_result(scenario: dict) -> PipelineResult:
    out = scenario["cached_output"]
    input_context = InputContext(
        text=out["original_text"], confidence=out["confidence"], transcript=None, sign_result=None, modality="voice"
    )
    return PipelineResult(
        original_input=input_context,
        disfluency_report=DisfluencyReport(has_disfluency=out["disfluency"]["has_disfluency"]),
        language_report=LanguageReport(
            languages_detected=out["languages_detected"], code_mixed=len(out["languages_detected"]) > 1
        ),
        accent_noise_report=AccentNoiseReport(
            confidence=out["confidence"],
            is_low_confidence=out["confidence"] < config.CONFIDENCE_THRESHOLD,
            clarifying_question=out.get("clarifying_question"),
        ),
        accessible_transcript=AccessibleTranscript(text=out["accessible_text"], corrections_made=True),
        visual_equivalent=VisualEquivalent(
            caption=out["accessible_text"], summary=out["accessible_text"], action_preview=out["action_preview"]
        ),
        accessibility_report=AccessibilityReport(
            barriers_detected=out["barriers_detected"], support_applied=out["support_applied"]
        ),
        simplified_steps=SimplifiedSteps(steps=out.get("steps", [out["accessible_text"]]), was_simplified=bool(out.get("steps"))),
        intent=Intent(goal=out["intent_goal"], action_type=out["intent_action_type"]),
        retrieved_context=[RetrievedSnippet(source="cached", title=out.get("retrieved_title", ""), content=out.get("retrieved_content", ""))]
        if out.get("retrieved_content")
        else [],
        skill_result=None,
        final_response=GroundedResponse(text=out["final_response"], used_context=[]),
        recovery_options=RecoveryDecision(
            needs_confirmation=out["needs_confirmation"], options=out["recovery_options"], reason=out["recovery_reason"]
        ),
    )
