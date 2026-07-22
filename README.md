# Atlas RAG

Atlas RAG is a local document question-answering system that implements the full
retrieval-augmented generation lifecycle: validated PDF/DOCX/TXT ingestion,
page-aware cleaning and chunking, normalized sentence-transformer embeddings,
a durable FAISS index, semantic retrieval, grounded optional generation,
citations, and evaluation. The React interface is backed entirely by the FastAPI
API; it contains no runtime corpus or answer mocks.

The checked workspace currently contains 60 indexed Atlas60 documents across 10
domains, 1,848 extracted pages, and 7,336 tokenizer-safe chunks. The target of 100
documents remains optional; the PRD minimum of 50 is satisfied.

## Architecture and data flow

```text
React/Vite (localhost:3000)
          |
          | /api/v1 JSON and multipart uploads
          v
FastAPI (localhost:8000)
          |
          +-- SQLite: documents, pages, chunks, jobs, queries, evaluations
          +-- durable single worker: ingest, delete, evaluate
          +-- shared MiniLM encoder
          +-- locked IndexIDMap2(IndexFlatIP) snapshot writer
          +-- private local originals and atomic FAISS snapshots
```

An upload is streamed to private storage and validated before a durable job is
created. The worker extracts and cleans text, creates overlapping page-aware
chunks, embeds them, builds and verifies a candidate FAISS snapshot, commits the
SQLite/index state, and only then marks the document indexed. Queries use the same
model and active snapshot, persist their ranked evidence, apply the calibrated
context gate, and call the optional generation provider only when evidence is
strong enough. Evaluation calls that exact production retrieval implementation.

SQLite is the lifecycle source of truth; FAISS owns vectors; the filesystem owns
originals and immutable index snapshots. One local worker and an inter-process
lock serialize index mutations. Active snapshots are written atomically and the
previous known-good snapshot is retained for recovery.

## Prerequisites

