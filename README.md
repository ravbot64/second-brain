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
