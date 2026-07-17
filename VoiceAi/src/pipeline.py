import json
import os
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Optional

from src import config
from src.agent.agent import AgentResult, AgentStep, run_agent
from src.analysis.accent_noise import AccentNoiseReport, analyze_accent_noise_confidence
from src.analysis.accessibility_report import AccessibilityReport, analyze_accessibility
from src.analysis.disfluency import DisfluencyReport, detect_stammering
from src.analysis.language import LanguageReport, detect_language_mix
from src.input.merge import InputContext, merge_inputs
from src.input.microphone import get_asr_backend
from src.input.vision import get_vision_backend
from src.knowledge.personalization import UserMemory
from src.knowledge.rag import KnowledgeBase, RetrievedSnippet, rag_retrieve, seed_default_knowledge_base
from src.llm import get_llm_backend
from src.response.generate import GroundedResponse, generate_grounded_response
from src.response.recovery import RecoveryDecision, decide_recovery_or_confirmation
from src.transcript.normalize import AccessibleTranscript, normalize_transcript
from src.transcript.visual_equivalent import VisualEquivalent, generate_caption_summary_action_preview
from src.understanding import dialogue_state
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
    agent_result: AgentResult
    final_response: GroundedResponse
    recovery_options: RecoveryDecision
    used_fallback_cache: bool = False
    fallback_reason: str = ""
    # Per-stage wall-clock timings in milliseconds -- so you can MEASURE
    # latency on the actual (possibly slow) lab laptop per backend, instead
    # of guessing whether local models are fast enough for a live demo.
    timings_ms: dict = field(default_factory=dict)
    total_ms: float = 0.0


