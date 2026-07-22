# Atlas RAG backend

This directory contains the local FastAPI application, durable SQLite metadata,
validated Atlas60 bootstrap, production document ingestion/deletion, and stable-ID
FAISS snapshot storage. The legacy 2,729-chunk artifact is validated for provenance but
never activated because its chunks exceed the selected embedding model's effective
input limit.

The repository-level `README.md` is the complete install, architecture, evaluation,
security, limitations, acceptance, and troubleshooting guide. This file focuses on
backend operations.

## Requirements

- Python 3.11 or 3.12
- [uv](https://docs.astral.sh/uv/)

## Development

```bash
cd backend
cp .env.example .env
uv sync --group dev --extra ml
uv run alembic upgrade head
uv run --extra ml python scripts/bootstrap_existing_corpus.py
uv run --extra ml python scripts/verify_storage.py
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Bootstrap reads and validates the repository's inventory, page, legacy vector,
evaluation, and accepted benchmark artifacts; rebuilds 220/240/60-token MiniLM
chunks; copies originals into private storage; and atomically creates an
`IndexIDMap2/IndexFlatIP` snapshot. It is idempotent: rerunning it verifies and
reports the active corpus without adding rows or vectors. `verify_storage.py`
checks the manifest and index checksums, configured model/chunk policy, ordered
chunk inputs, and exact SQLite/FAISS vector-ID equality.

The default database and storage live under `backend/storage/`. Runtime storage,
local environment files, credentials, and model caches must not be committed.
Generation is disabled by default and does not affect retrieval readiness. Run one
Uvicorn worker for the local v1 backend; a filesystem process lock ensures only one
durable ingestion worker can claim SQLite jobs and mutate FAISS.

## Retrieval and grounded chat

`POST /api/v1/chat/queries` embeds the question with the active index model, searches
an over-fetched candidate pool, applies an optional exact domain filter, removes
near-duplicate vectors, and persists ranked evidence before generation. The request
accepts `question`, optional `topK` (maximum 20), and optional `domain`. Re-open the
evidence snapshot later with `GET /api/v1/retrieval/{queryId}`; it remains available
even if a cited document is subsequently deleted. Answerable suggestions from the
versioned gold set are available at `GET /api/v1/chat/suggestions?limit=4`.

When the best score is below `ATLAS_MINIMUM_CONTEXT_SCORE`, chat returns HTTP 200
with a deterministic insufficient-context answer and never calls a provider. When
evidence passes the gate but generation is disabled, it returns the distinct typed
`503 GENERATION_PROVIDER_UNAVAILABLE` error. To enable OpenAI or a local
OpenAI-compatible endpoint, set `ATLAS_GENERATION_ENABLED=true`, a model, base URL,
and an API key for the default OpenAI endpoint. Context is bounded by
`ATLAS_GENERATION_CONTEXT_MAX_TOKENS`; provider requests use temperature zero, a
timeout, and a process-local concurrency semaphore. Answers must cite supplied
`[S#]` labels. One invalid response is corrected once; a second invalid response is
returned as `502 GENERATION_RESPONSE_INVALID`, never as a verified answer.

## Durable evaluation

Bootstrap imports the 33-question gold set as an immutable dataset version bound to
its SHA-256 hash. Start a production-retrieval evaluation and poll its run with:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/evaluation/runs \
  -H 'Content-Type: application/json' \
  -d '{"mode":"retrieval"}'
curl http://127.0.0.1:8000/api/v1/evaluation/runs/<run-id>
```

Evaluation jobs share the durable SQLite worker with ingestion and deletion, persist
each question before advancing, and resume after an interrupted process. They call
the same retrieval service as chat and record the active index version, model,
threshold, top-k configuration, Recall@1/3/5/10, MRR, retrieval latency, context-gate
accuracy, domains, and stable failure categories. Retrieval metrics use answerable
questions only. Manual answer-correctness and groundedness means remain `null` until
real ratings exist.

Optional generation evaluation must be explicitly bounded and generation must be
configured and ready:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/evaluation/runs \
  -H 'Content-Type: application/json' \
  -d '{"mode":"generation","maximumQuestions":5}'
```

`ATLAS_EVALUATION_GENERATION_MAX_QUESTIONS` defaults to 10. Read runs from
`GET /api/v1/evaluation/runs`, domain metrics from `/runs/{runId}/domains`, paginated
failures from `/runs/{runId}/failures`, and the frontend-ready aggregate from
`GET /api/v1/evaluation/latest`.

## Incremental ingestion

Upload accepts actual PDF, DOCX, and TXT bytes, stores the original under a generated
private name, and returns a durable job immediately:

```bash
curl -F 'file=@/absolute/path/to/document.pdf' \
  -F 'domain=user-uploaded' \
  http://127.0.0.1:8000/api/v1/documents/upload

curl http://127.0.0.1:8000/api/v1/ingestion-jobs/<job-id>
```

Uploads are streamed with a size limit and SHA-256 calculation. Extension, MIME,
PDF signature, TXT encoding, and DOCX ZIP structure/path/expansion checks run before
the durable document/job records are accepted. Exact checksum duplicates return
`409 DUPLICATE_DOCUMENT` with the existing document ID.

The worker preserves real PDF page numbers and logical page 1 for DOCX/TXT, cleans
text deterministically, creates tokenizer-bounded 220/240/60 chunks, and embeds in
bounded batches with the process-shared model. It builds a complete candidate FAISS
snapshot off the active index and commits pages, chunks, document state, job result,
and `index_state` together before swapping the in-memory index. Interrupted jobs are
reconciled and retried after restart; parser or finalization failures retain the
previous verified index and expose a safe typed job error.

## Coordinated deletion and index recovery

Deletion is asynchronous and uses the same durable queue and single index writer:

```bash
curl -X DELETE http://127.0.0.1:8000/api/v1/documents/<document-id>
curl http://127.0.0.1:8000/api/v1/ingestion-jobs/<job-id>
```

The worker builds a candidate snapshot without the document's stable vector IDs,
marks those chunks non-active, and verifies exact SQLite/manifest/FAISS alignment
before it removes document metadata and the private original. A write, verification,
or filesystem failure restores the prior index state; repeated requests while deletion
is queued/running return the same durable job. Interrupted deletions resume after
restart, including from a recoverable document-stable tombstone.

Completed mutations retain the active snapshot and one previous known-good snapshot
by default (`ATLAS_SNAPSHOT_RETENTION_COUNT=2`). The writer removes older completed
snapshots while leaving malformed directories available for diagnosis.

Stop the API before running offline repair commands so its in-memory index cannot
remain older than the newly activated database state:

```bash
uv run --extra ml python scripts/verify_storage.py
uv run --extra ml python scripts/rebuild_index.py
# or: make verify-storage && make rebuild-index
```

Verification exits nonzero on checksum, schema, model/chunk configuration,
ordered-input, or vector-ID mismatch. Rebuild re-embeds every SQLite chunk whose
status is `indexed`, preserves its stable vector ID, atomically activates and verifies
a new snapshot, and rolls back the active state if verification fails. It is the repair
path for a missing/corrupt FAISS file; it does not synthesize vectors or recover
missing SQLite chunk text.

Quality commands are available individually or as one gate:

```bash
make test
make lint
make typecheck
make coverage
make check
```

After pulling schema changes, run `uv run alembic upgrade head` and verify migration
drift with `uv run alembic check`. For a clean restart check, stop Uvicorn, start the
same command again, confirm `GET /health/ready` is HTTP 200, and rerun
`scripts/verify_storage.py`. If readiness reports a missing or corrupt index, stop
the API and run `scripts/rebuild_index.py` followed by `scripts/verify_storage.py`.
Running an offline rebuild while the API is live is unsupported.

`GET /health/live` proves only process liveness. Startup verifies the active snapshot,
loads one shared embedding model, reconciles the durable queue, and then starts the
worker. `GET /health/ready` returns HTTP 200 only when database, index, embedding,
and worker dependencies are ready; model load or index-alignment failures remain
truthful HTTP 503 states.

Read APIs are `GET /api/v1/documents`, `/documents/stats`, `/documents/{id}`,
`/documents/{id}/pages`, and `/documents/{id}/chunks`. Mutation/job APIs are
`POST /api/v1/documents/upload`, `DELETE /api/v1/documents/{id}`, and
`GET /api/v1/ingestion-jobs/{jobId}`. Absolute source and storage paths are never
returned.
