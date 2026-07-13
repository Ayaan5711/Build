import streamlit as st

from src import config
from src.agent.guardrail import check as guardrail_check
from src.agent.memory import Memory
from src.agent.orchestrator import orchestrate
from src.foundation.asr import get_asr_backend
from src.foundation.equalizer import equalize
from src.foundation.normalizer import normalize
from src.llm import get_llm_backend
from src.skills import get_skills
from src.transparency import TransparencyReport

st.set_page_config(page_title="Vocal Accessibility Layer")
st.title("Vocal Accessibility Layer")
st.caption(f"ASR backend: {config.ASR_BACKEND} · LLM backend: {config.LLM_BACKEND} · Embed backend: {config.EMBED_BACKEND}")

llm = get_llm_backend()
asr = get_asr_backend()
memory = Memory(user_id="demo-user")
memory.seed_faq(
    [
        {"question": "What time does the lab open?", "answer": "The Gen AI Lab opens at 9 AM."},
        {"question": "What is PAS 901?", "answer": "PAS 901:2025 is the Vocal Accessibility code of practice."},
    ]
)

mode = st.radio("Input mode", ["Text (dev)", "Audio file"], horizontal=True)

raw_text = None
asr_confidence = 1.0

if mode == "Text (dev)":
    raw_text = st.text_input(
        "Type an utterance (stands in for speech until real ASR is wired in):",
        "M-m-m-my na-name i-is So-soumesh, s-schedule a m-meeting at 5 PM",
    )
else:
    uploaded = st.file_uploader("Upload a short audio clip", type=["wav", "mp3", "m4a"])
    if uploaded:
        temp_path = "uploaded_audio" + "." + uploaded.name.rsplit(".", 1)[-1]
        with open(temp_path, "wb") as f:
            f.write(uploaded.read())
        result = asr.transcribe(temp_path)
        raw_text = result.text
        asr_confidence = result.confidence

if raw_text and st.button("Run pipeline"):
    with st.spinner("Running foundation layer..."):
        eq_result = equalize(raw_text, llm)
        norm_result = normalize(eq_result.clean_text, llm)

    st.subheader("Foundation layer")
    st.write("**Raw transcript:**", raw_text)
    st.write("**Cleaned (Speech Equalizer):**", eq_result.clean_text)
    st.write("**Detected intent / entities:**", norm_result.intent, norm_result.entities)

    with st.spinner("Routing to a skill..."):
        orch_result = orchestrate(norm_result.intent, norm_result.entities, norm_result.clean_text, llm)

    st.subheader("Agent layer")
    g_result = None
    if orch_result.clarify and not orch_result.skill_name:
        st.warning(f"Clarifying question: {orch_result.clarify}")
    elif orch_result.skill_name:
        skills = get_skills()
        skill = skills.get(orch_result.skill_name)
        if skill:
            with st.spinner("Checking guardrail..."):
                g_result = guardrail_check(asr_confidence, f"{skill.name}({orch_result.params})", llm)
            if g_result.approved:
                skill_result = skill.run(orch_result.params, memory)
                st.success(skill_result.output)
            else:
                st.warning(f"Guardrail held the action: {g_result.reason}. Please confirm before proceeding.")
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

st.divider()
st.caption("Available skills: " + ", ".join(get_skills().keys()))
