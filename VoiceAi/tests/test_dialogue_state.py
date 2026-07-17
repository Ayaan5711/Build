"""
Tests for the guided-dialogue slot-filling machinery (the "Simplified Voice
Interaction for Users with Cognitive Challenges" problem statement's core
requirement: paced, one-question-at-a-time interactions with real cross-turn
memory, not a stateless per-turn pipeline). Covers three layers: the Skill
base class's missing_slots(), the dialogue_state store itself, and the
agent's use of both to pace a real multi-turn task end to end.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from src.agent.agent import run_agent
from src.skills.base import Skill, SkillResult
from src.understanding import dialogue_state
from src.understanding.intent import Intent


@pytest.fixture(autouse=True)
def _clean_dialogue_state():
    """dialogue_state is a module-level store shared across the whole test
    process (mirrors its production scope: one server process, one demo) --
    reset it before and after every test so tests can't leak pending tasks
    into each other."""
    dialogue_state.reset_all()
    yield
    dialogue_state.reset_all()


class _FakeUserMemory:
    def __init__(self, user_id):
        self.user_id = user_id


class _TwoSlotSkill(Skill):
    name = "book_thing"
    description = "test skill with two required slots"
    keywords = ["book"]
    parameters = {"subject": "string", "time": "string"}
    required_slots = {"subject": "What should I book?", "time": "When?"}
    calls = []

    def run(self, params, ctx):
        _TwoSlotSkill.calls.append(dict(params))
        return SkillResult(True, f"Booked {params.get('subject')} at {params.get('time')}.", dict(params))


class FakeLLM:
    def __init__(self, decisions):
        self._decisions = list(decisions)

    def complete(self, system, user, *, task="", context=None):
        if self._decisions:
            return json.dumps(self._decisions.pop(0))
        return json.dumps({"thought": "done", "action": "finish", "answer": "fallback"})


def _ctx(user_id="u1"):
    return {"user_memory": _FakeUserMemory(user_id)}


# --------------------------------------------------------- Skill.missing_slots --
def test_missing_slots_reports_unfilled_required_fields_in_declared_order():
    skill = _TwoSlotSkill()
    assert skill.missing_slots({}) == ["subject", "time"]
    assert skill.missing_slots({"subject": "dentist"}) == ["time"]
    assert skill.missing_slots({"subject": "dentist", "time": "5pm"}) == []


def test_missing_slots_treats_blank_string_as_unfilled():
    skill = _TwoSlotSkill()
    assert skill.missing_slots({"subject": "  ", "time": "5pm"}) == ["subject"]


def test_skill_with_no_required_slots_never_reports_missing():
    from src.skills.faq_lookup import FAQLookupSkill

    assert FAQLookupSkill().missing_slots({}) == []


# ------------------------------------------------------------- dialogue_state --
def test_start_and_get_pending_task():
    assert dialogue_state.get_pending_task("u1") is None
    task = dialogue_state.start_pending_task("u1", "book_thing", {"subject": "dentist"}, "book the dentist")
    assert dialogue_state.get_pending_task("u1") is task
    assert task.filled_slots == {"subject": "dentist"}


def test_record_answer_fills_the_asked_slot_and_clears_it():
    dialogue_state.start_pending_task("u1", "book_thing", {}, "book something")
    dialogue_state.set_asked_slot("u1", "subject")
    task = dialogue_state.record_answer("u1", "the dentist")
    assert task.filled_slots["subject"] == "the dentist"
    assert task.asked_slot is None
    assert task.turns == 1


def test_record_answer_is_a_noop_without_an_open_question():
    dialogue_state.start_pending_task("u1", "book_thing", {}, "book something")
    # No set_asked_slot call -- nothing was actually asked yet.
    assert dialogue_state.record_answer("u1", "the dentist") is None


def test_clear_pending_task_removes_it():
    dialogue_state.start_pending_task("u1", "book_thing", {}, "book something")
    dialogue_state.clear_pending_task("u1")
    assert dialogue_state.get_pending_task("u1") is None


def test_pending_tasks_are_isolated_per_user():
    dialogue_state.start_pending_task("u1", "book_thing", {"subject": "dentist"}, "x")
    dialogue_state.start_pending_task("u2", "book_thing", {"subject": "haircut"}, "y")
    assert dialogue_state.get_pending_task("u1").filled_slots["subject"] == "dentist"
    assert dialogue_state.get_pending_task("u2").filled_slots["subject"] == "haircut"


# ---------------------------------------------- agent: pacing an under-specified call --
def test_agent_starts_guided_dialogue_instead_of_calling_underspecified_skill():
    """The core behaviour this whole feature exists for: when the planner's
    own params are missing something the skill actually needs, the agent
    must NOT call it half-specified -- it should ask for exactly the first
    missing thing and stop there."""
    llm = FakeLLM([{"thought": "book it", "action": "call_skill", "skill": "book_thing", "params": {}}])
    from src.skills import _registry

    _registry["book_thing"] = _TwoSlotSkill()
    try:
        result = run_agent("book something", Intent(), [], _ctx("agent-u1"), llm, max_steps=3)
        assert result.clarification == "What should I book?"
        assert result.steps[-1].action == "clarify"
        assert dialogue_state.get_pending_task("agent-u1") is not None
        assert dialogue_state.get_pending_task("agent-u1").asked_slot == "subject"
    finally:
        _registry.pop("book_thing", None)


def test_agent_full_paced_dialogue_completes_and_calls_skill_once():
    """Simulates the three real turns a user would produce: initial
    under-specified request, then two separate answers -- each call_agent
    call here stands in for a separate /api/run request."""
    from src.skills import _registry

    _registry["book_thing"] = _TwoSlotSkill()
    _TwoSlotSkill.calls.clear()
    try:
        llm1 = FakeLLM([{"thought": "book it", "action": "call_skill", "skill": "book_thing", "params": {}}])
        r1 = run_agent("book something", Intent(), [], _ctx("agent-u2"), llm1, max_steps=3)
        assert r1.clarification == "What should I book?"

        # Turn 2: this call must NOT re-plan from scratch -- it must treat
        # "the dentist" as the answer to the subject question, using a
        # completely different (and if consulted, wrong) LLM to prove the
        # continuation path doesn't even call the planner.
        llm2 = FakeLLM([{"thought": "should not be used", "action": "finish", "answer": "WRONG PATH"}])
        r2 = run_agent("the dentist", Intent(), [], _ctx("agent-u2"), llm2, max_steps=3)
        assert r2.clarification == "When?"
        assert r2.answer is None

        llm3 = FakeLLM([{"thought": "should not be used either", "action": "finish", "answer": "WRONG PATH"}])
        r3 = run_agent("5pm tomorrow", Intent(), [], _ctx("agent-u2"), llm3, max_steps=3)
        assert r3.clarification is None
        assert "Booked the dentist at 5pm tomorrow." == r3.answer
        assert dialogue_state.get_pending_task("agent-u2") is None
        assert _TwoSlotSkill.calls == [{"subject": "the dentist", "time": "5pm tomorrow"}]
    finally:
        _registry.pop("book_thing", None)


def test_agent_dialogue_turn_cap_resets_instead_of_looping_forever():
    from src.skills import _registry

    _registry["book_thing"] = _TwoSlotSkill()
    try:
        task = dialogue_state.start_pending_task("agent-u3", "book_thing", {}, "book something")
        task.turns = dialogue_state.MAX_DIALOGUE_TURNS
        dialogue_state.set_asked_slot("agent-u3", "subject")
        llm = FakeLLM([])  # must not be consulted -- the cap should trigger first
        result = run_agent("more rambling", Intent(), [], _ctx("agent-u3"), llm, max_steps=3)
        assert dialogue_state.get_pending_task("agent-u3") is None
        assert result.answer
        assert "start over" in result.answer.lower()
    finally:
        _registry.pop("book_thing", None)


def test_agent_no_pacing_when_planner_already_supplied_every_slot():
    """If the LLM already extracted both slots from one utterance (a real
    backend doing real NLU), no dialogue should start at all -- pacing only
    kicks in for what's actually missing."""
    from src.skills import _registry

    _registry["book_thing"] = _TwoSlotSkill()
    _TwoSlotSkill.calls.clear()
    try:
        llm = FakeLLM(
            [{"thought": "book it", "action": "call_skill", "skill": "book_thing", "params": {"subject": "dentist", "time": "5pm"}}]
        )
        result = run_agent("book the dentist at 5pm", Intent(), [], _ctx("agent-u4"), llm, max_steps=3)
        assert result.clarification is None
        assert dialogue_state.get_pending_task("agent-u4") is None
        assert _TwoSlotSkill.calls == [{"subject": "dentist", "time": "5pm"}]
    finally:
        _registry.pop("book_thing", None)
