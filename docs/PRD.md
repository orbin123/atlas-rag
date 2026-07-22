# Product Requirements Document: Local RAG Document Question-Answering System

## 1. Purpose

Build a local Retrieval-Augmented Generation (RAG) application that lets users upload documents, search them conversationally, and receive answers grounded in the most relevant document passages.

The system must demonstrate the full RAG lifecycle:

```text
Documents → text extraction → cleaning → chunking → embeddings → FAISS index
User question → query embedding → top-k retrieval → augmented prompt → answer + sources
```

The system does not fine-tune or post-train a model. Instead, it supplies relevant external knowledge to the language model at answer time.

## 2. Scope

### Included

- At least 50 documents; target 100 documents across multiple domains.
- PDF, TXT, and DOCX ingestion.
- Text extraction, normalization, cleaning, and chunking with overlap.
- Sentence-transformer embeddings.
- FAISS vector index for local semantic retrieval.
- FastAPI backend.
- React frontend.
- Document upload and incremental indexing.
- Answers with supporting source chunks, document names, pages, and relevance scores.
- Retrieval and answer-quality evaluation with plots.

### Not included

- Cloud deployment, user authentication, collaboration, billing, or production monitoring.
- Fine-tuning an embedding model or LLM.
- Full OCR support in version 1; scanned PDFs may be recorded as a known limitation.

## 3. Dataset Strategy and Justification

Use a curated corpus of approximately 100 publicly accessible documents from 10 broad domains, with roughly 10 documents per domain:

- Technology and artificial intelligence
- Healthcare and biology
- Finance and economics
- Climate and environment
- Education
- Law and public policy
- History and culture
- Space and science
- Cybersecurity
- Business and management

Use reliable, text-rich sources such as public reports, educational articles, technical documentation, research abstracts, government resources, or openly licensed PDFs.

This dataset is preferable to a random set of files because it:

1. Demonstrates cross-domain semantic retrieval.
2. Contains both factual and explanatory content.
3. Produces realistic ambiguity, where retrieval quality matters.
4. Makes evaluation possible through a manually curated set of questions and source-supported answers.
5. Supports an interviewer discussion about domain shift, data quality, provenance, and retrieval limitations.

The local filesystem is the source of truth for the corpus. During ingestion, derive metadata from the file and its location, then persist that metadata with the processed records and chunks. The original source URL and license/usage note are optional fields: retain them only when they are supplied and trustworthy.

## 4. Machine-Learning Flow

### Ingestion

1. User uploads or selects a document.
2. The application identifies its type.
3. The application creates an ingestion record with a generated document ID, file name, file type, folder-derived domain (or `user-uploaded`), upload time, and optional user-supplied title, source URL, and license note.
4. Text is extracted with page-level metadata where available.
5. Extraction noise is removed:
   - repeated headers and footers
   - excessive whitespace
   - broken line breaks
   - empty pages
   - non-informative symbols
6. The cleaned text is divided into context-preserving chunks.

### Chunking

Use a recursive, paragraph-aware chunking strategy:

- Target chunk length: 400–700 tokens
- Overlap: 60–120 tokens
- Prefer paragraph and sentence boundaries over character-only splitting

Overlap is important because a fact may start at the end of one chunk and continue in the next. It preserves continuity without embedding entire documents at once.

Each chunk retains metadata:

```text
chunk_id, document_id, file_name, domain, page_number,
chunk_index, original_text, cleaned_text
```

### Preprocessing

The project will demonstrate tokenization, normalization, and stop-word analysis in the notebook.

However, the final embedding text should remain close to natural language. Aggressively removing stop words or stemming text can reduce sentence-embedding quality because modern embedding models use word order and context. Therefore:

- Clean noise and normalize formatting.
- Preserve meaningful natural-language sentences for embeddings.
- Keep original chunk text for citations and display.

### Embedding and FAISS Indexing

Use a Sentence Transformer model to embed all chunks into dense vectors.

Recommended initial model: `all-MiniLM-L6-v2`

Reasons:

- Fast on a local machine.
- Lightweight and practical for 100 documents.
- Strong enough to demonstrate semantic retrieval.
- Easy to explain and replace later with a stronger model.

