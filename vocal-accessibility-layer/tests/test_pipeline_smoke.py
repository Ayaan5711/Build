"""
End-to-end smoke test using the mock backends only (no network, no model
weights, no microphone). Verifies the plumbing between every stage --
ASR -> Equalizer -> Normalizer -> Orchestrator -> Guardrail -> Skill --
is wired correctly. Swap backends to "local"/"ollama"/"event" for real
runs; this test intentionally stays on "mock" so it always passes offline.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.agent.guardrail import check as guardrail_check
from src.agent.memory import Memory
from src.agent.orchestrator import orchestrate
from src.foundation.asr import get_asr_backend
from src.foundation.equalizer import equalize
from src.foundation.normalizer import normalize
from src.llm import get_llm_backend
from src.skills import get_skills


def test_full_pipeline_schedule_intent(tmp_path):
    llm = get_llm_backend()
    asr = get_asr_backend()
    memory = Memory(user_id=f"test-{tmp_path.name}")

    audio_path = "data/sample_audio/example1.txt".replace(".txt", ".wav")
    asr_result = asr.transcribe(audio_path)
    assert "schedule" in asr_result.text.lower()

    eq_result = equalize(asr_result.text, llm)
    assert eq_result.corrections_made
    assert "M-m-m-my" not in eq_result.clean_text

    norm_result = normalize(eq_result.clean_text, llm)
    assert norm_result.clean_text

    orch_result = orchestrate(norm_result.intent, norm_result.entities, norm_result.clean_text, llm)
    assert orch_result.skill_name == "schedule_reminder"

    skills = get_skills()
    skill = skills[orch_result.skill_name]

    g_result = guardrail_check(asr_result.confidence, f"{skill.name}({orch_result.params})", llm)
    assert g_result.approved

    skill_result = skill.run(orch_result.params, memory)
    assert skill_result.success


def test_faq_skill_routes_and_answers(tmp_path):
    llm = get_llm_backend()
    memory = Memory(user_id=f"test-faq-{tmp_path.name}")
    memory.seed_faq([{"question": "What is PAS 901?", "answer": "A vocal accessibility standard."}])

    eq_result = equalize("what is PAS 901", llm)
    norm_result = normalize(eq_result.clean_text, llm)
    orch_result = orchestrate(norm_result.intent, norm_result.entities, norm_result.clean_text, llm)
    assert orch_result.skill_name == "faq_lookup"

    skill = get_skills()[orch_result.skill_name]
    result = skill.run({"query": "PAS 901"}, memory)
    assert result.success
    assert "vocal accessibility" in result.output.lower()


def test_skill_registry_discovers_all_skills():
    skills = get_skills()
    assert "faq_lookup" in skills
    assert "schedule_reminder" in skills


def test_new_skill_can_be_added_without_touching_orchestrator(tmp_path):
    """
    Proves the core extensibility claim: dropping a new Skill subclass in
    src/skills/ registers it automatically with zero changes to
    orchestrator.py, guardrail.py, or the foundation layer.
    """
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
            "    def run(self, params, memory):\n"
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
