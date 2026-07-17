import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.knowledge.rag import RetrievedSnippet
from src.llm import LLMBackend
from src.skills import get_skills
from src.understanding import dialogue_state
from src.understanding.intent import Intent

AGENT_SYSTEM_PROMPT = (
    "You are the action planner for an accessibility-first voice assistant. You "
    "work in a loop: each turn you either call ONE tool (skill) to get information "
    "or perform an action, ask the user ONE plain-language clarifying question if "
    "the request is genuinely ambiguous or missing required info, or finish with a "
    "final answer once you have enough. Respond ONLY with JSON:\n"
    '{"thought": <short reasoning>, "action": "call_skill"|"clarify"|"finish", '
    '"skill": <tool name or null>, "params": {<tool params>}, '
    '"question": <clarifying question or null>, "answer": <final answer or null>}.\n'
    "Rules: never call the same tool twice; prefer finishing quickly (fewer steps "
    "is better for a live demo); keep the user's meaning intact; be supportive, "
    "never diagnostic."
)


@dataclass
class AgentStep:
    step: int
    thought: str
    action: str  # "call_skill" | "clarify" | "finish"
    skill: Optional[str] = None
    params: Dict[str, Any] = field(default_factory=dict)
    question: Optional[str] = None
    observation: Optional[str] = None


@dataclass
class AgentResult:
    steps: List[AgentStep] = field(default_factory=list)
    answer: Optional[str] = None
    clarification: Optional[str] = None
    skills_used: List[str] = field(default_factory=list)
    skill_outputs: List[str] = field(default_factory=list)
    hit_max_steps: bool = False

    @property
    def combined_output(self) -> str:
        """A single string for the grounded-response synthesizer to build on:
        the agent's final answer if it produced one, else its gathered
        observations."""
        if self.answer:
            return self.answer
        return " | ".join(self.skill_outputs)


def _continue_pending_dialogue(
    pending: dialogue_state.PendingTask,
    accessible_text: str,
    skills: Dict[str, Any],
    ctx: Dict[str, Any],
) -> AgentResult:
    """
    Advances an in-progress guided dialogue by one turn (cognitive-load
    reduction: one question at a time, paced, instead of demanding every
    detail in one complex utterance). The current utterance is treated as
    the answer to whatever question was last asked -- not re-planned from
    scratch -- which is exactly the memory a stateless per-turn pipeline
    doesn't have on its own.
    """
    result = AgentResult()
    skill = skills.get(pending.skill_name)
    if not skill:
        dialogue_state.clear_pending_task(pending.user_id)
        result.answer = "Sorry, I lost track of that request. Could you start over?"
        return result

    if pending.turns >= dialogue_state.MAX_DIALOGUE_TURNS:
        dialogue_state.clear_pending_task(pending.user_id)
        step = AgentStep(
            step=1,
            thought="Guided dialogue exceeded its turn cap -- resetting instead of looping indefinitely.",
            action="finish",
        )
        result.steps.append(step)
        result.answer = "I'm having trouble gathering all the details for that. Let's start over -- what would you like to do?"
        return result

    dialogue_state.record_answer(pending.user_id, accessible_text)
    missing = skill.missing_slots(pending.filled_slots)

    if missing:
        next_slot = missing[0]
        dialogue_state.set_asked_slot(pending.user_id, next_slot)
        question = skill.required_slots[next_slot]
        step = AgentStep(
            step=1,
            thought=f"Got an answer for the previous question; still need '{next_slot}' before {pending.skill_name} can run.",
            action="clarify",
            skill=pending.skill_name,
            params=dict(pending.filled_slots),
            question=question,
        )
        result.steps.append(step)
        result.clarification = question
        return result

    # Every required slot is filled -- the paced dialogue is complete, run
    # the skill for real now (this is the only point at which it's called).
    skill_result = skill.run(pending.filled_slots, ctx)
    step = AgentStep(
        step=1,
        thought=f"All details for '{pending.skill_name}' are gathered -- completing the task.",
        action="call_skill",
        skill=pending.skill_name,
        params=dict(pending.filled_slots),
        observation=skill_result.output,
    )
    result.steps.append(step)
    result.skills_used.append(pending.skill_name)
    result.skill_outputs.append(skill_result.output)
    result.answer = skill_result.output
    dialogue_state.clear_pending_task(pending.user_id)
    return result