Normalize embedding vectors and store them in FAISS using inner-product search. For normalized vectors, inner product is equivalent to cosine similarity.

### Retrieval

When a question is asked:

1. Convert the query into an embedding using the same embedding model.
2. Search FAISS for the top-k nearest chunk vectors.
3. Return the most semantically relevant chunks with similarity scores.
4. Deduplicate or diversify highly similar chunks if necessary.
5. Pass the selected chunks and the question to the generation model.

Important terminology:

- **Cosine similarity** measures semantic closeness between embeddings.
- **k-nearest neighbors (k-NN)** means returning the top-k closest chunks.
- FAISS performs this nearest-neighbor retrieval; no separate k-NN classifier needs to be trained.

### Answer Generation

The LLM receives:

- the user’s question
- the top retrieved chunks
- source metadata
- a strict instruction to answer only from the provided context

The answer must:

- be concise and directly address the question
- cite source documents/pages or chunks
- state that the answer is not available if the context is insufficient
- avoid inventing unsupported details

## 5. Notebook Plan

The notebook is the learning and experimentation environment. It should be organized as these sections.

### Section 1 — Problem Definition

- Explain RAG, why it is useful, and why it avoids retraining.
- Define the corpus, user query flow, and success criteria.
- Explain the distinction between embeddings, cosine similarity, k-NN retrieval, and generation.

### Section 2 — Dataset Collection and Inspection

- Discover supported files directly from the corpus folders.
- Display document counts by domain and file type.
- Inspect a few representative documents.
- Explain source quality, diversity, and known dataset limitations. Note that provenance fields are optional and are not trusted unless verified.

### Section 3 — Text Extraction

- Extract text from PDF, DOCX, and TXT files.
- Preserve page-level information for PDFs.
- Show before-and-after examples of raw extracted text.

### Section 4 — Cleaning and Preprocessing

- Remove repeated headers/footers and excessive whitespace.
- Normalize Unicode and line breaks.
- Demonstrate tokenization, lowercasing, and stop-word analysis.
- Explain why the final embedding input keeps natural language intact.

### Section 5 — Chunking Experiment

- Implement recursive or paragraph-aware chunking.
- Apply overlap.
- Show sample chunks and metadata.
- Compare chunk sizes and explain the precision-versus-context tradeoff.

### Section 6 — Embedding Generation

- Load the sentence-transformer model.
- Generate embeddings for chunks.
- Inspect vector dimensions and normalized vectors.
- Explain semantic representation and why the query must use the same model.

### Section 7 — FAISS Index Construction

- Create a FAISS index.
- Add normalized chunk embeddings.
- Save the FAISS index and metadata locally.
- Demonstrate retrieval speed and index size.

### Section 8 — Retrieval Testing

- Embed several test questions.
- Retrieve top-k chunks.
- Display document names, pages, chunks, and similarity scores.
- Compare useful and poor retrieval examples.

### Section 9 — RAG Generation

- Construct a context-aware prompt.
- Send retrieved context plus the user question to the LLM.
- Display answer, citations, and retrieved evidence.
- Demonstrate the “insufficient context” fallback.

### Section 10 — Evaluation

Create a gold test set of approximately 30–50 questions. Each record contains:

```text
question, expected answer, supporting document, supporting chunk/page, domain
```

Measure:

- **Recall@k:** whether the correct supporting chunk appears in top-k retrieval.
- **MRR:** how highly the first correct chunk ranks.
- **Answer correctness:** manual 0–1 or 1–5 rating against expected answer.
- **Groundedness/relevance:** whether the answer is supported by retrieved context.
- **Latency:** time for retrieval and full answer generation.

Plot retrieval metrics and per-domain results.

### Section 11 — Findings and Limitations

Document the effect of chunk size, overlap, top-k selection, and model choice. Record failure cases and future improvements such as hybrid search, reranking, OCR, multilingual embeddings, and access control.

## 6. Application Build Plan

After the notebook is validated, move reusable functions into a maintainable application structure.

```text
  backend/
    app/
      api/
      services/
      models/
      utils/
    data/
    storage/
      faiss/
      metadata/
    tests/
  frontend/
  notebooks/
  dataset/
  evaluation/
  README.md
```

### Backend Responsibilities

