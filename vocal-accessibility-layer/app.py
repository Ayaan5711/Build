import streamlit as st

from src import config
from src.agent.guardrail import check as guardrail_check
from src.agent.memory import Memory
from src.agent.orchestrator import orchestrate
from src.foundation.asr import get_asr_backend
from src.foundation.equalizer import equalize
from src.foundation.normalizer import normalize
from src.foundation.tts import get_tts_backend
from src.llm import get_llm_backend
from src.skills import get_skills
from src.transparency import TransparencyReport

st.set_page_config(page_title="Vocal Accessibility Layer")
st.title("Vocal Accessibility Layer")
st.caption(
    f"ASR: {config.ASR_BACKEND} · LLM: {config.LLM_BACKEND} · "
    f"Embed: {config.EMBED_BACKEND} · TTS: {config.TTS_BACKEND}"
)


def _init_backend(label, factory):
    try:
        return factory()
    except Exception as e:
        st.error(f"{label} backend failed to initialize: {e}")
        st.stop()


llm = _init_backend("LLM", get_llm_backend)
asr = _init_backend("ASR", get_asr_backend)
tts = _init_backend("TTS", get_tts_backend)
memory = Memory(user_id="demo-user")
memory.seed_faq(
    [
        {"question": "What time does the lab open?", "answer": "The Gen AI Lab opens at 9 AM."},
        {"question": "What is PAS 901?", "answer": "PAS 901:2025 is the Vocal Accessibility code of practice."},
    ]
)

with st.expander("Personalize (optional) -- teach it a word/name it keeps mishearing"):
    known = memory.get_known_corrections()
    if known:
        st.caption("Currently remembered: " + ", ".join(f"{k} -> {v}" for k, v in known.items()))
    col1, col2 = st.columns(2)
    wrong_word = col1.text_input("Mishears it as", key="wrong_word")
    right_word = col2.text_input("Correct version", key="right_word")
    if st.button("Save correction") and wrong_word and right_word:
        memory.add_correction(wrong_word, right_word)
        st.success(f"Saved: '{wrong_word}' -> '{right_word}'. It'll be applied automatically next time.")
        st.rerun()

mode = st.radio("Input mode", ["Microphone", "Audio file", "Text (dev)"], horizontal=True)

raw_text = None
asr_confidence = 1.0

if mode == "Microphone":
    mic_audio = st.audio_input("Record yourself speaking")
    if mic_audio:
        temp_path = "uploaded_audio.wav"
        with open(temp_path, "wb") as f:
            f.write(mic_audio.read())
        result = asr.transcribe(temp_path)
        raw_text = result.text
        asr_confidence = result.confidence
elif mode == "Audio file":
    uploaded = st.file_uploader("Upload a short audio clip", type=["wav", "mp3", "m4a"])
    if uploaded:
        temp_path = "uploaded_audio." + uploaded.name.rsplit(".", 1)[-1]
        with open(temp_path, "wb") as f:
            f.write(uploaded.read())
        result = asr.transcribe(temp_path)
        raw_text = result.text
        asr_confidence = result.confidence
else:
    raw_text = st.text_input(
        "Type an utterance (stands in for speech until real ASR is wired in):",
        "M-m-m-my na-name i-is So-soumesh, s-schedule a m-meeting at 5 PM",
    )

if raw_text and st.button("Run pipeline"):
    known_corrections = memory.get_known_corrections()

    with st.spinner("Running foundation layer..."):
        eq_result = equalize(raw_text, llm, known_corrections=known_corrections)
        norm_result = normalize(eq_result.clean_text, llm)

    st.subheader("Foundation layer")
    st.write("**Raw transcript:**", raw_text)
    st.write("**Cleaned (Speech Equalizer):**", eq_result.clean_text)
    st.write("**Detected intent / entities:**", norm_result.intent, norm_result.entities)

    with st.spinner("Routing to a skill..."):
        orch_result = orchestrate(norm_result.intent, norm_result.entities, norm_result.clean_text, llm)

    st.subheader("Agent layer")
    g_result = None
    response_text = None
    if orch_result.clarify and not orch_result.skill_name:
        st.warning(f"Clarifying question: {orch_result.clarify}")
        response_text = orch_result.clarify
    elif orch_result.skill_name:
        skills = get_skills()
        skill = skills.get(orch_result.skill_name)
        if skill:
            with st.spinner("Checking guardrail..."):
                g_result = guardrail_check(asr_confidence, f"{skill.name}({orch_result.params})", llm)
            if g_result.approved:
                skill_result = skill.run(orch_result.params, memory)
                st.success(skill_result.output)
                response_text = skill_result.output
            else:
                st.warning(f"Guardrail held the action: {g_result.reason}. Please confirm before proceeding.")
                response_text = f"I'm not fully sure I heard that right. {g_result.reason}. Can you confirm?"
        else:
            st.error(f"Unknown skill: {orch_result.skill_name}")
    else:
        st.info("No matching skill and no clarifying question -- check the orchestrator prompt/backend.")

    report = TransparencyReport(
        asr_confidence=asr_confidence,
        corrections_made=eq_result.corrections_made,
        languages_detected=norm_result.languages_detected,
        skill_invoked=orch_result.skill_name or "",
        guardrail_approved=g_result.approved if g_result else True,
        guardrail_reason=g_result.reason if g_result else "",
    )
    st.subheader("Transparency")
    for badge in report.badges():
        st.markdown(f"- {badge}")

    if response_text and config.TTS_BACKEND != "mock":
        audio_bytes = tts.speak(response_text)
        if audio_bytes:
            st.subheader("Spoken response")
            st.audio(audio_bytes, format="audio/wav")

st.divider()
st.caption("Available skills: " + ", ".join(get_skills().keys()))
