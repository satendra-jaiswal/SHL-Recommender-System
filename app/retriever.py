"""
Retriever — loads the pre-built ChromaDB index at startup and exposes:
  - retrieve(query, k)  → list of catalog item dicts
  - is_valid_url(url)   → bool (used to strip LLM hallucinations)

Loaded once at application startup as a singleton.
Every /chat request reuses the same in-memory index.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

# ── Paths ──────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
CHROMA_PATH = DATA_DIR / "chroma_db"
CATALOG_PATH = DATA_DIR / "catalog.json"
COLLECTION_NAME = "shl_catalog"
EMBEDDING_MODEL = "all-MiniLM-L6-v2"


class Retriever:
    """
    Wraps ChromaDB + sentence-transformers for catalog retrieval.

    On init:
      1. Loads embedding model (cached by sentence-transformers after first load)
      2. Opens the pre-built Chroma persistent collection
      3. Builds an in-memory set of all valid catalog URLs for post-LLM validation
    """

    def __init__(self) -> None:
        logger.info("Loading embedding model: %s", EMBEDDING_MODEL)
        self._model = SentenceTransformer(EMBEDDING_MODEL)

        if not CHROMA_PATH.exists():
            raise RuntimeError(
                f"Chroma index not found at {CHROMA_PATH}. "
                "Run:  python scripts/build_index.py"
            )

        logger.info("Opening Chroma collection from %s", CHROMA_PATH)
        self._client = chromadb.PersistentClient(path=str(CHROMA_PATH))
        self._collection = self._client.get_collection(COLLECTION_NAME)
        logger.info("Collection loaded: %d items", self._collection.count())

        # Build URL validation set from catalog.json (used by is_valid_url)
        logger.info("Building URL validation index from %s", CATALOG_PATH)
        with open(CATALOG_PATH, "r", encoding="utf-8") as f:
            catalog: list[dict] = json.load(f)

        self._valid_urls: set[str] = {
            item["link"]
            for item in catalog
            if item.get("status") == "ok" and item.get("link")
        }
        logger.info("Retriever ready — %d valid URLs indexed.", len(self._valid_urls))

    # ── Public API ─────────────────────────────────────────────────────────

    def retrieve(self, query: str, k: int = 15) -> list[dict]:
        """
        Embed the query and return top-k most similar catalog items.

        Returns a list of dicts with keys:
          name, url, test_type, duration, job_levels, languages, keys, description
        """
        if not query.strip():
            return []

        k = min(k, self._collection.count())
        if k == 0:
            return []

        query_embedding = self._model.encode([query])[0].tolist()

        results = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=k,
            include=["metadatas", "documents"],
        )

        items: list[dict] = []
        if results and results.get("metadatas"):
            for meta in results["metadatas"][0]:
                items.append({
                    "name":        meta.get("name", ""),
                    "url":         meta.get("url", ""),
                    "test_type":   meta.get("test_type", "K"),
                    "duration":    meta.get("duration", ""),
                    "job_levels":  meta.get("job_levels", ""),
                    "languages":   meta.get("languages", ""),
                    "keys":        meta.get("keys", ""),
                    "description": meta.get("description", ""),
                })
        return items

    def is_valid_url(self, url: str) -> bool:
        """Return True only if the URL exists in the scraped catalog."""
        return url in self._valid_urls

    def get_all_valid_urls(self) -> set[str]:
        """Return the full set of valid catalog URLs."""
        return self._valid_urls


# ── Singleton ──────────────────────────────────────────────────────────────
# Initialized once at app startup via get_retriever()
_instance: Retriever | None = None


def get_retriever() -> Retriever:
    global _instance
    if _instance is None:
        _instance = Retriever()
    return _instance
