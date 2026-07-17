import json
import re

from src import config


class LLMBackend:
    def complete(self, system: str, user: str, *, task: str = "", context: dict = None) -> str:
        raise NotImplementedError


class MockLLMBackend(LLMBackend):
    """
    Deterministic, model-free stand-in so the full pipeline can be built and
    smoke-tested with zero network/model access. It does NOT do real
    language understanding -- it's plumbing verification only. Switch
    LLM_BACKEND to "ollama" (local dev) or "event" (match day) for the
    real thing. Task names below mirror the PRD's Appendix A pseudocode
    function names one-to-one.
    """

    def complete(self, system: str, user: str, *, task: str = "", context: dict = None) -> str:
        handler = getattr(self, f"_{task}", None)
        if handler:
            return handler(user, context)
        return user

    # -- normalize_transcript / disfluency cleanup --------------------------
    @staticmethod
    def _cleanup(text: str, context: dict = None) -> str:
        for wrong, right in (context or {}).items():
            text = re.sub(re.escape(wrong), right, text, flags=re.IGNORECASE)
        # Collapse "B-b-b-book" / "Ka-ka-ka-Kiran" stutter artifacts and
        # immediate word repeats -- a rough stand-in for an LLM cleanup pass.
        text = re.sub(r"\b(\w)(-\1)+\b", r"\1", text, flags=re.IGNORECASE)
        text = re.sub(r"\b(\w+)-\1\b", r"\1", text, flags=re.IGNORECASE)
        words = text.split()
        deduped = []
        for w in words:
            if not deduped or deduped[-1].lower().rstrip(",.") != w.lower().rstrip(",."):
                deduped.append(w)
        return " ".join(deduped)

    # -- detect_language_mix -------------------------------------------------
    @staticmethod
    def _language(text: str, context: dict = None) -> str:
        return json.dumps({"languages_detected": ["en"], "code_mixed": False})

    # -- analyze_accent_noise_confidence clarifying question -----------------
    @staticmethod
    def _clarify(text: str, context: dict = None) -> str:
        # Small heuristic set standing in for real accent-uncertainty
        # reasoning -- covers the PRD's own demo sample 3 ("eleven" in a
        # regional accent -> "Did you mean floor 11?") so it's testable
        # offline. Real backends handle this generally via the reasoning
        # model, not this lookup.
        near_homophones = {"eleven": "floor 11", "won": "one", "ate": "eight", "too": "two"}
        lower = text.lower().strip()
        for word, meaning in near_homophones.items():
            if word in lower.split():
                return json.dumps({"clarifying_question": f"Did you mean {meaning}?"})
        return json.dumps({"clarifying_question": None})

    # -- analyze_accessibility (structured barrier report) -------------------
    @staticmethod
    def _accessibility_report(user: str, context: dict = None) -> str:
        payload = json.loads(user)
        barriers = []
        if payload.get("disfluency_report", {}).get("has_disfluency"):
            barriers.append("speech_impairment")
        if payload.get("accent_noise_report", {}).get("confidence", 1.0) < config.CONFIDENCE_THRESHOLD:
            barriers.append("noise_or_accent_uncertainty")
        if payload.get("language_report", {}).get("code_mixed"):
            barriers.append("multilingual_code_mixing")
        if (payload.get("sign_result") or {}).get("gesture"):
            barriers.append("sign_or_gesture_interaction")
        return json.dumps(
            {
                "barriers_detected": barriers or ["none_detected"],
                "support_applied": [b.replace("_", " ") + " support" for b in barriers] or ["no support needed"],
                "notes": "supportive assistance, not a diagnosis",
            }
        )

    # -- extract_intent --------------------------------------------------------
    @staticmethod
    def _intent(text: str, context: dict = None) -> str:
        return json.dumps(
            {
                "goal": "unknown",
                "action_type": "unknown",
                "entities": {},
                "constraints": [],
                "urgency": "normal",
                "missing_information": [],
            }
        )

    # -- step-by-step cognitive-load simplification -----------------------------
    @staticmethod
    def _simplify(text: str, context: dict = None) -> str:
        parts = [p.strip() for p in re.split(r"[.;]| then | and then ", text) if p.strip()]
        return json.dumps({"steps": parts or [text]})

    # -- generate_caption_summary_action_preview ---------------------------------
    @staticmethod
    def _caption(text: str, context: dict = None) -> str:
        return json.dumps({"caption": text, "summary": text, "action_preview": f"About to act on: {text}"})

    # -- generate_grounded_response ------------------------------------------------
    @staticmethod
    def _response(user: str, context: dict = None) -> str:
        payload = json.loads(user)
        # A domain skill already produced the real result (e.g. a saved
        # reminder) -- surface it, matching what RESPONSE_SYSTEM_PROMPT
        # instructs a real LLM to do ("incorporate it naturally"). Silently
        # dropping this and echoing the transcript instead made completed
        # tasks under the free/offline mock profile look like nothing
        # happened, even when something real (a persisted reminder) did.
        skill_output = payload.get("skill_output")
        if skill_output:
            return skill_output
        return f"Understood: {payload.get('accessible_transcript', '')}"

    # -- decide_recovery_or_confirmation ---------------------------------------------
    @staticmethod
    def _recovery(user: str, context: dict = None) -> str:
        payload = json.loads(user)
        confidence = payload.get("confidence", 1.0)
        missing = payload.get("missing_slots", [])
        needs_confirmation = confidence < config.CONFIDENCE_THRESHOLD or bool(missing)
        return json.dumps(
            {
                "needs_confirmation": needs_confirmation,
                "options": ["confirm", "correct", "retry", "switch_modality"] if needs_confirmation else ["confirm"],
                "reason": "low confidence or missing information" if needs_confirmation else "confidence acceptable",
            }
        )

    # -- select_skill (domain-aware assistance routing, FR-20) ------------------------
    @staticmethod
    def _select_skill(user: str, context: dict = None) -> str:
        payload = json.loads(user)
        text = payload.get("clean_text", "")
        lower = text.lower()
        skills = payload.get("available_skills", [])
        for skill in skills:
            if skill["name"] == "general_help":
                continue
            if any(kw in lower for kw in skill.get("keywords", [])):
                return json.dumps({"skill": skill["name"], "params": {}, "clarify": None})
        if any(s["name"] == "general_help" for s in skills):
            return json.dumps({"skill": "general_help", "params": {"message": text}, "clarify": None})
        return json.dumps({"skill": None, "params": {}, "clarify": "Could you tell me more about what you'd like to do?"})

    # -- agent_step (one step of the multi-step agent loop) --------------------------
    @staticmethod
    def _agent_step(user: str, context: dict = None) -> str:
        """
        Deterministic stand-in for the agent's planner so the loop is
        testable offline. Behaviour: step 1 routes to a matching tool (or
        finishes directly if none matches); step 2 (after an observation)
        finalizes using that observation. Produces a genuine multi-step
        trace, just without real reasoning.
        """
        payload = json.loads(user)
        text = payload.get("user_request", "")
        lower = text.lower()
        tools = payload.get("available_tools", [])
        observations = payload.get("observations_so_far", [])

        if observations:
            last = observations[-1].get("observation", "")
            return json.dumps(
                {
                    "thought": "I have the tool result; finalizing.",
                    "action": "finish",
                    "skill": None,
                    "params": {},
                    "question": None,
                    "answer": f"Based on that: {last}",
                }
            )

        for tool in tools:
            if tool["name"] == "general_help":
                continue
            if any(kw in lower for kw in tool.get("keywords", [])):
                return json.dumps(
                    {
                        "thought": f"'{text}' matches the {tool['name']} tool; calling it.",
                        "action": "call_skill",
                        "skill": tool["name"],
                        "params": {"query": text, "message": text},
                        "question": None,
                        "answer": None,
                    }
                )
        return json.dumps(
            {
                "thought": "No specific tool matches; responding directly.",
                "action": "finish",
                "skill": None,
                "params": {},
                "question": None,
                "answer": f'I heard: "{text}". I don\'t have a specific action for that yet, but I\'m listening.',
            }
        )


