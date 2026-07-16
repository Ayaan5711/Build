"""
Tests for the cost tracker, budget cap, and cost-profile routing. All run
offline -- they exercise the estimation/routing logic, never a real API.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.cost import BudgetExceeded, CostTracker


def _fresh_tracker(tmp_path, monkeypatch):
    from src import config

    monkeypatch.setattr(config, "COST_LOG_PATH", str(tmp_path / ".cost_log.json"))
    return CostTracker()


def test_local_and_mock_backends_record_no_cost(tmp_path, monkeypatch):
    """The whole point of the budget design: Ollama/mock stages cost $0 and
    never touch the tracker."""
    tracker = _fresh_tracker(tmp_path, monkeypatch)
    assert tracker.total_usd == 0.0
    assert tracker.summary_by_stage() == {}


def test_llm_cost_estimate_is_positive_and_stagewise(tmp_path, monkeypatch):
    tracker = _fresh_tracker(tmp_path, monkeypatch)
    tracker.record_llm("response", "azure/genailab-maas-gpt-4o", "a prompt " * 50, "a completion " * 20)
    assert tracker.total_usd > 0
    assert "response" in tracker.summary_by_stage()


def test_gpt4o_costs_more_than_gpt4o_mini(tmp_path, monkeypatch):
    tracker = _fresh_tracker(tmp_path, monkeypatch)
    prompt = "word " * 100
    completion = "word " * 100
    big = tracker.estimate_llm_usd("azure/genailab-maas-gpt-4o", prompt, completion)
    small = tracker.estimate_llm_usd("azure/genailab-maas-gpt-4o-mini", prompt, completion)
    assert big > small > 0


def test_budget_cap_blocks_when_exceeded(tmp_path, monkeypatch):
    from src import config

    tracker = _fresh_tracker(tmp_path, monkeypatch)
    monkeypatch.setattr(config, "BUDGET_USD_CAP", 0.0000001)
    tracker.record_llm("response", "azure/genailab-maas-gpt-4o", "x " * 500, "y " * 500)
    try:
        tracker.check_budget(0.01)
        assert False, "expected BudgetExceeded"
    except BudgetExceeded:
        pass


def test_budget_check_passes_under_cap(tmp_path, monkeypatch):
    from src import config

    tracker = _fresh_tracker(tmp_path, monkeypatch)
    monkeypatch.setattr(config, "BUDGET_USD_CAP", 100.0)
    tracker.check_budget(0.001)  # should not raise


def test_asr_cost_recorded_by_minutes(tmp_path, monkeypatch):
    tracker = _fresh_tracker(tmp_path, monkeypatch)
    tracker.record_asr("asr", "azure/genailab-maas-whisper", 2.0)
    assert tracker.total_usd > 0


def test_cost_log_persists_and_reloads(tmp_path, monkeypatch):
    from src import config

    log_path = str(tmp_path / ".cost_log.json")
    monkeypatch.setattr(config, "COST_LOG_PATH", log_path)
    tracker = CostTracker()
    tracker.record_llm("intent", "azure/genailab-maas-gpt-4o-mini", "hello", "world")
    assert os.path.exists(log_path)
    reloaded = CostTracker.load()
    assert reloaded.total_usd == tracker.total_usd


def test_profile_mock_routes_all_llm_roles_to_mock(monkeypatch):
    import importlib

    monkeypatch.setenv("PROFILE", "mock")
    for k in list(os.environ):
        if k.startswith("LLM_BACKEND"):
            monkeypatch.delenv(k, raising=False)
    from src import config

    importlib.reload(config)
    for role in ("cleanup", "reasoning", "intent", "response", "caption"):
        assert config.resolve_llm_backend(role) == "mock"
    importlib.reload(config)  # restore default for other tests


def test_profile_hybrid_uses_local_for_cleanup_hosted_for_response(monkeypatch):
    import importlib

    monkeypatch.setenv("PROFILE", "hybrid")
    for k in list(os.environ):
        if k.startswith("LLM_BACKEND"):
            monkeypatch.delenv(k, raising=False)
    from src import config

    importlib.reload(config)
    assert config.resolve_llm_backend("cleanup") == "ollama"
    assert config.resolve_llm_backend("intent") == "ollama"
    assert config.resolve_llm_backend("response") == "event"
    assert config.ASR_BACKEND == "event"
    assert config.EMBED_BACKEND == "ollama"
    monkeypatch.setenv("PROFILE", "mock")
    importlib.reload(config)  # restore


def test_per_role_env_override_wins_over_profile(monkeypatch):
    import importlib

    monkeypatch.setenv("PROFILE", "local")
    monkeypatch.setenv("LLM_BACKEND_RESPONSE", "event")
    from src import config

    importlib.reload(config)
    assert config.resolve_llm_backend("response") == "event"
    assert config.resolve_llm_backend("cleanup") == "ollama"
    monkeypatch.delenv("LLM_BACKEND_RESPONSE", raising=False)
    monkeypatch.setenv("PROFILE", "mock")
    importlib.reload(config)  # restore
