# Palm Mind AI - Conversational RAG Backend

FastAPI backend for PDF/TXT ingestion, document-grounded multi-turn chat and interview booking. All inference runs locally with Ollama; no paid API key is required.

## Architecture

- Upload -> pypdf/UTF-8 extraction -> fixed or recursive chunks with overlap -> `nomic-embed-text` embeddings (768 dimensions) -> Qdrant.
- SQLite/SQLAlchemy persists document metadata and confirmed interview bookings.
- Chat -> Redis history -> LLM booking extraction, or history-aware standalone query -> Qdrant retrieval -> custom grounded generation with `qwen2.5:1.5b` and source excerpts.
- Redis stores a separate booking draft, confirmation status and completed booking ID. A per-session Redis lock serializes turns. SQL lookup prevents identical booking retries from inserting duplicates.

No RetrievalQAChain, FAISS, Chroma or frontend is used. The OpenAI Python SDK is only a client for the local Ollama `/v1` API. Booking extraction uses JSON object mode, not function calling or unsupported strict JSON-schema options. See [Ollama compatibility](https://docs.ollama.com/api/openai-compatibility).

## Setup (Windows / PowerShell)

Requires Python 3.11, Docker Desktop and [Ollama](https://ollama.com/download/windows). Start Docker Desktop and Ollama first.

```powershell
git clone https://github.com/Cyberpunk288/palmmind-conversational-rag.git
cd palmmind-conversational-rag
git switch development
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env  # New installations only; preserve existing local settings.
docker compose up -d
ollama pull qwen2.5:1.5b
ollama pull nomic-embed-text
ollama list
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Ollama normally runs as a background application; use `ollama serve` if it is not running. Swagger: http://127.0.0.1:8000/docs. Liveness: http://127.0.0.1:8000/health. The health endpoint is a liveness check, not a model readiness check. Startup checks Qdrant and Redis, so start them before FastAPI.

If Windows application control blocks SQLAlchemy compiled extensions, set `$env:DISABLE_SQLALCHEMY_CEXT_RUNTIME='1'` before starting Python to use its supported pure-Python fallback.

This execution environment uses a separate `.venv-test` with Python 3.11.15. Your existing Windows `.venv` was not modified; continue using it on your machine. Use `.\.venv-test\Scripts\python.exe` only when running in this execution environment.

## Configuration

Copy `.env.example` for the complete configuration. Important values:

| Variable | Default |
| --- | --- |
| OPENAI_BASE_URL | http://localhost:11434/v1 |
| OPENAI_API_KEY | ollama (placeholder ignored by local Ollama) |
| OPENAI_CHAT_MODEL | qwen2.5:1.5b |
| OPENAI_EMBEDDING_MODEL | nomic-embed-text |
| EMBEDDING_DIMENSION | 768 |
| QDRANT_COLLECTION | document_chunks_nomic_embed_text_768 |
| QDRANT_URL | http://localhost:6333 |
| REDIS_URL | redis://localhost:6379/0 |
| DATABASE_URL | sqlite:///./app.db |
| MAX_UPLOAD_BYTES | 10485760 |

The physical collection name appends a stable hash of the embedding model name. Changing models selects a separate collection, and retrieval also filters by model. Existing collections are never deleted or resized. A dimension or distance-metric mismatch stops startup with a clear error: correct the configuration or choose a new collection prefix and re-ingest. Previously uploaded OpenAI vectors are preserved but are not searched by the Ollama collection. If you replace a model's weights under the same model name, choose a new collection prefix manually.

## API 1: Document ingestion

`POST /api/v1/documents/ingest`, multipart fields `file` and `strategy` (`fixed` or `recursive`, default `recursive`).

```powershell
curl.exe -X POST http://127.0.0.1:8000/api/v1/documents/ingest -F "file=@sample.txt" -F "strategy=fixed"
curl.exe -X POST http://127.0.0.1:8000/api/v1/documents/ingest -F "file=@document.pdf" -F "strategy=recursive"
```

Returns `document_id`, `filename`, `strategy`, `chunks_stored`. Metadata is committed to SQLite after vector insertion. Failed writes trigger compensating deletion of the new document's vectors. Unsupported extensions return 415, oversized uploads 413, and empty/invalid/non-UTF-8 files or PDFs without extractable text 422. Scanned PDFs require external OCR.

## API 2: Conversational RAG and booking

`POST /api/v1/chat`, JSON with `session_id` and `message`. Use the same session ID for follow-ups. Responses include `answer`, `sources` and nullable `booking_id`.

```powershell
$body = @{session_id='demo123'; message='What does the document say about internships?'} | ConvertTo-Json
Invoke-RestMethod http://127.0.0.1:8000/api/v1/chat -Method Post -ContentType 'application/json' -Body $body
$body = @{session_id='demo123'; message='How long do they last?'} | ConvertTo-Json
Invoke-RestMethod http://127.0.0.1:8000/api/v1/chat -Method Post -ContentType 'application/json' -Body $body
```

The LLM rewrites follow-up questions before embedding. Retrieved passages and history are sent to the generation model with instructions to answer only from documents. Empty retrieval returns an explicit unknown response. Dependency failures return 503; invalid embedding dimensions or malformed model JSON return 502.

Booking example, using one session ID:

1. `I want to book an interview.` -> asks for name.
2. `My name is Riyan Shrestha.` -> asks for email.
3. `riyan@example.com` -> asks for preferred date.
4. `October 20, 2026, at 2 PM.` -> summarizes all details and asks for confirmation.
5. `Yes, confirm.` -> saves to SQLite and returns booking ID.
6. `confirm` -> returns the existing booking ID without inserting another booking.

Name, email, date and time are validated. Appointment must be in the future, including time on today's date. All appointment times are Nepal time (Asia/Kathmandu, UTC+05:45). Giving details, even with an LLM `confirmed` flag, never saves a booking before a separate confirmation turn. Changing details requires a fresh confirmation. Supported confirmations include `confirm`, `yes`, `yes, confirm`, `book it`, and `confirm the booking`.

## Storage

SQLite tables: `documents` and `bookings` (created automatically on startup). Redis `chat:<session>` retains the latest 20 messages for 24 hours; `booking:<session>` retains draft/completed state for 24 hours. `lock:<session>` protects concurrent chat turns. Docker volumes persist Qdrant and Redis; SQLite lives in the configured local database file. `.env`, environments, databases and uploads are excluded from Git.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Automated tests use actual SQLite and PDF parsing, mocked model/Redis calls, and an actual in-memory Qdrant client for insertion/retrieval. They cover chunking without text loss, both file types/strategies, vector validation, collection safety, history-aware retrieval, booking validation/confirmation/idempotency, HTTP contracts and dependency errors.

Opt-in live smoke test (requires both Ollama models and all services):

```powershell
$env:RUN_LIVE_TESTS='1'
.\.venv\Scripts\python.exe -m pytest tests/test_live.py -q -s
Remove-Item Env:RUN_LIVE_TESTS
```

The live test writes identifiable sample documents and a far-future test booking. It checks ingestion, real embeddings/retrieval, multi-turn questions and booking persistence/duplicate confirmation. Mocked tests are not evidence of live model quality. See [TEST_RESULTS.md](TEST_RESULTS.md) for actual verification and blockers in this workspace, and [SUBMISSION.md](SUBMISSION.md) for the final verification and Git commands.

## Limitations

- Small local model extraction and grounding quality vary; malformed extraction is reported rather than silently accepted.
- Booking cancellation, scheduling availability, calendar integration and email delivery are not implemented.
- Confirmation phrases use an explicit allowlist. Redis expiry loses conversation/draft state; committed bookings remain in SQLite.
- SQL and Qdrant have compensating writes rather than distributed transactions. A service outage during cleanup can leave orphan vectors.
- Synchronous PDF parsing/SQLite operations suit this assignment's local workload; larger workloads need background ingestion.
- This local demo has no authentication, tenant isolation or rate limiting. Uploaded documents share a collection.
- Stable model tags must identify stable embedding weights; changing weights requires a fresh collection prefix.
