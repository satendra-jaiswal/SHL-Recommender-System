"""
Build the ChromaDB vector index from data/catalog.json.

Run ONCE locally before committing or deploying:
    python scripts/build_index.py

The resulting data/chroma_db/ directory must be committed to the repo
so HF Spaces starts instantly without rebuilding at runtime.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer

# ── Paths ──────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
CATALOG_PATH = DATA_DIR / "catalog.json"
CHROMA_PATH = DATA_DIR / "chroma_db"
COLLECTION_NAME = "shl_catalog"
EMBEDDING_MODEL = "all-MiniLM-L6-v2"

# ── test_type mapping (from ARCHITECTURE.md Section 5.2) ───────────────────
KEY_TO_CODE: dict[str, str] = {
    "Ability & Aptitude":              "A",
    "Assessment Exercises":            "E",
    "Biodata & Situational Judgment":  "B",
    "Competencies":                    "C",
    "Development & 360":               "D",
    "Knowledge & Skills":              "K",
    "Personality & Behavior":          "P",
    "Simulations":                     "S",
}


def keys_to_test_type(keys: list[str]) -> str:
    """
    Convert a list of key names to comma-joined letter codes.
    e.g. ["Knowledge & Skills", "Simulations"] -> "K,S"
    """
    codes: list[str] = []
    seen: set[str] = set()
    for key in keys:
        code = KEY_TO_CODE.get(key)
        if code and code not in seen:
            codes.append(code)
            seen.add(code)
    return ",".join(codes) if codes else "K"   # default to K if unknown


def build_document_text(item: dict) -> str:
    """
    Build enriched text for embedding (from ARCHITECTURE.md Section 5.3).
    Combining name + keys + job levels + languages + description ensures
    semantic search works for both keyword ("Java") and concept queries
    ("backend developer proficiency").
    """
    name = item.get("name", "")
    keys = item.get("keys", [])
    job_levels = item.get("job_levels", [])
    languages = item.get("languages", [])
    duration = item.get("duration", "")
    description = item.get("description", "")

    # Show first 5 languages, note if more exist
    lang_sample = ", ".join(languages[:5])
    if len(languages) > 5:
        lang_sample += f" (+{len(languages) - 5} more)"

    levels_str = ", ".join(job_levels) if job_levels else "All Levels"
    keys_str = ", ".join(keys) if keys else "General"

    return (
        f"Name: {name}\n"
        f"Test Type: {keys_str}\n"
        f"Job Levels: {levels_str}\n"
        f"Duration: {duration}\n"
        f"Languages: {lang_sample}\n"
        f"Description: {description}"
    ).strip()


def main() -> None:
    # ── 1. Load catalog ────────────────────────────────────────────────────
    if not CATALOG_PATH.exists():
        print(f"ERROR: catalog.json not found at {CATALOG_PATH}")
        print("Run first:  python scripts/catalog_scraper.py")
        sys.exit(1)

    print(f"Loading catalog from {CATALOG_PATH} ...")
    with open(CATALOG_PATH, "r", encoding="utf-8") as f:
        catalog: list[dict] = json.load(f)

    # Keep only items with status=ok
    catalog = [item for item in catalog if item.get("status") == "ok"]
    print(f"  {len(catalog)} items with status=ok")

    # ── 2. Build documents + metadata ─────────────────────────────────────
    documents: list[str] = []
    metadatas: list[dict] = []
    ids: list[str] = []

    for idx, item in enumerate(catalog):
        doc_text = build_document_text(item)
        test_type = keys_to_test_type(item.get("keys", []))

        # Metadata stored alongside each vector in Chroma
        meta = {
            "entity_id": str(item.get("entity_id", idx)),
            "name": item.get("name", ""),
            "url": item.get("link", ""),
            "test_type": test_type,
            "duration": item.get("duration", ""),
            "job_levels": ", ".join(item.get("job_levels", [])),
            "languages": ", ".join(item.get("languages", [])[:10]),
            "keys": ", ".join(item.get("keys", [])),
            # Truncate description to 500 chars for metadata; full version is in doc text
            "description": item.get("description", "")[:500],
        }

        documents.append(doc_text)
        metadatas.append(meta)
        ids.append(f"item_{item.get('entity_id', idx)}")

    # ── 3. Embed ───────────────────────────────────────────────────────────
    print(f"\nLoading embedding model: {EMBEDDING_MODEL} ...")
    model = SentenceTransformer(EMBEDDING_MODEL)

    print(f"Generating embeddings for {len(documents)} documents ...")
    embeddings = model.encode(
        documents,
        show_progress_bar=True,
        batch_size=64,
        convert_to_numpy=True,
    )

    # ── 4. Build Chroma collection ─────────────────────────────────────────
    CHROMA_PATH.mkdir(parents=True, exist_ok=True)
    print(f"\nCreating Chroma collection at {CHROMA_PATH} ...")

    client = chromadb.PersistentClient(path=str(CHROMA_PATH))

    # Drop existing collection if re-running
    try:
        client.delete_collection(COLLECTION_NAME)
        print("  Dropped existing collection.")
    except Exception:
        pass

    collection = client.create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )

    # Add in batches of 100 to stay within Chroma limits
    BATCH = 100
    for start in range(0, len(documents), BATCH):
        end = min(start + BATCH, len(documents))
        collection.add(
            documents=documents[start:end],
            embeddings=embeddings[start:end].tolist(),
            metadatas=metadatas[start:end],
            ids=ids[start:end],
        )
        print(f"  Indexed {end}/{len(documents)} items")

    print(f"\n[OK] Index built successfully!")
    print(f"   Collection : {COLLECTION_NAME}")
    print(f"   Items      : {collection.count()}")
    print(f"   Path       : {CHROMA_PATH}")
    print("\n[WARNING] Commit data/chroma_db/ to your repo before deploying to HF Spaces.")


if __name__ == "__main__":
    main()
