from typing import Literal
from pydantic import BaseModel, Field


class IngestionResponse(BaseModel):
    document_id: str
    filename: str
    strategy: Literal["fixed", "recursive"]
    chunks_stored: int


class ChatRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
    message: str = Field(min_length=1, max_length=4000)


class Source(BaseModel):
    document_id: str
    filename: str
    score: float
    excerpt: str


class ChatResponse(BaseModel):
    session_id: str
    answer: str
    sources: list[Source] = Field(default_factory=list)
    booking_id: str | None = None
