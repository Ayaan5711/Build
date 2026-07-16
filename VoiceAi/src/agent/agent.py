import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.knowledge.rag import RetrievedSnippet
from src.llm import LLMBackend
from src.skills import get_skills
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
    """
    skills = get_skills()
    tool_schemas = [s.schema() for s in skills.values()]
    observations: List[Dict[str, str]] = []
    result = AgentResult()

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