FastAPI handles document ingestion, indexing, retrieval, question answering, and evaluation.

Core services:

- `document_parser`: extracts text from supported formats
- `preprocessor`: cleans and normalizes text
- `chunker`: creates overlapping chunks and metadata
- `embedding_service`: loads the sentence-transformer model
- `faiss_store`: persists, updates, and searches the vector index
- `retrieval_service`: retrieves and formats top-k evidence
- `generation_service`: constructs the grounded prompt and generates an answer
- `evaluation_service`: runs the test set and creates metric results

Suggested local endpoints:

```text
POST /documents/upload
GET  /documents
DELETE /documents/{document_id}

POST /chat/query
GET  /retrieval/{query_id}
POST /evaluation/run
GET  /evaluation/results
GET  /health
```

`POST /chat/query` should return:

```text
answer
sources: [{file_name, page_number, chunk_text, similarity_score}]
retrieval_latency_ms
generation_latency_ms
```

## 7. React Frontend: Required Pages

### 1. Dashboard / Chat Page

Primary working page.

Functions:

- Enter a question.
- Submit to the FastAPI RAG endpoint.
- Show the final answer.
- Show answer citations.
- Show the retrieved chunks used by the model.
- Display similarity scores and source page/document details.
- Show a clear “not enough context found” state.

### 2. Document Library Page

Shows the available knowledge base.

Functions:

- List indexed documents.
- Filter by domain or file type.
- Show document metadata: name, type, size, pages, chunk count, upload date.
- Open document details.
- Remove a document from the local index.

### 3. Upload Document Page or Upload Modal

Adds new content to the knowledge base.

Functions:

- Choose PDF, DOCX, or TXT files.
- Validate supported formats.
- Upload to FastAPI.
- Display ingestion progress: extracting, cleaning, chunking, embedding, indexing.
- Show success state with number of chunks added.
- Show meaningful failure messages.

### 4. Document Detail Page

Provides transparency for each indexed document.

Functions:

- Display document metadata.
- Display extracted pages/text preview.
- Display chunks created from the document.
- Show chunk identifiers and page references.
- Help demonstrate explainability during an interview.

### 5. Evaluation Page

Shows system quality rather than only a polished chat interface.

Functions:

- Run the saved evaluation test set.
- Display Recall@k, MRR, answer correctness, groundedness, and latency.
- Show charts by domain.
- Display failed examples for error analysis.

## 8. Acceptance Criteria

The local application is complete when:

- At least 50 documents are ingested; 100 is the target.
- PDF, TXT, and DOCX ingestion works.
- Documents are chunked with overlap and preserved metadata.
- Chunks are embedded and persisted in FAISS.
- New document uploads are indexed without rebuilding the system manually.
- User queries retrieve top-k semantically relevant chunks.
- Answers cite retrieved evidence.
- The system responds safely when evidence is insufficient.
- A test set evaluates retrieval and answer quality.
- Evaluation results are shown in plots.
- README explains setup, architecture, dataset, evaluation, limitations, and interview talking points.

## 9. Three-Day Execution Plan

### Day 1 — Research Notebook and Corpus

- Gather 50–100 documents in domain folders; ingestion generates the working metadata records.
- Complete extraction, cleaning, chunking, embedding, and FAISS notebook sections.
- Test semantic retrieval with representative questions.
- Create the first evaluation question set.

### Day 2 — Backend and RAG Integration

- Move notebook code into FastAPI services.
- Implement document ingestion, FAISS persistence, retrieval, and generation APIs.
- Add source citations and insufficient-context handling.
- Run evaluation and generate plots.

### Day 3 — React UI, Testing, and Documentation

- Build the chat, document library, upload, detail, and evaluation pages.
- Connect UI to FastAPI.
- Test upload-to-answer flow end to end.
- Document design decisions, limitations, results, and future roadmap.

## 10. Future Improvements

- Hybrid retrieval: BM25 keyword search plus dense vector search.
- Cross-encoder reranking of the top retrieved chunks.
- Better domain-specific or multilingual embedding models.
- OCR for scanned PDFs.
- Query rewriting and conversational memory.
- Source highlighting in document previews.
- Role-based access control and separate indexes for private corpora.
- Retrieval-quality monitoring and automatic regression evaluation.
