# Palm Mind AI — Conversational RAG Backend

A modular **FastAPI** backend with exactly two business APIs: document ingestion and multi-turn conversational RAG with AI-assisted interview booking. No frontend, FAISS, Chroma, or RetrievalQAChain.

## Architecture

1. Upload PDF/TXT → extract text (pypdf/UTF-8) → **fixed** or **recursive** chunking → OpenAI embeddings → **Qdrant**.
2. Store document metadata in **SQLite via SQLAlchemy**.
3. Chat → load conversation history from **Redis** → LLM detects interview-booking intent.
4. Ordinary question → embed query → top-k Qdrant retrieval → custom grounded prompt → LLM answer + citations.
5. Booking request → LLM gathers name/email/date/time over multiple turns → explicit confirmation → save booking to SQLite.

## Setup (Windows 11, PowerShell)

Prerequisites: Python 3.11 or 3.12, Docker Desktop (running), an OpenAI API key (with billing/credits enabled).

```powershell
git clone <YOUR_GITHUB_REPOSITORY_URL>
cd palmmind-rag-backend
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
notepad .env
```

Set `OPENAI_API_KEY` in `.env` (NEVER commit this file).

```powershell
docker compose up -d
uvicorn app.main:app --reload
```

Open **http://127.0.0.1:8000/docs** for Swagger. Qdrant dashboard: http://localhost:6333/dashboard.

If you have Python 3.12 instead, replace `py -3.11` with `py -3.12`.

## API 1: Ingest document

`POST /api/v1/documents/ingest` (multipart/form-data)

- `file`: `.pdf` or UTF-8 `.txt`, max 10 MB
- `strategy`: `fixed` or `recursive` (default `recursive`)

Example:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/documents/ingest -F "file=@sample.txt" -F "strategy=recursive"
```

Response:

```json
{"document_id":"<uuid>","filename":"sample.txt","strategy":"recursive","chunks_stored":3}
```

Note: image-only/scanned PDFs need OCR; this implementation returns 422 when no extractable text exists.

## API 2: Chat + booking

`POST /api/v1/chat` (application/json)

```json
{"session_id":"demo123","message":"What does the uploaded document say about internships?"}
```

For follow-ups keep the **same** `session_id`. Response contains `answer`, matching `sources`, and optional `booking_id`.

Booking example, keeping `session_id` constant:

1. `"I want to book an interview."`
2. `"My name is Maya Shrestha, email maya@example.com."`
3. `"October 29, 2026 at 14:30."`
4. `"Confirm the booking."`

The booking is saved only after explicit confirmation, and the reply includes its ID. No real calendar availability checks or emails are sent.

## Testing

```powershell
pytest -q
```

Unit tests cover both chunkers. Integration smoke tests require running Docker services and a funded OpenAI API key. Validate in Swagger: upload both file types, both strategies, ask a grounded question, follow up with a pronoun, walk through interview booking, confirm booking, check SQLite persistence.

## Structure

```text
app/
  config.py       Environment configuration
  database.py     SQLAlchemy models, document/booking metadata
  schemas.py      Typed request and response contracts
  chunking.py     Two chunking strategies
  services.py     Extraction, embeddings, Qdrant, Redis, LLM, booking
  main.py         FastAPI app, lifecycle, two business endpoints
 tests/
  test_chunking.py
```

## Notes / limitations

- `OPENAI_EMBEDDING_MODEL` and `EMBEDDING_DIMENSION` must match (default `text-embedding-3-small` = 1536).
- Redis memory expires after 24 hours; currently last 20 messages are retained.
- Booking date/time have no timezone attached; treat them as local interview time agreed by the user.
- SQL and Qdrant are independent; compensation is applied on failed SQL writes, but no distributed transaction is guaranteed.
- For production: authentication, per-user namespace isolation, rate limits, upload malware checks, prompt-injection defenses, logging, background ingestion, migrations, redaction/encryption of personal data, and booking availability/deduplication are needed.