- Python 3.11 or 3.12
- [uv](https://docs.astral.sh/uv/)
- Node.js 20 or newer and npm
- The repository's `data/atlas60/` corpus and `artifacts/` bootstrap inputs

The first model setup can download the pinned sentence-transformer revision. No
generation provider is required for ingestion, retrieval, or evaluation.

## Install and run

From the repository root:

```bash
cd backend
cp .env.example .env
uv sync --group dev --extra ml
uv run alembic upgrade head
uv run --extra ml python scripts/bootstrap_existing_corpus.py
uv run --extra ml python scripts/verify_storage.py
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Bootstrap is checksum-validated and idempotent. A second run verifies the active
corpus rather than duplicating records or vectors. Keep the backend at one Uvicorn
worker in local v1.

In a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open <http://localhost:3000>. The hostname matters because it matches the default
CORS allowlist. API documentation is at <http://127.0.0.1:8000/docs>.

Check readiness before using retrieval:

```bash
curl http://127.0.0.1:8000/health/live
curl http://127.0.0.1:8000/health/ready
curl http://127.0.0.1:8000/api/v1/system/info
```

Liveness only proves that the process is running. Readiness additionally requires
SQLite, the verified active index, the embedding model, and the durable worker.
Generation readiness is reported separately.

## Common operations

Run migrations after pulling schema changes:

```bash
cd backend
uv run alembic upgrade head
uv run alembic check
```

Upload, monitor, and delete a document:

```bash
curl -F 'file=@/absolute/path/to/document.pdf' \
  -F 'domain=user-uploaded' \
  http://127.0.0.1:8000/api/v1/documents/upload
curl http://127.0.0.1:8000/api/v1/ingestion-jobs/<job-id>
curl -X DELETE http://127.0.0.1:8000/api/v1/documents/<document-id>
```

Run a retrieval-only evaluation and poll it:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/evaluation/runs \
  -H 'Content-Type: application/json' \
  -d '{"mode":"retrieval"}'
curl http://127.0.0.1:8000/api/v1/evaluation/runs/<run-id>
curl http://127.0.0.1:8000/api/v1/evaluation/latest
```

Generation evaluation is opt-in and bounded:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/evaluation/runs \
  -H 'Content-Type: application/json' \
  -d '{"mode":"generation","maximumQuestions":5}'
```

To enable chat generation, set `ATLAS_GENERATION_ENABLED=true`,
`ATLAS_GENERATION_MODEL`, and an OpenAI-compatible `ATLAS_GENERATION_BASE_URL`.
The default OpenAI URL also requires `ATLAS_GENERATION_API_KEY`. Secrets belong in
`backend/.env`, never source control. Provider requests use temperature 0, a
30-second default timeout, a two-request concurrency bound, and validated `[S#]`
citations. Without a provider, evidence and retrieval details are still persisted,
and answerable chat requests return the typed
`GENERATION_PROVIDER_UNAVAILABLE` response. Below-threshold questions return a
deterministic safe fallback without contacting any provider.

## Model and retrieval decisions

The production configuration is pinned and surfaced by `/api/v1/system/info`:

| Setting | Active value | Reason |
| --- | --- | --- |
| Embedding | `sentence-transformers/all-MiniLM-L6-v2` at revision `1110a243...` | Fast local 384-dimensional baseline |
| Chunking | target 220, maximum 240, overlap 60 tokens | Fits MiniLM's verified 256-token effective input limit with no silent truncation |
| FAISS | normalized float32 `IndexIDMap2(IndexFlatIP)` | Exact cosine-equivalent search with stable deletion IDs |
| Retrieval | top-k 5 by default, maximum 20 | Bounded API and UI behavior |
| Context gate | top score at least 0.46 | Calibrated on the versioned Atlas gold set for safe refusal |
| Deduplication | vector similarity 0.97 | Removes nearly identical overlapping evidence without a fake reranker |

The PRD's original 400–700-token chunk target is an approved production deviation:
the selected local model cannot consume it safely. Historical notebooks retain the
larger experimental artifacts for reproducibility but are explicitly labeled as
experiments; backend services and manifests are canonical.

## Evaluation results

The current durable retrieval run evaluates 33 versioned questions: 30 answerable
and 3 unsupported. It reports Recall@1 `0.867`, Recall@3/5 `0.967`, Recall@10
`1.000`, MRR `0.906`, fallback accuracy `1.000`, and mean retrieval latency about
`175 ms` on the recorded local run. The Evaluation page renders overall metrics,
per-domain bar plots, and derived failure records from backend data.

Citation rate, answer correctness, and groundedness remain `N/A` for a
retrieval-only run. They are never replaced by invented values; generation metrics
require an explicitly bounded generation run, and correctness/groundedness require
manual ratings.

## Verification

```bash
cd backend
make check                         # lock, Ruff, strict mypy, tests, >=85% coverage
uv run alembic upgrade head
uv run alembic check
uv run --extra ml python scripts/verify_storage.py

cd ../frontend
npm run lint
npm test
npm run build
```

The backend tests include real SQLite and FAISS integration flows for all three file
formats, first upload into an empty corpus, incremental indexing, missing/corrupt
index fail-closed behavior and rebuild, stale-job reconciliation, provider absence,
safe fallback, deletion, evaluation, and clean restart.

## Recovery and troubleshooting

Stop the API before offline index work so its in-memory index cannot lag the
database:

```bash
cd backend
uv run --extra ml python scripts/verify_storage.py
uv run --extra ml python scripts/rebuild_index.py
uv run --extra ml python scripts/verify_storage.py
```

- `health/ready` reports `INDEX_INCONSISTENT` or a missing/corrupt index: stop the
  API, run the rebuild sequence above, then restart. Rebuild re-embeds persisted
  SQLite chunk text and preserves stable vector IDs; it does not invent missing
  text.
- A job was running during a crash: restart the backend. The sole worker lock proves
  inherited running jobs stale and requeues them within their retry limit.
- Upload returns `415` or `422`: confirm the extension, MIME, signature/ZIP
  structure, encoding, and extractable text. Encrypted or scanned-only PDFs are not
  accepted in v1.
- Upload returns `409`: the exact file checksum is already indexed.
- Chat returns generation `503`: configure a provider or continue using retrieval
  evidence and retrieval-only evaluation. This is distinct from an HTTP 200
  insufficient-context fallback.
- The browser reports a network/CORS error: start the backend on port 8000 and open
  the frontend as `http://localhost:3000`, or update both CORS and
  `VITE_API_BASE_URL` consistently.
- A fresh workspace has no active index: run migrations and the idempotent bootstrap
  command. An intentionally empty database can also accept a first upload and will
  create its initial valid snapshot automatically.

## Security assumptions and limitations

Atlas v1 is a localhost, single-user research system without authentication,
authorization, tenancy, cloud deployment, or production rate limiting. Do not bind
it to an untrusted network. Uploads are size-bounded, streamed, signature/MIME
checked, stored under generated private names, and protected against path traversal,
symlinks, unsafe DOCX entries, and archive expansion. Logs omit document bodies,
prompts, answers, and credentials. Retrieved text is delimited as untrusted evidence
inside the generation prompt.

Known limitations are no OCR, no hybrid keyword search, no cross-encoder reranker,
no conversational memory, no automatic provenance verification, and no automatic
answer grading. Source URL and license metadata remain optional unless supplied and
trusted. Local generation quality, latency, and cost depend on the configured
provider.

Useful design talking points are the measured token-window tradeoff, normalized
inner-product/cosine equivalence, stable FAISS IDs, atomic snapshot/SQLite
coordination, durable restart recovery, the calibrated refusal boundary, persisted
evidence after deletion, and keeping retrieval metrics separate from human answer
quality.

More detail is available in [the backend operations guide](backend/README.md),
[the PRD](docs/PRD.md), and [the backend build decisions](docs/backend_build/BACKEND_PLAN.md).
