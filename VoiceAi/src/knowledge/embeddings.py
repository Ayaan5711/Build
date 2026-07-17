from chromadb.api.types import EmbeddingFunction

from src import config


class MockEmbeddingFunction(EmbeddingFunction):
    """Deterministic bag-of-words hash embedding -- no model/network
    dependency, so RAG retrieval is testable offline. Swap EMBED_BACKEND
    to "ollama" (gte-large, local) or "event" (genailab, hosted) for real
    semantic search."""

    def __init__(self):
        pass

    def __call__(self, input):
        import hashlib

        import numpy as np

        vectors = []
        for text in input:
            vec = np.zeros(256)
            for token in text.lower().split():
                idx = int(hashlib.md5(token.encode()).hexdigest(), 16) % 256
                vec[idx] += 1
            norm = np.linalg.norm(vec)
            vectors.append((vec / norm if norm else vec).tolist())
        return vectors

    @staticmethod
    def name() -> str:
        return "voiceai_mock_embedding"

    def get_config(self):
        return {}

    @staticmethod
    def build_from_config(config_dict):
        return MockEmbeddingFunction()


class OllamaEmbeddingFunction(EmbeddingFunction):
    """Offline fallback using Ollama's locally-pulled gte-large model --
    the PRD's own knowledge-retrieval model choice, run locally so RAG
    keeps working even if genailab.tcs.in is unreachable."""

    def __init__(self):
        import requests

        self._requests = requests

    def __call__(self, input):
        vectors = []
        for text in input:
            resp = self._requests.post(
                f"{config.OLLAMA_HOST}/api/embeddings",
                json={"model": config.OLLAMA_EMBED_MODEL, "prompt": text},
                timeout=30,
            )
            resp.raise_for_status()
            vectors.append(resp.json()["embedding"])
        return vectors

    @staticmethod
    def name() -> str:
        return "voiceai_ollama_embedding"

    def get_config(self):
        return {}

    @staticmethod
    def build_from_config(config_dict):
        return OllamaEmbeddingFunction()


class GenAILabEmbeddingFunction(EmbeddingFunction):
    def __init__(self):
        import httpx

        if not config.GENAILAB_API_KEY:
            raise RuntimeError(
                "EMBED_BACKEND=event requires GENAILAB_API_KEY to be set (in .env or the "
                "environment) -- this is the key handed out on match day."
            )
        # Same missing-timeout fix as the ASR/LLM clients -- httpx's 5s
        # default is too short for real hosted inference under load.
        self.client = httpx.Client(verify=False, timeout=config.GENAILAB_TIMEOUT_S)

    def __call__(self, input):
        from src.cost import get_cost_tracker

        tracker = get_cost_tracker()
        tracker.check_budget()
        resp = self.client.post(
            f"{config.GENAILAB_BASE_URL}/v1/embeddings",
            headers={"Authorization": f"Bearer {config.GENAILAB_API_KEY}"},
            json={"model": config.GENAILAB_EMBED_MODEL, "input": input},
        )
        resp.raise_for_status()
        tracker.record_embedding("embedding", config.GENAILAB_EMBED_MODEL, list(input))
        return [item["embedding"] for item in resp.json()["data"]]

    @staticmethod
    def name() -> str:
        return "voiceai_genailab_embedding"

    def get_config(self):
        return {}

    @staticmethod
    def build_from_config(config_dict):
        return GenAILabEmbeddingFunction()


def get_embedding_function():
    if config.EMBED_BACKEND == "event":
        return GenAILabEmbeddingFunction()
    if config.EMBED_BACKEND == "ollama":
        return OllamaEmbeddingFunction()
    return MockEmbeddingFunction()
