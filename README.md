# AeroAPI

AeroAPI is an AI-assisted API testing workspace. Upload a Postman collection, optionally add a Postman environment file, choose an LLM provider, and generate functional, edge-case, regression, and security-oriented checks for your endpoints.

## Features

- Postman collection and environment JSON parsing
- Optional API documentation/business-rules context for more domain-aware test generation
- AI-generated API test cases with Gemini, Groq, Claude, OpenAI-compatible, Codex-compatible, and custom providers
- Deterministic local demo mode with `demo-token`
- Async request execution with progress updates
- Run dashboard, result detail pages, HTML/CSV/Postman collection exports, and optional Slack alerts
- FastAPI backend, Next.js frontend, SQLite local database by default

## Project Layout

```text
backend/    FastAPI app, database models, providers, runner, tests
frontend/   Next.js app router UI
examples/   Demo Postman collection
```

## Requirements

- Python 3.12
- Node.js 20+
- npm
- uv for Python environment management

## Backend Setup

```bash
cd backend
uv venv .venv --python 3.12
uv pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Backend URL: `http://127.0.0.1:8000`

The backend uses `backend/aeroapi.db` locally. That file is ignored by Git.
See `backend/.env.example` for the optional database setting.

## Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

Frontend URL: `http://localhost:3001`

If your backend runs somewhere else, create `frontend/.env.local`:

```env
NEXT_PUBLIC_API_URL=http://127.0.0.1:8000
```
See `frontend/.env.example` for the default frontend API setting.

## Running A Demo

1. Start the backend and frontend.
2. Open `http://localhost:3001/new-run`.
3. Upload `examples/postman-demo.collection.json`.
4. Optionally upload or paste API docs, business rules, validation rules, workflow notes, or error contracts.
5. Use `demo-token` as the API token for deterministic local generation.
6. Click `Run tests`.
7. Open the completed run and download the generated Postman collection.

Use a real provider token only when you want AeroAPI to call the selected LLM provider.

## Postman Export

Completed runs can be exported as a Postman Collection v2.1 JSON file. The export groups generated cases by endpoint and writes each case as a Postman request with:

- request method, URL, headers, query params, and JSON body
- `prerequest` JavaScript for run metadata and base URL checks
- `test` JavaScript with status-code, response-time, and security assertions

Set `baseUrl` as a Postman collection or environment variable before running exported collections.

## Groq Notes

Groq model IDs change over time. The current UI can use models such as `qwen/qwen3-32b` and `llama-3.3-70b-versatile` when your Groq project has permission to call them. The backend retries malformed JSON responses once with a repair prompt before failing the run.

## Checks

Backend:

```bash
cd backend
.\.venv\Scripts\python.exe -m pytest
```

Frontend:

```bash
cd frontend
npm exec tsc -- --noEmit
npm audit
```

## Safety

Only run AeroAPI against APIs you own or have explicit permission to test. Deep mode and security-oriented payloads may trigger alerts or mutate data on poorly isolated systems.