def run_agent(
    accessible_text: str,
    intent: Intent,
    retrieved_context: List[RetrievedSnippet],
    ctx: Dict[str, Any],
    llm: LLMBackend,
    max_steps: int = 3,
) -> AgentResult:
    """
    A real agent loop (not one-shot routing): plan -> call a skill -> observe
    the result -> decide again, up to max_steps. Skills are the agent's
    tools. Ends when the agent finishes, asks a clarifying question, or hits
    the step cap (which also bounds latency/cost -- important on slow
    hardware, since each step is one LLM call). The full trace is returned
    for transparency (NFR-08) and makes the agent's reasoning visible in the
    dashboard.

    Also owns the guided-dialogue entry point: if this user has an
    in-progress paced task (see src/understanding/dialogue_state.py), this
    turn continues it instead of re-planning from scratch.
    """
    skills = get_skills()
    tool_schemas = [s.schema() for s in skills.values()]
    observations: List[Dict[str, str]] = []
    result = AgentResult()

    user_memory = ctx.get("user_memory")
    user_id = getattr(user_memory, "user_id", None)

    if user_id:
        pending = dialogue_state.get_pending_task(user_id)
        if pending:
            return _continue_pending_dialogue(pending, accessible_text, skills, ctx)

    for i in range(1, max_steps + 1):
        payload = {
            "user_request": accessible_text,
            "intent": {"goal": intent.goal, "action_type": intent.action_type, "entities": intent.entities},
            "available_tools": tool_schemas,
            "retrieved_context": [{"title": s.title, "content": s.content} for s in retrieved_context],
            "observations_so_far": observations,
            "steps_remaining": max_steps - i + 1,
        }
        raw = llm.complete(AGENT_SYSTEM_PROMPT, json.dumps(payload), task="agent_step")
        try:
            decision = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            # Malformed plan -> stop safely with whatever we have.
            result.hit_max_steps = True
            break

        action = decision.get("action", "finish")
        step = AgentStep(
            step=i,
            thought=decision.get("thought", ""),
            action=action,
            skill=decision.get("skill"),
            params=decision.get("params") or {},
            question=decision.get("question"),
        )

        if action == "call_skill":
            name = decision.get("skill")
            # Loop guard: never run the same tool twice -- prevents an LLM
            # from spinning, and bounds cost/latency.
            if name in result.skills_used:
                step.observation = f"(skipped: {name} already used) -- finalizing"
                result.steps.append(step)
                result.hit_max_steps = True
                break
            skill = skills.get(name)
            if not skill:
                step.observation = f"No such tool: {name}"
                result.steps.append(step)
                continue

            # Cognitive-load reduction: if this skill needs something the
            # planner didn't supply, don't call it half-specified (e.g. a
            # reminder with no time) and don't dump every missing field on
            # the user at once either -- start a paced dialogue and ask for
            # exactly one thing.
            missing = skill.missing_slots(step.params) if user_id else []
            if missing:
                dialogue_state.start_pending_task(user_id, name, step.params, accessible_text)
                first_slot = missing[0]
                dialogue_state.set_asked_slot(user_id, first_slot)
                question = skill.required_slots[first_slot]
                step.action = "clarify"
                step.question = question
                result.steps.append(step)
                result.clarification = question
                return result

            skill_result = skill.run(step.params, ctx)
            step.observation = skill_result.output
            result.steps.append(step)
            result.skills_used.append(name)
            result.skill_outputs.append(skill_result.output)
            observations.append({"skill": name, "observation": skill_result.output})
            continue

        if action == "clarify":
            result.steps.append(step)
            result.clarification = decision.get("question")
            return result

        # finish (or any unknown action -> treat as finish)
        step.action = "finish"
        result.steps.append(step)
        result.answer = decision.get("answer") or result.combined_output
        return result

    # Ran out of steps without an explicit finish.
    result.hit_max_steps = True
    if not result.answer:
        result.answer = result.combined_output or "I've gathered what I can; please confirm how you'd like to proceed."
    return result
