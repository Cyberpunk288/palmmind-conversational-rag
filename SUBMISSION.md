# Submission preparation

Work remains on `development`. Automated tests passed: **34 passed, 0 failed, 1 live test skipped**. Live integration is unverified: Ollama is reachable with an empty model list, and Qdrant/Redis refused connections. See [TEST_RESULTS.md](TEST_RESULTS.md) for actual results and exact errors.

The implementation and documentation are prepared for the final local commit on `development`. No push or merge has been performed. Existing Windows `.venv`, Qdrant collections and Redis data were preserved.

## Final verification on the Windows machine

Use your existing working Python 3.11 environment. From the repository directory:

```powershell
$env:DISABLE_SQLALCHEMY_CEXT_RUNTIME='1'
.\.venv\Scripts\python.exe -m pytest -q
docker compose up -d
ollama list
```

Once both `qwen2.5:1.5b` and `nomic-embed-text` appear and Qdrant/Redis are reachable, run the opt-in live test. It adds sample documents, session keys and one future test booking; do not run it against production data.

```powershell
$env:RUN_LIVE_TESTS='1'
.\.venv\Scripts\python.exe -m pytest tests/test_live.py -q -s
Remove-Item Env:RUN_LIVE_TESTS
```

Additionally verify a text-bearing PDF through Swagger using both chunking strategies; automated PDF ingestion tests already pass with mocked embeddings. Record the actual live result before describing the project as verified end to end.

## Commit and development-branch push commands

The staging and commit commands below describe the final local commit preparation. The push command remains a separate user action; no push has been performed. Review the commit with `git show --stat HEAD` before pushing:

```powershell
git switch development
git status --short
git diff --check
git add .env.example .gitignore README.md TEST_RESULTS.md SUBMISSION.md requirements.txt app/chunking.py app/config.py app/main.py app/schemas.py app/services.py tests/test_chunking.py tests/test_services.py tests/test_live.py
git diff --cached --check
git diff --cached --stat
git diff --cached
git commit -m "Implement Ollama RAG and confirmed interview booking with regression tests"
git push origin development
```

Merge or push to `main` only after explicit approval. Do not use `git add -f` for environment, database, uploads or model files.

Suggested review summary: Local Ollama chat/embeddings, safe model-specific Qdrant collections, PDF/TXT ingestion, history-aware RAG, Redis booking drafts, explicit confirmation and SQLite persistence with duplicate protection. Automated verification: 34 passed; live verification blocked by service/model availability in the execution environment.
