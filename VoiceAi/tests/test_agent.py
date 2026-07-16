"""
Tests for the multi-step agent loop. Uses mock/fake LLMs only -- no network.
Covers: multi-step trace, tool call + observation, finalize, clarify, the
step cap, and the loop guard against re-calling the same tool.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.agent.agent import run_agent
from src.knowledge.rag import KnowledgeBase, seed_default_knowledge_base
from src.llm import get_llm_backend
from src.understanding.intent import Intent


class FakeLLM:
    """Returns a scripted sequence of agent decisions, one per call, so we
    can drive the loop down a specific path deterministically."""

    def __init__(self, decisions):
        self._decisions = list(decisions)
        self.calls = 0

    def complete(self, system, user, *, task="", context=None):
        self.calls += 1
        if self._decisions:
            return json.dumps(self._decisions.pop(0))
        return json.dumps({"thought": "done", "action": "finish", "answer": "fallback"})


def _ctx(tmp_path):
    kb = KnowledgeBase(collection_name=f"agent_kb_{tmp_path.name}")
    seed_default_knowledge_base(kb)
    return {"knowledge_base": kb}


def test_agent_multi_step_calls_tool_then_finishes(tmp_path):
    """The core agentic behaviour: call a tool, observe, then finalize --
    a genuine >1 step trace, driven by the offline mock backend."""
    llm = get_llm_backend("intent")  # MockLLMBackend under default profile
    result = run_agent("what is PAS 901", Intent(goal="get_information"), [], _ctx(tmp_path), llm, max_steps=3)
    assert len(result.steps) >= 2
    assert result.steps[0].action == "call_skill"
    assert result.steps[-1].action == "finish"
    assert result.skills_used  # at least one tool used
    assert result.answer


def test_agent_finishes_directly_when_no_tool_matches(tmp_path):
    llm = get_llm_backend("intent")
    result = run_agent("the weather is pleasant", Intent(), [], _ctx(tmp_path), llm, max_steps=3)
    assert result.steps[-1].action == "finish"
    assert result.answer


def test_agent_clarify_path_via_fake_llm(tmp_path):
    llm = FakeLLM([{"thought": "ambiguous", "action": "clarify", "question": "Did you mean floor 11?"}])
    result = run_agent("eleven", Intent(), [], _ctx(tmp_path), llm, max_steps=3)
    assert result.clarification == "Did you mean floor 11?"
    assert result.steps[-1].action == "clarify"
    assert result.answer is None


def test_agent_respects_max_steps_cap(tmp_path):
    # An LLM that always wants to call a (different-looking) tool would loop
    # forever without the cap; here it always says call_skill for a real tool.
    llm = FakeLLM(
        [
            {"thought": "1", "action": "call_skill", "skill": "faq_lookup", "params": {"query": "x"}},
            {"thought": "2", "action": "call_skill", "skill": "faq_lookup", "params": {"query": "y"}},
            {"thought": "3", "action": "call_skill", "skill": "faq_lookup", "params": {"query": "z"}},
            {"thought": "4", "action": "call_skill", "skill": "faq_lookup", "params": {"query": "w"}},
        ]
    )
    result = run_agent("question", Intent(), [], _ctx(tmp_path), llm, max_steps=2)
    # Never more steps than the cap.
    assert len(result.steps) <= 2
    assert result.hit_max_steps
    assert result.answer  # still produces something to say


def test_agent_loop_guard_blocks_repeated_tool(tmp_path):
    llm = FakeLLM(
        [
            {"thought": "call once", "action": "call_skill", "skill": "faq_lookup", "params": {"query": "x"}},
            {"thought": "call again (should be blocked)", "action": "call_skill", "skill": "faq_lookup", "params": {"query": "x"}},
        ]
    )
    result = run_agent("question", Intent(), [], _ctx(tmp_path), llm, max_steps=5)
    # faq_lookup used exactly once despite being requested twice.
    assert result.skills_used.count("faq_lookup") == 1
    assert result.hit_max_steps


def test_agent_malformed_json_is_handled(tmp_path):
    class BadLLM:
        def complete(self, system, user, *, task="", context=None):
            return "not json at all"

    result = run_agent("hello", Intent(), [], _ctx(tmp_path), BadLLM(), max_steps=3)
    assert result.hit_max_steps
    # Doesn't crash; returns an empty-but-valid result.
    assert isinstance(result.steps, list)
