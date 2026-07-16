import streamlit as st

from src import config
from src.knowledge.personalization import UserMemory
from src.knowledge.rag import KnowledgeBase, seed_default_knowledge_base
from src.pipeline import run_pipeline

st.set_page_config(page_title="TCS iON Voice AI", layout="wide")
st.title("TCS iON Voice AI -- AI for Every Voice")
st.caption(
    f"ASR: {config.ASR_BACKEND} · Vision: {config.VISION_BACKEND} · LLM: {config.LLM_BACKEND} · "
    f"Embed: {config.EMBED_BACKEND}"
)

with st.expander("Privacy note", expanded=False):
    st.write(
        "No raw audio or video is stored beyond what's needed to produce a transcript or gesture "
        "interpretation for this session. Accessibility analysis is supportive, not a diagnosis. "
        "Nothing is acted on without your confirmation."
    )

user_memory = UserMemory(user_id="demo-user")
kb = KnowledgeBase()
if kb.collection.count() == 0:
    seed_default_knowledge_base(kb)

# --- Screen 1: choose modality ---------------------------------------------
st.header("1. Choose how to interact")
mode = st.radio(
    "Input modality (Multimodal Fallback, FR-15)",
    ["Start Listening", "Start Camera", "Type instead (dev/testing)"],
    horizontal=True,
)

with st.expander("Personalize (optional) -- teach it a word/name it keeps mishearing"):
    known = user_memory.get_known_corrections()
    if known:
        st.caption("Currently remembered: " + ", ".join(f"{k} -> {v}" for k, v in known.items()))
    col1, col2 = st.columns(2)
    wrong_word = col1.text_input("Mishears it as", key="wrong_word")
    right_word = col2.text_input("Correct version", key="right_word")
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

run_clicked = st.button("Run", type="primary", disabled=not (audio_path or image_path or text_override))

if run_clicked:
    with st.spinner("Processing..."):
        result = run_pipeline(audio_path=audio_path, image_path=image_path, text_override=text_override)

    if result.used_fallback_cache:
        st.warning(f"FALLBACK MODE: {result.fallback_reason}")

    # --- Screens 3-4: original + accessible transcript ---------------------
    st.header("2-4. What was heard / understood")
    col1, col2 = st.columns(2)
    col1.text_area("Original input", result.original_input.text, height=80)
    col2.text_area("Accessible transcript", result.accessible_transcript.text, height=80)
    st.caption(f"Modality: {result.original_input.modality} · Confidence: {result.original_input.confidence:.0%}")
    if result.accent_noise_report.clarifying_question:
        st.info(f"Clarifying question: {result.accent_noise_report.clarifying_question}")

    # --- Screen 5-6: accessibility barrier + support applied ----------------
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

    if result.simplified_steps.was_simplified:
        st.subheader("Step-by-step (cognitive load reduction)")
        for i, step in enumerate(result.simplified_steps.steps, 1):
            st.markdown(f"{i}. {step}")

    # --- Screen 7: intent -----------------------------------------------------
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

    # --- Screen 8: RAG context -------------------------------------------------
    with st.expander(f"View Retrieved Context ({len(result.retrieved_context)} snippets)"):
        for snippet in result.retrieved_context:
            st.markdown(f"**{snippet.title}** ({snippet.source})")
            st.write(snippet.content)

    if result.skill_result:
        st.caption(f"Domain skill invoked: {result.skill_result.output}")

    # --- Screen 9: action preview + confirmation --------------------------------
    st.header("9. Action preview & confirmation")
    st.info(result.visual_equivalent.action_preview)
    st.caption(f"Caption: {result.visual_equivalent.caption}")

    st.subheader("Final response")
    st.success(result.final_response.text)

    # --- Screen 10: recovery options -----------------------------------------------
    st.header("10. Confirm or recover")
    cols = st.columns(len(result.recovery_options.options))
    for col, option in zip(cols, result.recovery_options.options):
        label = {"confirm": "Confirm", "correct": "Correct", "retry": "Retry", "switch_modality": "Switch Modality"}.get(
            option, option
        )
        col.button(label, key=f"recovery_{option}")
    if result.recovery_options.needs_confirmation:
        st.caption(f"Confirmation requested: {result.recovery_options.reason}")

st.divider()
st.caption("TCS iON Voice AI -- every voice, every context, every user.")
