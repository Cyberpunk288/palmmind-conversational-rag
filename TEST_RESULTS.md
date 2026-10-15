# Final verification - October 15, 2026

## Automated tests

**34 passed, 0 failed, 1 skipped, 1 warning in 4.69 seconds.**

```powershell
$env:DISABLE_SQLALCHEMY_CEXT_RUNTIME='1'
.\.venv-test\Scripts\python.exe -m pytest -q
```

Python 3.11.15 and SQLAlchemy 2.0.54 were used in a separate `.venv-test`. The original Windows `.venv` was not modified. The warning is a Starlette TestClient/httpx deprecation warning; it did not fail a test. The skipped test is the explicit opt-in live end-to-end test.

Both REST APIs pass automated HTTP and service tests. Full operation against live Ollama, Qdrant and Redis is **not verified**.

Tests cover actual PDF extraction and TXT ingestion with both chunkers, recursive chunk text preservation, embedding validation, the real OpenAI client against a mocked Ollama HTTP transport, safe collection dimension/distance checks, actual in-memory Qdrant insertion/retrieval, actual SQLite persistence, compensating vector deletion on SQL failure, mocked Redis history retention/session isolation, history-aware RAG retrieval, unknown answers, upload/request validation, dependency errors, multi-turn booking, explicit confirmation, changed details, duplicate confirmation and recovery from Redis failure after a booking commit.

## Final live connectivity check

Read-only requests ran outside the sandbox. No existing collection or Redis data was modified or deleted.

| Service | Target | Actual result |
| --- | --- | --- |
| Ollama | `http://127.0.0.1:11434/api/tags` | Reachable, returning `{"models":[]}`. Neither required model is available yet. |
| Qdrant | `http://127.0.0.1:6333/healthz` | `URLError: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>` |
| Redis | `127.0.0.1:6379` | `ConnectionRefusedError: [WinError 10061] No connection could be made because the target machine actively refused it` |

Real model embeddings/generation, server-backed Qdrant operations, Redis memory and the full live booking conversation remain blocked. Downloading models do not appear in Ollama's installed-model list until ready. The user reported `qwen2.5:1.5b` downloading and plans to download `nomic-embed-text` next. No repeated connectivity polling was performed after this final check.

Once both models and all services are available, run the live test on the Windows machine using its existing working environment:

```powershell
$env:DISABLE_SQLALCHEMY_CEXT_RUNTIME='1'
$env:RUN_LIVE_TESTS='1'
.\.venv\Scripts\python.exe -m pytest tests/test_live.py -q -s
Remove-Item Env:RUN_LIVE_TESTS
```

This opt-in test adds sample TXT documents, session keys and a far-future booking. A live text-bearing PDF upload should additionally be checked through Swagger with both strategies. Automated PDF ingestion already passes with mocked embeddings.

## SQLAlchemy fallback

The installed SQLAlchemy 2.0.54 explicitly implements `DISABLE_SQLALCHEMY_CEXT_RUNTIME=1` in [its official release source](https://github.com/sqlalchemy/sqlalchemy/blob/rel_2_0_54/lib/sqlalchemy/util/_has_cy.py). Verification confirmed `HAS_CYEXTENSION=False` and no SQLAlchemy compiled-extension modules loaded. No installed source or Windows security settings were changed. SQLAlchemy investigation is complete.

## Submission state

Implementation, README, tests and submission instructions are prepared on `development` for the final local commit. `git diff --check` passed. Ignore checks confirmed local environments, `.env`, databases, uploads and model paths are excluded; no environment/database files were tracked. No push or merge has been performed. The live integration limitation must remain disclosed in submission.
