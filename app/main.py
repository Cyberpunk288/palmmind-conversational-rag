from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, AsyncIterator

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from openai import AsyncOpenAI
from qdrant_client import AsyncQdrantClient
from redis.asyncio import Redis
from sqlalchemy.orm import Session

from app.chunking import Strategy
from app.config import settings
from app.database import SessionLocal, init_db
from app.schemas import ChatRequest, ChatResponse, IngestionResponse
from app.services import Services


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    init_db()
    llm = AsyncOpenAI(api_key=settings.openai_api_key)
    qdrant = AsyncQdrantClient(url=settings.qdrant_url)
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    service = Services(llm, qdrant, redis)
    await service.prepare_collection()
    await redis.ping()
    app.state.services = service
    try:
        yield
    finally:
        await redis.aclose()
        await qdrant.close()
        await llm.close()


app = FastAPI(title="Palm Mind AI - Conversational RAG", version="1.0.0", lifespan=lifespan)


@app.get("/health", tags=["System"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/v1/documents/ingest", response_model=IngestionResponse, tags=["Document Ingestion"])
async def ingest_document(
    file: Annotated[UploadFile, File(description="PDF or UTF-8 TXT file")],
    strategy: Annotated[Strategy, Form(description="fixed or recursive")] = "recursive",
) -> IngestionResponse:
    filename = Path(file.filename or "").name
    if not filename.lower().endswith((".pdf", ".txt")):
        raise HTTPException(415, "Only .pdf and .txt files are supported")
    contents = await file.read(settings.max_upload_bytes + 1)
    await file.close()
    if len(contents) > settings.max_upload_bytes:
        raise HTTPException(413, "File exceeds 10 MB limit")
    if not contents:
        raise HTTPException(422, "Empty file")
    with SessionLocal() as db:
        doc_id, count = await app.state.services.ingest(filename, contents, strategy, db)
    return IngestionResponse(document_id=doc_id, filename=filename, strategy=strategy, chunks_stored=count)


@app.post("/api/v1/chat", response_model=ChatResponse, tags=["Conversational RAG"])
async def chat(payload: ChatRequest) -> ChatResponse:
    with SessionLocal() as db:
        answer, sources, booking_id = await app.state.services.conversation(payload.session_id, payload.message, db)
    return ChatResponse(session_id=payload.session_id, answer=answer, sources=sources, booking_id=booking_id)
