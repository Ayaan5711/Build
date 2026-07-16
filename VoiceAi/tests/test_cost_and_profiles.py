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


# ------------------------------------------------------------------------
# Real bug reproduction: python-dotenv does NOT strip a trailing "# comment"
# on a line whose value is blank (e.g. "KEY=   # mock | local" parses as
# KEY="# mock | local", the entire comment, not KEY=""). .env.example used
# to have exactly that pattern on "leave blank to use the profile" lines --
# left un-edited, this silently set backends to a garbage string that is
# truthy, which (for the global LLM_BACKEND) would silently override every
# role's profile-based routing. Found via live testing on a real machine.
# ------------------------------------------------------------------------
def test_garbled_comment_value_is_ignored_not_used_literally(monkeypatch):
    import importlib

    # Exactly what a leftover, un-edited .env.example line produces.
    monkeypatch.setenv("VISION_BACKEND", "# mock | local (MediaPipe Hands)")
    monkeypatch.setenv("PROFILE", "mock")
    from src import config

    importlib.reload(config)
    assert config.VISION_BACKEND == "mock"  # falls back to profile default, not the garbage string
    monkeypatch.delenv("VISION_BACKEND", raising=False)
    importlib.reload(config)  # restore


def test_garbled_global_llm_backend_does_not_veto_profile_routing(monkeypatch):
    """This is the serious variant: a garbled (but non-empty, hence
    previously truthy) global LLM_BACKEND would have silently forced every
    role back to mock even under PROFILE=hybrid/fast, defeating the whole
    point of switching profiles for the real demo."""
    import importlib

    monkeypatch.setenv("LLM_BACKEND", "# (blank) | mock | ollama | event")
    monkeypatch.setenv("PROFILE", "hybrid")
    from src import config

    importlib.reload(config)
    assert config.LLM_BACKEND == ""  # garbage treated as blank, not a literal override
    assert config.resolve_llm_backend("response") == "event"  # hybrid profile's real routing intact
    assert config.resolve_llm_backend("cleanup") == "ollama"
    monkeypatch.delenv("LLM_BACKEND", raising=False)
    monkeypatch.setenv("PROFILE", "mock")
    importlib.reload(config)  # restore


def test_invalid_profile_value_falls_back_to_mock(monkeypatch):
    import importlib

    monkeypatch.setenv("PROFILE", "not-a-real-profile")
    from src import config

    importlib.reload(config)
    assert config.PROFILE == "mock"
    monkeypatch.setenv("PROFILE", "mock")
    importlib.reload(config)  # restore
