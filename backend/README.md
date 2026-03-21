# Second Brain Backend

Backend API for Second Brain (FastAPI + SQLAlchemy + Qdrant).

## Responsibilities

- Authentication (register, login, guest)
- User-scoped chat retrieval and response generation
- Document ingestion (file and raw text)
- Persistent chat history APIs
- Document and vector metadata management

## Run Locally

From this backend directory:

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```

Backend will run at:

- http://127.0.0.1:8000

## Environment

Copy and fill env values from:

- .env.example

Key variables include:

- DB_URL
- QDRANT_URL / QDRANT_PATH / QDRANT_API_KEY
- GOOGLE_API_KEY
- JWT_SECRET / JWT_ALGORITHM / JWT_EXPIRE_MINUTES
- CORS_ORIGINS

## Notes

- This README only covers backend setup.
- Project overview and live demo link are documented in the root README.
