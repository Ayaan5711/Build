import chromadb

from src import config
from src.knowledge.embeddings import get_embedding_function


class UserMemory:
    """
    Per-user correction history: once a user confirms a fix (e.g.
    "Ka-ka-Kiran" -> "Kiran"), it's remembered and applied automatically by
    normalize_transcript() on future turns, instead of relying on the LLM
    to guess it again every time. Separate from the shared KnowledgeBase
    (rag.py), which is curated content common to all users.
    """

    def __init__(self, user_id: str):
        self.user_id = user_id
        self.client = chromadb.PersistentClient(path=config.CHROMA_PERSIST_DIR)
        self.corrections = self.client.get_or_create_collection(
            f"corrections_{user_id}", embedding_function=get_embedding_function()
        )

    def add_correction(self, original: str, corrected: str):
        self.corrections.upsert(ids=[original], documents=[original], metadatas=[{"corrected": corrected}])

    def get_known_corrections(self) -> dict:
        data = self.corrections.get()
        return {doc: meta["corrected"] for doc, meta in zip(data["documents"], data["metadatas"])}
