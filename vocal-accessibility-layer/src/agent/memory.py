import hashlib

import chromadb
from chromadb.api.types import EmbeddingFunction

from src import config


class MockEmbeddingFunction(EmbeddingFunction):
    """
    Deterministic bag-of-words hash embedding -- no model or network
    dependency, so retrieval wiring can be tested offline. Swap
    EMBED_BACKEND to "event" for real semantic search via genailab's
    text-embedding-3-large.
    """

    def __init__(self):
        pass

    def __call__(self, input):
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
        return "vocal_accessibility_mock_embedding"

    def get_config(self):
        return {}

    @staticmethod
    def build_from_config(config_dict):
        return MockEmbeddingFunction()


class GenAILabEmbeddingFunction(EmbeddingFunction):
    def __init__(self):
        import httpx

        self.client = httpx.Client(verify=False)

    def __call__(self, input):
        resp = self.client.post(
            f"{config.GENAILAB_BASE_URL}/v1/embeddings",
            headers={"Authorization": f"Bearer {config.GENAILAB_API_KEY}"},
            json={"model": config.GENAILAB_EMBED_MODEL, "input": input},
        )
        resp.raise_for_status()
        return [item["embedding"] for item in resp.json()["data"]]

    @staticmethod
    def name() -> str:
        return "vocal_accessibility_genailab_embedding"

    def get_config(self):
        return {}

    @staticmethod
    def build_from_config(config_dict):
        return GenAILabEmbeddingFunction()


def _get_embedding_function():
    if config.EMBED_BACKEND == "event":
        return GenAILabEmbeddingFunction()
    return MockEmbeddingFunction()


class Memory:
    """
    Per-user profile: a correction history (fed back from the Speech
    Equalizer when a user confirms a fix, so the same word gets recognized
    correctly next time) and a small FAQ knowledge base, both retrieved via
    embeddings so the orchestrator/guardrail can reuse prior resolutions
    instead of asking the same clarifying question twice.
    """

    def __init__(self, user_id: str):
        self.user_id = user_id
        embedding_fn = _get_embedding_function()
        self.client = chromadb.PersistentClient(path=config.CHROMA_PERSIST_DIR)
        self.corrections = self.client.get_or_create_collection(
            f"corrections_{user_id}", embedding_function=embedding_fn
        )
        self.faq = self.client.get_or_create_collection("faq", embedding_function=embedding_fn)

    def add_correction(self, original: str, corrected: str):
        self.corrections.upsert(ids=[original], documents=[original], metadatas=[{"corrected": corrected}])

    def get_known_corrections(self) -> dict:
        data = self.corrections.get()
        return {doc: meta["corrected"] for doc, meta in zip(data["documents"], data["metadatas"])}

    def seed_faq(self, entries: list):
        if not entries:
            return
        self.faq.upsert(
            ids=[e["question"] for e in entries],
            documents=[e["question"] for e in entries],
            metadatas=[{"answer": e["answer"]} for e in entries],
        )

    def search_faq(self, query: str, k: int = 1) -> list:
        if self.faq.count() == 0:
            return []
        results = self.faq.query(query_texts=[query], n_results=min(k, self.faq.count()))
        return [
            {"question": doc, "answer": meta["answer"]}
            for doc, meta in zip(results["documents"][0], results["metadatas"][0])
        ]
