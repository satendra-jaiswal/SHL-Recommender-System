"""
Pydantic models for the SHL Assessment Recommender API.
Schema is NON-NEGOTIABLE — deviating breaks the automated evaluator.

POST /chat expects ChatRequest, returns ChatResponse.
GET  /health returns {"status": "ok"}
"""
from __future__ import annotations

from typing import List, Literal
from pydantic import BaseModel, field_validator


class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    messages: List[Message]

    @field_validator("messages")
    @classmethod
    def messages_not_empty(cls, v: List[Message]) -> List[Message]:
        if not v:
            raise ValueError("messages must not be empty")
        if v[-1].role != "user":
            raise ValueError("last message must be from the user")
        return v


class Recommendation(BaseModel):
    name: str
    url: str
    test_type: str   # e.g. "K", "P", "A", "K,S"


class ChatResponse(BaseModel):
    reply: str
    recommendations: List[Recommendation] = []
    end_of_conversation: bool = False


class HealthResponse(BaseModel):
    status: str = "ok"
