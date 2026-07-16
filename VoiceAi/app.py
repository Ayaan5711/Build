import streamlit as st

from src import config
from src.cost import get_cost_tracker, reset_cost_tracker
from src.knowledge.personalization import UserMemory
from src.knowledge.rag import KnowledgeBase, seed_default_knowledge_base
from src.pipeline import run_pipeline

st.set_page_config(page_title="TCS iON Voice AI", layout="wide")
ss = st.session_state

user_memory = UserMemory(user_id="demo-user")
kb = KnowledgeBase()
if kb.collection.count() == 0:
    seed_default_knowledge_base(kb)

MODES = ["Start Listening", "Start Camera", "Type instead (dev/testing)"]
ss.setdefault("input_mode", MODES[0])
ss.setdefault("result", None)
ss.setdefault("last_inputs", {})
ss.setdefault("correcting", False)
ss.setdefault("confirmed", False)


def do_run(audio_path=None, image_path=None, text_override=None, correction=None):
    """Central pipeline runner. `correction` re-runs on user-edited text and
    remembers it (personalization) so the same mishearing is auto-fixed next
    time -- this is what makes the Correct/Retry recovery buttons real."""
    if correction is not None and ss.result is not None:
        original = ss.result.original_input.text
        if original and correction.strip() and correction.strip() != original.strip():
            user_memory.add_correction(original, correction.strip())
        audio_path = image_path = None
        text_override = correction
    ss.result = run_pipeline(audio_path=audio_path, image_path=image_path, text_override=text_override)
    ss.last_inputs = {"audio_path": audio_path, "image_path": image_path, "text_override": text_override}
    ss.correcting = False
    ss.confirmed = False


def _confirm():
    ss.confirmed = True


def _retry():
    do_run(**ss.last_inputs)


def _correct():
    ss.correcting = True


def _switch_modality():
    ss.input_mode = MODES[(MODES.index(ss.input_mode) + 1) % len(MODES)]


def _apply_correction():
    do_run(correction=ss.get("correction_text", ""))


# --- Sidebar: cost & budget -------------------------------------------------
tracker = get_cost_tracker()
with st.sidebar:
    st.subheader("Cost & budget")
    st.metric("Estimated hosted spend", f"${tracker.total_usd:.4f}")
    st.progress(min(1.0, tracker.total_usd / config.BUDGET_USD_CAP) if config.BUDGET_USD_CAP else 0.0)
    st.caption(f"Cap ${config.BUDGET_USD_CAP:.2f} · Profile: **{config.PROFILE}**")
    if config.PROFILE in ("mock", "local"):
        st.caption("Fully local/offline -- $0 by design.")
    by_stage = tracker.summary_by_stage()
    if by_stage:
        st.write({k: f"${v:.4f}" for k, v in by_stage.items()})
    st.caption("Estimates for budgeting, not exact billing.")
    if st.button("Reset cost log"):
        reset_cost_tracker()
        st.rerun()

    # --- Latency: measure on the real laptop, don't guess -------------------
    if ss.get("result") is not None and ss.result.timings_ms:
        st.subheader("Latency (last run)")
        total = ss.result.total_ms
        st.metric("Total", f"{total/1000:.1f} s")
        if total > 12000:
            st.error("Slow for a live demo (>12s). Try PROFILE=fast (all hosted).")
        elif total > 6000:
            st.warning("A bit slow (>6s). PROFILE=fast will be snappier.")
        else:
            st.success("Snappy enough for a live demo.")
        slow_first = dict(sorted(ss.result.timings_ms.items(), key=lambda kv: -kv[1]))
        st.write({k: f"{v/1000:.2f} s" for k, v in slow_first.items()})

st.title("TCS iON Voice AI -- AI for Every Voice")
st.caption(
    f"ASR: {config.ASR_BACKEND} · Vision: {config.VISION_BACKEND} · Embed: {config.EMBED_BACKEND} · "
    f"Profile: {config.PROFILE}"
)

with st.expander("Privacy note", expanded=False):
    st.write(
        "No raw audio or video is stored beyond what's needed to produce a transcript or gesture "
        "interpretation for this session. Accessibility analysis is supportive, not a diagnosis. "
        "Nothing is acted on without your confirmation."
    )

