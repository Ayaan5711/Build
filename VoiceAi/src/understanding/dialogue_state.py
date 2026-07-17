"""
Slot-filling dialogue manager for cognitive-friendly, paced multi-step
interactions (the "Simplified Voice Interaction for Users with Cognitive
Challenges" problem statement). Without this module every /api/run call is
independent -- the agent can ask "what time?" but has no way to know, on
the next turn, that the reply is an answer to that specific question
rather than a brand-new request. This module is exactly that missing
memory: which task is in progress, which slots are filled, and which
question was just asked.

Deliberately in-process, per-user, in-memory (not persisted to disk) --
a half-answered question shouldn't survive a server restart, unlike an
actually-completed reminder (see src/integrations/reminders_store.py,
which IS persisted). This mirrors src/knowledge/personalization.py's
scope: single-demo-laptop, one process, not a multi-instance deployment.
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# Safety cap on how many turns one guided dialogue can run before we give up
# and let the user start over -- bounds the same "runaway loop" risk the
# agent's own step cap protects against, just across turns instead of
# within one.
MAX_DIALOGUE_TURNS = 6


@dataclass
class PendingTask:
    user_id: str
    skill_name: str
    filled_slots: Dict[str, Any] = field(default_factory=dict)
    asked_slot: Optional[str] = None
    turns: int = 0
    original_utterance: str = ""


_pending: Dict[str, PendingTask] = {}


def get_pending_task(user_id: str) -> Optional[PendingTask]:
    return _pending.get(user_id)


def start_pending_task(user_id: str, skill_name: str, filled_slots: Dict[str, Any], original_utterance: str) -> PendingTask:
    task = PendingTask(user_id=user_id, skill_name=skill_name, filled_slots=dict(filled_slots), original_utterance=original_utterance)
    _pending[user_id] = task
    return task


def set_asked_slot(user_id: str, slot_name: str) -> None:
    task = _pending.get(user_id)
    if task:
        task.asked_slot = slot_name


def record_answer(user_id: str, answer_text: str) -> Optional[PendingTask]:
    """Fills whichever slot was last asked with the raw answer text (the
    accessible transcript of the reply). No-op if there's no open question
    to answer."""
    task = _pending.get(user_id)
    if not task or not task.asked_slot:
        return None
    task.filled_slots[task.asked_slot] = answer_text
    task.asked_slot = None
    task.turns += 1
    return task


def clear_pending_task(user_id: str) -> None:
    _pending.pop(user_id, None)


def reset_all() -> None:
    """Test-only: clear every in-progress dialogue between test cases."""
    _pending.clear()
