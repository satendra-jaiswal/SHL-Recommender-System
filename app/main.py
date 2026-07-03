"""
FastAPI application — /health and /chat endpoints.

Startup:
  - Loads ChromaDB retriever singleton (loads embedding model + opens Chroma)
  - The index must already exist at data/chroma_db/ (pre-built by build_index.py)

Endpoints:
  GET  /health  →  {"status": "ok"}
  POST /chat    →  ChatResponse
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from app.schemas import ChatRequest, ChatResponse, HealthResponse
from app.agent import run_agent
from app.retriever import get_retriever

# Load environment variables from .env file (local dev only)
load_dotenv()

# ── Logging ────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


# ── Lifespan (startup) ─────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Load the retriever (ChromaDB + embedding model) once at startup.
    This ensures /health responds instantly and the first /chat call
    does not bear the model loading cost.
    """
    logger.info("Starting SHL Recommender — loading retriever ...")
    try:
        retriever = get_retriever()
        logger.info("Retriever ready. Catalog items: %d", retriever._collection.count())
    except Exception as e:
        logger.error("Failed to load retriever: %s", e)
        logger.error(
            "Make sure data/chroma_db/ exists. Run: python scripts/build_index.py"
        )
    yield
    logger.info("Shutting down SHL Recommender.")


# ── FastAPI app ────────────────────────────────────────────────────────────
app = FastAPI(
    title="SHL Assessment Recommender",
    description=(
        "Conversational API that recommends SHL assessments based on "
        "job descriptions and hiring needs."
    ),
    version="1.0.0",
    lifespan=lifespan,
)


# ── Endpoints ──────────────────────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health() -> HealthResponse:
    """
    Health check endpoint.
    Called by the evaluator on startup to confirm the service is running.
    Returns {"status": "ok"} immediately.
    """
    return HealthResponse(status="ok")


@app.post("/chat", response_model=ChatResponse, tags=["Chat"])
async def chat(request: ChatRequest) -> ChatResponse:
    """
    Main chat endpoint.

    Accepts the full conversation history and returns:
    - reply: next assistant message
    - recommendations: 0–10 SHL assessments ([] when clarifying or refusing)
    - end_of_conversation: true only when user confirms final shortlist
    """
    logger.info(
        "POST /chat — %d messages, last user: '%s'",
        len(request.messages),
        request.messages[-1].content[:80] if request.messages else "",
    )

    try:
        response = run_agent(request.messages)
        logger.info(
            "Response — recs: %d, eoc: %s",
            len(response.recommendations),
            response.end_of_conversation,
        )
        return response
    except Exception as e:
        logger.exception("Unhandled error in /chat: %s", e)
        # Return a safe response rather than exposing internal errors
        return ChatResponse(
            reply=(
                "I'm having a technical issue right now. "
                "Please try again in a moment."
            ),
            recommendations=[],
            end_of_conversation=False,
        )


# ── Global exception handler ───────────────────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled exception: %s", exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error. Please try again."},
    )


# ── Entry point for local dev ──────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=True)
