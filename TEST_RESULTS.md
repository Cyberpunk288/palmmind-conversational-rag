# Final verification - October 15, 2026

## Automated tests

**34 passed, 0 failed, 1 skipped, 1 warning in 3.92 seconds.**

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
| Ollama | `http://127.0.0.1:11434/api/tags` | Reachable; `qwen2.5:1.5b` is installed. `nomic-embed-text` is not yet listed. |
| Qdrant | `http://127.0.0.1:6333/healthz` | `URLError: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>` |
| Redis | `127.0.0.1:6379` | `ConnectionRefusedError: [WinError 10061] No connection could be made because the target machine actively refused it` |

Real embeddings and document-grounded generation, server-backed Qdrant operations, real Redis memory and full live REST integration remain blocked. Real Ollama booking extraction was verified separately below. The final check confirmed the chat model download is complete; the embedding model remains unavailable. No repeated connectivity polling was performed after this final check.

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

Implementation, README, tests and submission instructions were committed locally on `development` as `316dce3`. Final verification notes are recorded in a subsequent documentation commit. `git diff --check` passed. Ignore checks confirmed local environments, `.env`, databases, uploads and model paths are excluded; no environment/database files were tracked. No push or merge has been performed. The live integration limitation must remain disclosed in submission.

## Real Ollama booking smoke test

**Passed** after the final connectivity check showed `qwen2.5:1.5b` installed. This was an actual OpenAI-compatible Ollama model request sequence through `Services.conversation`, with fake Redis and a temporary in-memory SQLite database. It was not a full live REST/Redis integration test.

The test sent booking intent, name, email and an explicit future date/time over four turns. The model supplied the details, the service requested explicit confirmation, and a separate `Yes, confirm.` saved the booking. A repeated `confirm` returned the same booking ID. Assertions verified exactly one persisted record with `riyan@example.com`, date `2099-10-20`, and time `14:00`. All assertions passed. One intermediate model response triggered the service's validation/re-prompt before the explicit appointment details were supplied; it did not save invalid data.

No existing Qdrant or Redis data was touched. Final automated pytest result remains **34 passed, 0 failed, 1 skipped**, plus one non-failing deprecation warning, in **3.92 seconds**. The standalone real-model smoke test is additional to that pytest count.
