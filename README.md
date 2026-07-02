# Second Brain

Second Brain is a full-stack personal knowledge assistant with:

- FastAPI backend for auth, ingestion, retrieval, and chat APIs
- Next.js frontend for chat UI, knowledge management, and account flows
- PostgreSQL + Qdrant for structured metadata and vector search

## Live Demo

- https://second-brain-five-eta.vercel.app/

## Project Structure

- backend: API server, auth, ingestion pipeline, retrieval, and data models
- frontend: user interface, chat history, auth flows, and document management

## Local Development

1. Start backend

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```

2. Start frontend

```bash
cd frontend
npm install
npm run dev
```

3. Open app

- http://localhost:3000

## Environment

- Backend env vars: see backend/.env.example
- Frontend env vars:

```bash
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
```

## Deployment

- Frontend: Vercel (set `NEXT_PUBLIC_API_BASE_URL` to the deployed backend URL).
- Backend: Render. A `render.yaml` blueprint is included; secrets (`DB_URL`,
  `QDRANT_URL`, `QDRANT_API_KEY`, `GOOGLE_API_KEY`, `CORS_ORIGINS`) are set in the
  Render dashboard and never committed. `JWT_SECRET` is auto-generated.

### Cold starts (free tier)

Render's free tier spins the backend down after ~15 minutes of inactivity, so the
first request can take up to a minute. This repo mitigates that in two ways:

1. Frontend warmup + retry: the app pings the backend on load, shows a
   "waking up the server" banner, and automatically retries transient
   `502/503/504`/network errors with backoff so cold starts don't surface as errors.
2. Keep-alive workflow: `.github/workflows/keep-alive.yml` pings the health
   endpoint every 10 minutes. Add a repository variable `BACKEND_URL`
   (Settings → Secrets and variables → Actions → Variables) pointing at the API
   root, e.g. `https://your-service.onrender.com`.

## Security notes

- Passwords hashed with PBKDF2-HMAC-SHA256 (600k iterations); existing hashes stay valid.
- Strict CORS (explicit origins, methods, headers), security headers (HSTS, CSP,
  `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`), and per-endpoint
  rate limiting (stricter budget on `/api/auth/*`).
- Uploads are restricted to `.txt/.md/.csv/.pdf` (plus sniffed plain text) and size
  is enforced while streaming to disk.
- `JWT_SECRET` must be a strong secret (≥32 chars) in production or the API refuses
  to start.