# --- Screen 1: choose modality ---------------------------------------------
st.header("1. Choose how to interact")
mode = st.radio("Input modality (Multimodal Fallback, FR-15)", MODES, horizontal=True, key="input_mode")

with st.expander("Personalize (optional) -- teach it a word/name it keeps mishearing"):
    known = user_memory.get_known_corrections()
    if known:
        st.caption("Currently remembered: " + ", ".join(f"{k} -> {v}" for k, v in known.items()))
    c1, c2 = st.columns(2)
    wrong_word = c1.text_input("Mishears it as", key="wrong_word")
    right_word = c2.text_input("Correct version", key="right_word")
    if st.button("Save correction") and wrong_word and right_word:
        user_memory.add_correction(wrong_word, right_word)
        st.success(f"Saved: '{wrong_word}' -> '{right_word}'.")
        st.rerun()

audio_path = None
image_path = None
text_override = None

if mode == "Start Listening":
    mic_audio = st.audio_input("Recording... speak now")
    if mic_audio:
        audio_path = "captured_audio.wav"
        with open(audio_path, "wb") as f:
            f.write(mic_audio.read())
        st.success("Captured. Click Run below.")
elif mode == "Start Camera":
    st.caption("Predefined gestures: thumbs up = confirm, open palm = help, fist = correct/cancel, pointing = select, peace = switch modality.")
    camera_image = st.camera_input("Camera active -- show a gesture")
    if camera_image:
        image_path = "captured_gesture.jpg"
        with open(image_path, "wb") as f:
            f.write(camera_image.read())
        st.success("Captured. Click Run below.")
else:
    text_override = st.text_input(
        "Type what you'd say (stands in for speech/sign until live capture is verified):",
        "B-b-b-book appointment tomorrow",
    )

if st.button("Run", type="primary", disabled=not (audio_path or image_path or text_override)):
    with st.spinner("Processing..."):
        do_run(audio_path=audio_path, image_path=image_path, text_override=text_override)