@contextmanager
def _stage(timings: dict, name: str):
    start = time.perf_counter()
    try:
        yield
    finally:
        timings[name] = round((time.perf_counter() - start) * 1000, 1)


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
    timings = {}
    pipeline_start = time.perf_counter()

    asr = get_asr_backend()
    vision = get_vision_backend()
    user_memory = UserMemory(user_id)
    kb = KnowledgeBase()
    # Self-seed the RAG knowledge base so retrieval works when the pipeline
    # runs outside the app (notebook, tests, direct calls), not only after
    # the UI happened to seed it.
    if kb.collection.count() == 0:
        seed_default_knowledge_base(kb)
    ctx = {"knowledge_base": kb, "user_memory": user_memory}
    # Whether this turn is answering a question from an in-progress guided
    # dialogue (see src/understanding/dialogue_state.py) -- if so, intent
    # extraction and RAG retrieval below are skipped: the agent isn't going
    # to re-plan from scratch, it's just filling the next slot, so those
    # LLM calls would be pure wasted cost/latency on a flow that's already
    # multi-turn by nature.
    continuing_dialogue = bool(dialogue_state.get_pending_task(user_id))

    with _stage(timings, "asr"):
        if text_override is not None:
            from src.input.microphone import Transcript

            transcript = Transcript(text=text_override, confidence=1.0)
        elif audio_path:
            transcript = asr.transcribe(audio_path)
        else:
            transcript = None

    with _stage(timings, "vision"):
        sign_result = vision.interpret(image_path) if image_path else None
    input_context = merge_inputs(transcript=transcript, sign_result=sign_result)

    with _stage(timings, "language+disfluency (rule-based)"):
        language_report = detect_language_mix(input_context)
        disfluency_report = detect_stammering(input_context)

    reasoning_llm = get_llm_backend("reasoning")
    with _stage(timings, "accent/noise"):
        accent_noise_report = analyze_accent_noise_confidence(input_context, llm=reasoning_llm)

    cleanup_llm = get_llm_backend("cleanup")
    known_corrections = user_memory.get_known_corrections()
    with _stage(timings, "normalize (cleanup LLM)"):
        accessible_transcript = normalize_transcript(input_context.text, cleanup_llm, known_corrections=known_corrections)

    caption_llm = get_llm_backend("caption")
    with _stage(timings, "caption LLM"):
        visual_equivalent = generate_caption_summary_action_preview(accessible_transcript.text, caption_llm)

    with _stage(timings, "accessibility report (reasoning LLM)"):
        accessibility_report = analyze_accessibility(
            disfluency_report, language_report, accent_noise_report, sign_result, reasoning_llm
        )

    with _stage(timings, "simplify"):
        simplified_steps = simplify_instructions(accessible_transcript.text, cleanup_llm)

    intent_llm = get_llm_backend("intent")
    with _stage(timings, "intent LLM"):
        if continuing_dialogue:
            intent = Intent(goal="continuing_guided_dialogue", action_type="dialogue_continuation")
        else:
            intent = extract_intent(accessible_transcript.text, sign_result, intent_llm)

    with _stage(timings, "RAG retrieval"):
        retrieved_context = [] if continuing_dialogue else rag_retrieve(accessible_transcript.text, kb, k=3)

    with _stage(timings, "agent loop (plan->tool->observe)"):
        agent_result = run_agent(
            accessible_transcript.text,
            intent,
            retrieved_context,
            ctx,
            get_llm_backend("intent"),
            max_steps=config.AGENT_MAX_STEPS,
        )

    response_llm = get_llm_backend("response")
    with _stage(timings, "final response (response LLM)"):
        if agent_result.clarification:
            # A paced guided-dialogue turn: the response IS the next
            # question, verbatim -- skip LLM synthesis so it can't be
            # paraphrased into something longer or vaguer, which would
            # defeat the entire point of pacing one plain question at a
            # time (also saves an LLM call/cost on what's already a
            # multi-turn flow).
            final_response = GroundedResponse(text=agent_result.clarification, used_context=[])
        else:
            final_response = generate_grounded_response(
                accessible_transcript.text,
                intent,
                retrieved_context,
                accessibility_report,
                response_llm,
                skill_output=agent_result.combined_output or None,
                languages_detected=language_report.languages_detected,
            )

    with _stage(timings, "recovery decision (reasoning LLM)"):
        recovery_options = decide_recovery_or_confirmation(
            input_context.confidence, intent.missing_information, accessibility_report, reasoning_llm
        )
        # If the agent itself decided it needs to ask the user something,
        # that forces confirmation regardless of the confidence heuristic.
        if agent_result.clarification:
            recovery_options.needs_confirmation = True
            if "correct" not in recovery_options.options:
                recovery_options.options = list(recovery_options.options) + ["correct"]
            recovery_options.reason = f"agent needs clarification: {agent_result.clarification}"
            # Mid guided-dialogue there's nothing to "confirm" yet -- the
            # response is a question, not a proposed action -- so offering
            # a Confirm button here would be confusing. Correct/Retry/
            # Switch Modality all still make sense (answer differently,
            # re-record, or switch how you're answering).
            if dialogue_state.get_pending_task(user_id) and "confirm" in recovery_options.options:
                recovery_options.options = [o for o in recovery_options.options if o != "confirm"]

    total_ms = round((time.perf_counter() - pipeline_start) * 1000, 1)
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
        agent_result=agent_result,
        final_response=final_response,
        recovery_options=recovery_options,
        timings_ms=timings,
        total_ms=total_ms,
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
        agent_result=AgentResult(
            answer=out["final_response"],
            skill_outputs=[out["final_response"]],
            steps=[
                AgentStep(
                    step=1,
                    thought="cached scenario (offline fallback) -- no live agent run",
                    action="finish",
                    observation=out["final_response"],
                )
            ],
        ),
        final_response=GroundedResponse(text=out["final_response"], used_context=[]),
        recovery_options=RecoveryDecision(
            needs_confirmation=out["needs_confirmation"], options=out["recovery_options"], reason=out["recovery_reason"]
        ),
    )
