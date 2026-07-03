"""
Agent — the core pipeline for each /chat request.

Pipeline (from ARCHITECTURE.md Section 4 & 6):
  1. Count turns → check turn cap
  2. Build retrieval query from full conversation history
  3. Retrieve top-15 candidates from ChromaDB
  4. Build system prompt (role + catalog context + rules + output format)
  5. Call Gemini 2.5 Flash via LangChain
  6. Parse JSON response
  7. Validate URLs (strip hallucinations) + cap at 10 recommendations
  8. Return ChatResponse
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import List

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

from app.schemas import ChatResponse, Message, Recommendation
from app.retriever import get_retriever
from app.prompt import build_system_prompt, build_retrieval_query

logger = logging.getLogger(__name__)

# ── LLM setup ─────────────────────────────────────────────────────────────
# Temperature 0.2 — consistent, catalog-grounded output, low hallucination risk
# (from ARCHITECTURE.md Key Design Decisions)
LLM_REQUEST_TIMEOUT_SECONDS = 30
_llm: ChatGoogleGenerativeAI | None = None


def get_llm() -> ChatGoogleGenerativeAI:
    global _llm
    if _llm is None:
        api_key = os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            raise RuntimeError(
                "GOOGLE_API_KEY environment variable is not set. "
                "Set it before starting the server."
            )
        _llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            temperature=0.2,
            request_timeout=LLM_REQUEST_TIMEOUT_SECONDS,
            retries=0,
            google_api_key=api_key,
        )
    return _llm


# ── JSON extraction ────────────────────────────────────────────────────────
def extract_json(text: str) -> str:
    """
    Extract JSON from the LLM response.
    Handles cases where the model wraps output in ```json ... ``` fences.
    """
    # Try to find JSON inside code fences
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence_match:
        return fence_match.group(1)

    # Try to find raw JSON object
    brace_match = re.search(r"\{.*\}", text, re.DOTALL)
    if brace_match:
        return brace_match.group(0)

    return text


# ── Response validation ────────────────────────────────────────────────────
def validate_and_clean(data: dict, retriever) -> ChatResponse:
    """
    Validate the LLM's parsed JSON output:
    1. Ensure required fields exist
    2. Strip any URL not in catalog.json (hallucination guard)
    3. Cap recommendations at 10
    """
    reply = str(data.get("reply", "I'm here to help — could you tell me more about the role?"))
    end_of_conversation = bool(data.get("end_of_conversation", False))

    raw_recs = data.get("recommendations", [])
    if not isinstance(raw_recs, list):
        raw_recs = []

    # Validate and clean each recommendation
    clean_recs: list[Recommendation] = []
    for rec in raw_recs[:10]:   # enforce max 10
        if not isinstance(rec, dict):
            continue
        name = str(rec.get("name", "")).strip()
        url = str(rec.get("url", "")).strip()
        test_type = str(rec.get("test_type", "")).strip()

        if not name or not url:
            continue

        # Strip hallucinated URLs — only allow URLs that exist in the catalog
        if not retriever.is_valid_url(url):
            logger.warning("Stripped hallucinated URL: %s (for '%s')", url, name)
            continue

        clean_recs.append(Recommendation(name=name, url=url, test_type=test_type))

    return ChatResponse(
        reply=reply,
        recommendations=clean_recs,
        end_of_conversation=end_of_conversation,
    )


# ── Safe fallback response ─────────────────────────────────────────────────
def _safe_clarify_response(reason: str = "") -> ChatResponse:
    """
    Return a safe CLARIFY response when JSON parsing fails.
    (from ARCHITECTURE.md Section 6.4 edge case)
    """
    msg = (
        "I'd be happy to help you find the right SHL assessments. "
        "Could you tell me more about the role you're hiring for — "
        "the job title, seniority level, and what you're trying to measure?"
    )
    if reason:
        logger.error("Falling back to safe CLARIFY: %s", reason)
    return ChatResponse(reply=msg, recommendations=[], end_of_conversation=False)


# ── Main agent function ────────────────────────────────────────────────────
def run_agent(messages: List[Message]) -> ChatResponse:
    """
    Core agent pipeline. Called by POST /chat.

    Args:
        messages: Full conversation history (user + assistant turns).

    Returns:
        ChatResponse with reply, recommendations, and end_of_conversation flag.
    """
    retriever = get_retriever()
    llm = get_llm()

    # ── Step 1: Turn cap check ─────────────────────────────────────────────
    # Evaluator caps at 8 total turns. Warn at 6 so LLM forces a recommendation.
    total_turns = len(messages)
    logger.info("Turn count: %d", total_turns)

    # ── Step 2: Build retrieval query from full history ────────────────────
    # Concatenate all user messages so accumulated context is captured
    msg_dicts = [{"role": m.role, "content": m.content} for m in messages]
    retrieval_query = build_retrieval_query(msg_dicts)
    logger.info("Retrieval query: %s", retrieval_query[:100])

    # ── Step 3: Retrieve top-15 candidates from ChromaDB ──────────────────
    # k=15 over-retrieves so the LLM can reason about relevance and pick 1-10
    catalog_items = retriever.retrieve(retrieval_query, k=15)
    logger.info("Retrieved %d catalog items", len(catalog_items))

    # ── Step 4: Build system prompt ────────────────────────────────────────
    system_prompt = build_system_prompt(
        catalog_items=catalog_items,
        total_turns=total_turns,
    )

    # ── Step 5: Build LangChain message list ──────────────────────────────
    lc_messages = [SystemMessage(content=system_prompt)]
    for msg in messages:
        if msg.role == "user":
            lc_messages.append(HumanMessage(content=msg.content))
        else:
            lc_messages.append(AIMessage(content=msg.content))

    # ── Step 6: Call Gemini 2.5 Flash ─────────────────────────────────────
    logger.info("Calling LLM (%d messages in context)", len(lc_messages))
    try:
        response = llm.invoke(lc_messages)
        raw_text = response.content
        logger.debug("LLM raw response: %s", raw_text[:300])
    except Exception as e:
        logger.error("LLM call failed: %s", e)
        return _safe_clarify_response(reason=str(e))

    # ── Step 7: Parse JSON response ────────────────────────────────────────
    # Attempt 1
    json_str = extract_json(raw_text)
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError:
        # Attempt 2 — retry the LLM with explicit JSON instruction
        logger.warning("JSON parse failed on attempt 1. Retrying LLM...")
        retry_messages = lc_messages + [
            AIMessage(content=raw_text),
            HumanMessage(content=(
                "Your previous response was not valid JSON. "
                "Please respond ONLY with valid JSON matching the required schema. "
                "No explanation, no code fences — just raw JSON."
            )),
        ]
        try:
            retry_response = llm.invoke(retry_messages)
            json_str2 = extract_json(retry_response.content)
            data = json.loads(json_str2)
        except Exception as e2:
            logger.error("JSON parse failed on attempt 2: %s", e2)
            return _safe_clarify_response(reason=f"JSON parse error: {e2}")

    # ── Step 8: Validate + return ─────────────────────────────────────────
    return validate_and_clean(data, retriever)
