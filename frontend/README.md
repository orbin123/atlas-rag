# Atlas RAG frontend

React/Vite client for the local Atlas RAG FastAPI backend. Every screen reads durable backend state; uploads, deletion, chat, evidence, and evaluation are real API operations.

## Run locally

1. Start the backend as described in `../backend/README.md`.
2. Copy `.env.example` to `.env` if the API is not at the default URL.
3. Run `npm install` and `npm run dev`.
4. Open <http://localhost:3000>. Use this hostname (rather than `127.0.0.1`) with the backend's default CORS allowlist.

Use `npm test`, `npm run lint`, and `npm run build` for frontend verification. Generation is optional: when it is disabled, retrieval and all corpus/evaluation screens remain available, while supported chat questions display the backend's typed provider-unavailable error. Below-threshold questions still return the deterministic insufficient-context response.
