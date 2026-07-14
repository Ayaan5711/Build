import json
import re

from src import config


class LLMBackend:
    def complete(self, system: str, user: str, *, task: str = "", context: dict = None) -> str:
        raise NotImplementedError


class MockLLMBackend(LLMBackend):
    """
    Deterministic, model-free stand-in so the pipeline can be built and
    smoke-tested in environments with no LLM access at all (e.g. a sandbox
    with no route to Ollama or genailab.tcs.in). It does NOT do real
    language understanding -- it's plumbing verification only. Switch
    LLM_BACKEND to "ollama" (local dev) or "event" (match day) for the
    real thing.
    """

    def complete(self, system: str, user: str, *, task: str = "", context: dict = None) -> str:
        if task == "equalizer":
            return self._equalize(user, context)
        if task == "normalize":
            return self._normalize(user)
        if task == "orchestrate":
            return self._orchestrate(user)
        if task == "guardrail":
            return self._guardrail(user)
        return user

    @staticmethod
    def _equalize(text: str, context: dict = None) -> str:
        # Personalization: apply any per-user corrections learned from past
        # confirmations (e.g. a name the ASR keeps mangling) before the
        # generic stutter cleanup below.
        for wrong, right in (context or {}).items():
            text = re.sub(re.escape(wrong), right, text, flags=re.IGNORECASE)
        # Collapse "M-m-my" / "na-name i-is" style stutter artifacts and
        # immediate word repeats -- a rough stand-in for an LLM cleanup pass.
        text = re.sub(r"\b(\w)(-\1)+\b", r"\1", text, flags=re.IGNORECASE)
        text = re.sub(r"\b(\w+)-\1\b", r"\1", text, flags=re.IGNORECASE)
        words = text.split()
        deduped = []
        for w in words:
            if not deduped or deduped[-1].lower().rstrip(",.") != w.lower().rstrip(",."):
                deduped.append(w)
        return " ".join(deduped)

    @staticmethod
    def _normalize(text: str) -> str:
        return json.dumps(
            {
                "intent": "unknown",
                "entities": {},
                "languages_detected": ["en"],
                "clean_text": text,
            }
        )

    @staticmethod
    def _orchestrate(user: str) -> str:
        payload = json.loads(user)
        text = payload.get("clean_text", "")
        lower = text.lower()
        skills = payload.get("available_skills", [])
        for skill in skills:
            if skill["name"] == "general_help":
                continue  # tried last, as the explicit fallback
            if any(kw in lower for kw in skill.get("keywords", [])):
                return json.dumps({"skill": skill["name"], "params": {}, "clarify": None})
        if any(s["name"] == "general_help" for s in skills):
            return json.dumps({"skill": "general_help", "params": {"message": text}, "clarify": None})
        return json.dumps(
            {
                "skill": None,
                "params": {},
                "clarify": "Could you tell me more about what you'd like to do?",
            }
        )

    @staticmethod
    def _guardrail(user: str) -> str:
        payload = json.loads(user)
        approved = payload.get("confidence", 0) >= config.CONFIDENCE_THRESHOLD
        reason = "confidence above threshold" if approved else "confidence below threshold, needs confirmation"
        return json.dumps({"approved": approved, "reason": reason})


class OllamaLLMBackend(LLMBackend):
    """Local-dev backend using an Ollama server -- the same offline SLM
    stack (Llama-3.2-3B etc.) available on the event lab laptops."""

    def __init__(self):
        import requests

        self._requests = requests

    def complete(self, system: str, user: str, *, task: str = "", context: dict = None) -> str:
        resp = self._requests.post(
            f"{config.OLLAMA_HOST}/api/chat",
            json={
                "model": config.OLLAMA_MODEL,
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
    """Event-day backend -- hosted models via genailab.tcs.in, same client
    pattern as the hackathon's own sample code."""

    def __init__(self):
        import httpx
        from langchain_openai import ChatOpenAI

        if not config.GENAILAB_API_KEY:
            raise RuntimeError(
                "LLM_BACKEND=event requires GENAILAB_API_KEY to be set (in .env or the "
                "environment) -- this is the key handed out on match day."
            )
        client = httpx.Client(verify=False)
        self.llm = ChatOpenAI(
            base_url=config.GENAILAB_BASE_URL,
            model=config.GENAILAB_CHAT_MODEL,
            api_key=config.GENAILAB_API_KEY,
            http_client=client,
        )

    def complete(self, system: str, user: str, *, task: str = "", context: dict = None) -> str:
        response = self.llm.invoke(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ]
        )
        return response.content


def get_llm_backend() -> LLMBackend:
    if config.LLM_BACKEND == "ollama":
        return OllamaLLMBackend()
    if config.LLM_BACKEND == "event":
        return GenAILabLLMBackend()
    return MockLLMBackend()
