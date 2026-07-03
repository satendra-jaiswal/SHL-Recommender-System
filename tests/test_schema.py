"""
Hard eval tests — schema compliance and URL validation.

These must ALL pass before submission.
Run: pytest tests/test_schema.py -v
"""
from __future__ import annotations

import json
import pytest
from pathlib import Path
from fastapi.testclient import TestClient

from app.main import app
from app.schemas import ChatResponse, Recommendation

ROOT = Path(__file__).resolve().parent.parent
CATALOG_PATH = ROOT / "data" / "catalog.json"

client = TestClient(app)


# ── Load valid URLs for validation ─────────────────────────────────────────
@pytest.fixture(scope="session")
def valid_urls() -> set[str]:
    with open(CATALOG_PATH, "r", encoding="utf-8") as f:
        catalog = json.load(f)
    return {item["link"] for item in catalog if item.get("status") == "ok" and item.get("link")}


# ── /health tests ──────────────────────────────────────────────────────────
def test_health_returns_200():
    resp = client.get("/health")
    assert resp.status_code == 200


def test_health_returns_ok():
    resp = client.get("/health")
    data = resp.json()
    assert data == {"status": "ok"}, f"Expected {{'status': 'ok'}}, got {data}"


# ── /chat schema tests ─────────────────────────────────────────────────────
def _chat(messages: list[dict]) -> dict:
    resp = client.post("/chat", json={"messages": messages})
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    return resp.json()


def test_chat_response_has_required_fields():
    data = _chat([{"role": "user", "content": "I need an assessment"}])
    assert "reply" in data, "Missing 'reply' field"
    assert "recommendations" in data, "Missing 'recommendations' field"
    assert "end_of_conversation" in data, "Missing 'end_of_conversation' field"


def test_chat_reply_is_string():
    data = _chat([{"role": "user", "content": "I need an assessment"}])
    assert isinstance(data["reply"], str), f"reply must be str, got {type(data['reply'])}"
    assert len(data["reply"]) > 0, "reply must not be empty"


def test_chat_recommendations_is_list():
    data = _chat([{"role": "user", "content": "I need an assessment"}])
    assert isinstance(data["recommendations"], list), "recommendations must be a list"


def test_chat_end_of_conversation_is_bool():
    data = _chat([{"role": "user", "content": "I need an assessment"}])
    assert isinstance(data["end_of_conversation"], bool), "end_of_conversation must be bool"


def test_recommendations_max_10(valid_urls):
    # Use a detailed query likely to get many results
    data = _chat([{
        "role": "user",
        "content": (
            "We need assessments for a mid-level software engineer — "
            "Java, Python, SQL, personality, cognitive ability."
        )
    }])
    recs = data["recommendations"]
    assert len(recs) <= 10, f"Got {len(recs)} recommendations — max is 10"


def test_recommendation_fields(valid_urls):
    data = _chat([{
        "role": "user",
        "content": (
            "Hiring a senior Java backend engineer. "
            "Need cognitive and personality assessments."
        )
    }])
    recs = data["recommendations"]
    for rec in recs:
        assert "name" in rec, f"Recommendation missing 'name': {rec}"
        assert "url" in rec, f"Recommendation missing 'url': {rec}"
        assert "test_type" in rec, f"Recommendation missing 'test_type': {rec}"
        assert isinstance(rec["name"], str) and rec["name"], "name must be non-empty string"
        assert isinstance(rec["url"], str) and rec["url"], "url must be non-empty string"
        assert isinstance(rec["test_type"], str), "test_type must be string"


def test_all_urls_in_catalog(valid_urls):
    """
    Critical: every URL in recommendations must exist in catalog.json.
    Hallucinated URLs are a hard eval failure.
    """
    data = _chat([{
        "role": "user",
        "content": (
            "Hiring senior Java backend engineer with Spring Boot, SQL, AWS. "
            "Need cognitive and personality assessments."
        )
    }])
    recs = data["recommendations"]
    for rec in recs:
        url = rec["url"]
        assert url in valid_urls, (
            f"URL not in catalog: {url}\n"
            f"Assessment: {rec['name']}\n"
            "This is a hallucinated URL — hard eval failure."
        )


def test_empty_messages_returns_400():
    resp = client.post("/chat", json={"messages": []})
    assert resp.status_code == 422, f"Expected 422 for empty messages, got {resp.status_code}"


def test_last_message_must_be_user():
    resp = client.post("/chat", json={
        "messages": [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "How can I help?"},
        ]
    })
    # Last message is assistant — should be rejected
    assert resp.status_code == 422, f"Expected 422, got {resp.status_code}"


def test_parse_as_chat_response():
    """Ensure the response can be parsed by the ChatResponse Pydantic model."""
    data = _chat([{"role": "user", "content": "I need an assessment for a sales manager"}])
    # This will raise if the schema doesn't match
    parsed = ChatResponse(**data)
    assert parsed.reply