# --- Render the latest result (persists across recovery-button reruns) ------
result = ss.result
if result:
    if result.used_fallback_cache:
        st.warning(f"FALLBACK MODE: {result.fallback_reason}")

    st.header("2-4. What was heard / understood")
    c1, c2 = st.columns(2)
    c1.text_area("Original input", result.original_input.text, height=80)
    c2.text_area("Accessible transcript", result.accessible_transcript.text, height=80)
    st.caption(f"Modality: {result.original_input.modality} · Confidence: {result.original_input.confidence:.0%}")
    if result.accent_noise_report.clarifying_question:
        st.info(f"Clarifying question: {result.accent_noise_report.clarifying_question}")

    st.header("5-6. Accessibility barrier & support applied")
    bcol, scol = st.columns(2)
    bcol.write("**Barriers detected:**")
    for b in result.accessibility_report.barriers_detected:
        bcol.markdown(f"- {b}")
    scol.write("**Support applied:**")
    for s in result.accessibility_report.support_applied:
        scol.markdown(f"- {s}")
    if result.language_report.code_mixed:
        st.caption(f"Languages detected: {', '.join(result.language_report.languages_detected)}")

    with st.expander("Detection evidence (raw detector output, not just the conclusion)"):
        d = result.disfluency_report
        st.write(f"Has disfluency: {d.has_disfluency}")
        if d.repeated_syllables:
            st.write(f"Repeated syllables: {', '.join(d.repeated_syllables)}")
        if d.repeated_words:
            st.write(f"Repeated words: {', '.join(d.repeated_words)}")
        if d.filler_words_found:
            st.write(f"Filler words: {', '.join(d.filler_words_found)}")
        if d.long_pause_markers:
            st.write(f"Long pause markers: {d.long_pause_markers}")
        if result.language_report.romanized_markers:
            st.write(f"Language markers: {', '.join(result.language_report.romanized_markers)}")

    if result.simplified_steps.was_simplified:
        st.subheader("Step-by-step (cognitive load reduction)")
        for i, step in enumerate(result.simplified_steps.steps, 1):
            st.markdown(f"{i}. {step}")

    st.header("7. Detected intent")
    st.json(
        {
            "goal": result.intent.goal,
            "action_type": result.intent.action_type,
            "entities": result.intent.entities,
            "constraints": result.intent.constraints,
            "urgency": result.intent.urgency,
            "missing_information": result.intent.missing_information,
        }
    )

    with st.expander(f"View Retrieved Context ({len(result.retrieved_context)} snippets)"):
        for snippet in result.retrieved_context:
            st.markdown(f"**{snippet.title}** ({snippet.source})")
            st.write(snippet.content)

    # --- Agent reasoning trace (the agentic flow, made visible) -------------
    st.header("8b. Agent reasoning trace")
    agent = result.agent_result
    st.caption(
        f"{len(agent.steps)} step(s) · tools used: {', '.join(agent.skills_used) or 'none'}"
        + (" · hit step cap" if agent.hit_max_steps else "")
    )
    for step in agent.steps:
        icon = {"call_skill": "🔧", "clarify": "❓", "finish": "✅"}.get(step.action, "•")
        with st.expander(f"{icon} Step {step.step}: {step.action}" + (f" → {step.skill}" if step.skill else "")):
            st.markdown(f"**Thought:** {step.thought}")
            if step.skill:
                st.markdown(f"**Tool:** `{step.skill}`  ·  **Params:** `{step.params}`")
            if step.observation:
                st.markdown(f"**Observation:** {step.observation}")
            if step.question:
                st.markdown(f"**Clarifying question:** {step.question}")
    if agent.clarification:
        st.info(f"Agent needs clarification: {agent.clarification}")

    st.header("9. Action preview & confirmation")
    st.info(result.visual_equivalent.action_preview)
    st.caption(f"Caption: {result.visual_equivalent.caption}")
    st.subheader("Final response")
    st.success(result.final_response.text)

    # --- Screen 10: recovery options (wired, not decorative) ----------------
    st.header("10. Confirm or recover")

    def _explain_why_review_needed(confidence_pct, barriers, fallback_reason):
        parts = []
        if confidence_pct < 60:
            parts.append(f"speech confidence was only {confidence_pct:.0f}% (often background noise, an accent, or unclear audio)")
        if "speech_impairment" in barriers:
            parts.append("a disfluency (repeated words/sounds) was detected and cleaned up")
        if "multilingual_code_mixing" in barriers:
            parts.append("mixed languages were detected")
        if "noise_or_accent_uncertainty" in barriers and confidence_pct >= 60:
            parts.append("the system wasn't fully certain it heard you correctly")
        if "sign_or_gesture_interaction" in barriers:
            parts.append("a gesture was interpreted, not spoken words")
        if not parts:
            parts.append(fallback_reason or "the system wants to double-check before acting")
        return "Why: " + "; ".join(parts) + "."

    if result.recovery_options.needs_confirmation:
        st.warning(
            "**Please review before continuing.** "
            + _explain_why_review_needed(
                result.original_input.confidence * 100,
                result.accessibility_report.barriers_detected,
                result.recovery_options.reason,
            )
        )
    else:
        st.success("This looks good -- click Confirm to proceed, or use another option if something's off.")

    labels = {"confirm": "Confirm", "correct": "Correct", "retry": "Retry", "switch_modality": "Switch Modality"}
    callbacks = {"confirm": _confirm, "correct": _correct, "retry": _retry, "switch_modality": _switch_modality}
    cols = st.columns(len(result.recovery_options.options))
    for col, option in zip(cols, result.recovery_options.options):
        col.button(labels.get(option, option), key=f"rec_{option}", on_click=callbacks.get(option))

    if ss.confirmed:
        st.success("Confirmed -- the action would now proceed.")
    if ss.correcting:
        st.text_input("Edit the transcript, then apply", value=result.accessible_transcript.text, key="correction_text")
        st.button("Apply correction & re-run", on_click=_apply_correction)

st.divider()
st.caption("TCS iON Voice AI -- every voice, every context, every user.")
