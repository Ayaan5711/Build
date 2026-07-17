import json
import os
from dataclasses import dataclass
from typing import List

import chromadb

from src import config
from src.knowledge.embeddings import get_embedding_function

_SEED_DATA_PATH = os.path.join(os.path.dirname(__file__), "seed_data", "accessibility_knowledge.json")
_CLASSROOM_SEED_DATA_PATH = os.path.join(os.path.dirname(__file__), "seed_data", "classroom_knowledge.json")


@dataclass
class RetrievedSnippet:
    source: str
    title: str
    content: str


class KnowledgeBase:
    """
    Curated RAG knowledge base (FR-12): accessibility guidance (PAS 901),
    FAQs, workflow steps, and domain content. Shown transparently to the
    user (dashboard "View Retrieved Context") per Appendix B -- "keep RAG
    sources curated and show retrieved snippets transparently".

    New domain content for a match-day use case gets added the same way
    skills are added: call seed() with more entries, no code changes.
    """

    def __init__(self, collection_name: str = "knowledge_base"):
        self.client = chromadb.PersistentClient(path=config.CHROMA_PERSIST_DIR)
        self.collection = self.client.get_or_create_collection(collection_name, embedding_function=get_embedding_function())

    def seed(self, entries: List[dict]):
        """entries: [{"id": str, "source": str, "title": str, "content": str}]"""
        if not entries:
            return
        self.collection.upsert(
            ids=[e["id"] for e in entries],
            documents=[e["content"] for e in entries],
            metadatas=[{"source": e["source"], "title": e["title"]} for e in entries],
        )

    def retrieve(self, query: str, k: int = 3) -> List[RetrievedSnippet]:
        if not query or self.collection.count() == 0:
            return []
        results = self.collection.query(query_texts=[query], n_results=min(k, self.collection.count()))
        snippets = []
        for doc, meta in zip(results["documents"][0], results["metadatas"][0]):
            snippets.append(RetrievedSnippet(source=meta.get("source", "unknown"), title=meta.get("title", ""), content=doc))
        return snippets


def rag_retrieve(query: str, kb: KnowledgeBase, k: int = 3) -> List[RetrievedSnippet]:
    """Alias matching the PRD's Appendix A pseudocode naming."""
    return kb.retrieve(query, k=k)


def seed_default_knowledge_base(kb: KnowledgeBase):
    """
    Loads PAS 901 guidance + generic accessibility FAQs (curated ahead of
    match day, per the team's own research notes) into the knowledge base.
    Real domain content for the assigned use case gets added the exact same
    way -- more entries via kb.seed(), no code changes -- mirroring how new
    skills are added in src/skills/.
    """
    with open(_SEED_DATA_PATH) as f:
        entries = json.load(f)
    kb.seed(entries)


def seed_classroom_knowledge_base(kb: KnowledgeBase):
    """
    Match-day domain content for the classroom/education use case (static,
    scripted-for-demo facts like today's absent students -- not date-aware
    the way src/integrations/class_schedule.py's real timetable lookups
    are, since "who's absent" doesn't have a real live attendance system
    behind it here). Same additive kb.seed() pattern as
    seed_default_knowledge_base -- called alongside it, not instead of it.
    """
    with open(_CLASSROOM_SEED_DATA_PATH) as f:
        entries = json.load(f)
    kb.seed(entries)