class OllamaLLMBackend(LLMBackend):
    """Local-dev / lab-laptop backend using Ollama, model chosen per role
    (see config.OLLAMA_MODELS) -- matches the PRD's distinct cleanup vs.
    reasoning vs. intent vs. response model plan, using what's actually
    pulled on the lab hardware."""

    def __init__(self, role: str = "cleanup"):
        import requests

        self._requests = requests
        self.model = config.OLLAMA_MODELS.get(role, config.OLLAMA_MODELS["cleanup"])

    def complete(self, system: str, user: str, *, task: str = "", context: dict = None) -> str:
        resp = self._requests.post(
            f"{config.OLLAMA_HOST}/api/chat",
            json={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "stream": False,
            },
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()["message"]["content"]


class GenAILabLLMBackend(LLMBackend):
    """Event-day backend -- hosted models via genailab.tcs.in, model chosen
    per role (see config.GENAILAB_MODELS), same client pattern as the
    hackathon's own sample code."""

    def __init__(self, role: str = "cleanup"):
        import httpx
        from langchain_openai import ChatOpenAI

        if not config.GENAILAB_API_KEY:
            raise RuntimeError(
                "LLM_BACKEND=event requires GENAILAB_API_KEY to be set (in .env or the "
                "environment) -- this is the key handed out on match day."
            )
        self.role = role
        self.model = config.GENAILAB_MODELS.get(role, config.GENAILAB_MODELS["cleanup"])
        client = httpx.Client(verify=False)
        self.llm = ChatOpenAI(
            base_url=config.GENAILAB_BASE_URL,
            model=self.model,
            api_key=config.GENAILAB_API_KEY,
            http_client=client,
        )

    def complete(self, system: str, user: str, *, task: str = "", context: dict = None) -> str:
        from src.cost import get_cost_tracker

        tracker = get_cost_tracker()
        prompt = system + "\n" + user
        # Guardrail: refuse the call if it would push us past the budget cap
        # (raises BudgetExceeded, which the pipeline treats as a backend
        # failure and falls back to cached scenarios).
        tracker.check_budget(tracker.estimate_llm_usd(self.model, prompt, prompt))
        response = self.llm.invoke(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ]
        )
        content = response.content
        tracker.record_llm(self.role, self.model, prompt, content)
        return content


def get_llm_backend(role: str = "cleanup") -> LLMBackend:
    """
    role selects both which backend (per the active cost profile, via
    config.resolve_llm_backend) AND which model within that backend (per
    the PRD's model table): "cleanup" | "reasoning" | "intent" |
    "response" | "caption". This is what lets a single run use free local
    Ollama for cleanup/intent but hosted gpt-4o for the final response.
    """
    backend = config.resolve_llm_backend(role)
    if backend == "ollama":
        return OllamaLLMBackend(role)
    if backend == "event":
        return GenAILabLLMBackend(role)
    return MockLLMBackend()
