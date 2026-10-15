from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, AsyncIterator

import logging
from fastapi import FastAPI, File, Form, HTTPException, UploadFile, Request
from fastapi.responses import JSONResponse
from openai import APIError
from redis.exceptions import RedisError, LockError
from sqlalchemy.exc import SQLAlchemyError
from qdrant_client.http.exceptions import UnexpectedResponse, ResponseHandlingException
from openai import AsyncOpenAI
from qdrant_client import AsyncQdrantClient
from redis.asyncio import Redis

from app.chunking import Strategy
from app.config import settings
from app.database import SessionLocal, init_db
from app.schemas import ChatRequest, ChatResponse, IngestionResponse
from app.services import Services


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    init_db()
    llm = AsyncOpenAI(api_key=settings.openai_api_key, base_url=settings.openai_base_url, timeout=120, max_retries=0)
    qdrant = AsyncQdrantClient(url=settings.qdrant_url)
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    service = Services(llm, qdrant, redis)
    try:
        await service.prepare_collection()
        await redis.ping()
        app.state.services = service
        yield
    finally:
        await redis.aclose()
        await qdrant.close()
        await llm.close()


app = FastAPI(title="Palm Mind AI - Conversational RAG", version="1.0.0", lifespan=lifespan)


@app.exception_handler(APIError)
@app.exception_handler(RedisError)
@app.exception_handler(LockError)
@app.exception_handler(SQLAlchemyError)
@app.exception_handler(UnexpectedResponse)
@app.exception_handler(ResponseHandlingException)
async def dependency_error(request: Request, exc: Exception) -> JSONResponse:
    logging.getLogger(__name__).error("Dependency failure on %s: %s", request.url.path, type(exc).__name__)
    return JSONResponse(status_code=503, content={"detail": "A required local service is unavailable. Check Ollama models, Qdrant, Redis and SQLite; then retry."})


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
        raise HTTPException(413, f"File exceeds {settings.max_upload_bytes} byte limit")
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
