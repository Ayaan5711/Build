import json
import os
import threading
from dataclasses import dataclass, field
from typing import List

from src import config


class BudgetExceeded(RuntimeError):
    """Raised when a hosted call would push estimated spend past the cap.
    The pipeline treats this like any other backend failure -- it falls
    back to cached scenarios (NFR-03) rather than crashing."""


@dataclass
class CostEntry:
    stage: str
    model: str
    kind: str  # "llm" | "embedding" | "asr"
    units: float  # tokens (llm/embedding) or minutes (asr)
    usd: float


@dataclass
class CostTracker:
    """
    Estimates and caps hosted spend across the session. Local Ollama and
    mock calls cost nothing and are never recorded. Persists to a small
    gitignored JSON so the running total survives app restarts during the
    event (Streamlit reruns the script constantly).

    Costs are ESTIMATES from a static rate table for budgeting -- a
    guardrail against runaway loops, not a billing statement.
    """

    entries: List[CostEntry] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    @property
    def total_usd(self) -> float:
        return round(sum(e.usd for e in self.entries), 6)

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        # ~4 chars/token is the standard rough estimate; good enough for a
        # budget guardrail when the API doesn't return exact usage.
        return max(1, len(text or "") // 4)

    @staticmethod
    def _rate_for(model: str):
        for key, rate in config.COST_PER_1M_TOKENS.items():
            if key != "_default" and key in model:
                return rate
        return config.COST_PER_1M_TOKENS["_default"]

    def estimate_llm_usd(self, model: str, prompt: str, completion: str) -> float:
        in_rate, out_rate = self._rate_for(model)
        in_tok = self._estimate_tokens(prompt)
        out_tok = self._estimate_tokens(completion)
        return (in_tok * in_rate + out_tok * out_rate) / 1_000_000

    def check_budget(self, prospective_usd: float = 0.0):
        if self.total_usd + prospective_usd > config.BUDGET_USD_CAP:
            raise BudgetExceeded(
                f"Estimated spend ${self.total_usd:.4f} + ${prospective_usd:.4f} would exceed "
                f"the ${config.BUDGET_USD_CAP:.2f} cap. Refusing hosted call; falling back."
            )

    def record_llm(self, stage: str, model: str, prompt: str, completion: str):
        usd = self.estimate_llm_usd(model, prompt, completion)
        tokens = self._estimate_tokens(prompt) + self._estimate_tokens(completion)
        with self._lock:
            self.entries.append(CostEntry(stage, model, "llm", tokens, usd))
            self._persist()

    def record_embedding(self, stage: str, model: str, texts: List[str]):
        in_rate, _ = self._rate_for(model)
        tokens = sum(self._estimate_tokens(t) for t in texts)
        usd = tokens * in_rate / 1_000_000
        with self._lock:
            self.entries.append(CostEntry(stage, model, "embedding", tokens, usd))
            self._persist()

    def record_asr(self, stage: str, model: str, minutes: float):
        usd = minutes * config.WHISPER_COST_PER_MINUTE
        with self._lock:
            self.entries.append(CostEntry(stage, model, "asr", minutes, usd))
            self._persist()

    def summary_by_stage(self) -> dict:
        out = {}
        for e in self.entries:
            out.setdefault(e.stage, 0.0)
            out[e.stage] += e.usd
        return {k: round(v, 6) for k, v in out.items()}

    def _persist(self):
        try:
            with open(config.COST_LOG_PATH, "w") as f:
                json.dump(
                    {"total_usd": self.total_usd, "entries": [e.__dict__ for e in self.entries]},
                    f,
                    indent=2,
                )
        except OSError:
            pass  # cost logging must never break the pipeline

    @classmethod
    def load(cls) -> "CostTracker":
        tracker = cls()
        if os.path.exists(config.COST_LOG_PATH):
            try:
                with open(config.COST_LOG_PATH) as f:
                    data = json.load(f)
                tracker.entries = [
                    CostEntry(e["stage"], e["model"], e["kind"], e["units"], e["usd"]) for e in data.get("entries", [])
                ]
            except (OSError, json.JSONDecodeError, KeyError):
                pass
        return tracker


# Process-wide singleton so every backend records into the same tally.
_tracker = None


def get_cost_tracker() -> CostTracker:
    global _tracker
    if _tracker is None:
        _tracker = CostTracker.load()
    return _tracker


def reset_cost_tracker():
    """Clear the running total (e.g. a 'reset budget' button in the UI)."""
    global _tracker
    _tracker = CostTracker()
    _tracker._persist()
    return _tracker
