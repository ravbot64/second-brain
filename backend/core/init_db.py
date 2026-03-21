import asyncio
from qdrant_client.http.models import Distance, VectorParams, PayloadSchemaType
from .database import engine, Base
from .qdrant import client
from sqlalchemy import inspect, text
from .models_db import DBDocument, DBUser

COLLECTION_NAME = "second_brain_chunks"

def init_postgres():
    Base.metadata.create_all(bind=engine)

    # Lightweight migration for older deployments created before auth/user scoping.
    inspector = inspect(engine)
    if engine.dialect.name.startswith("postgres") and "documents" in inspector.get_table_names():
        columns = {c["name"] for c in inspector.get_columns("documents")}
        if "user_id" not in columns:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE documents ADD COLUMN user_id VARCHAR"))
                conn.execute(text("UPDATE documents SET user_id = 'legacy' WHERE user_id IS NULL"))
                conn.execute(text("ALTER TABLE documents ALTER COLUMN user_id SET NOT NULL"))

    if "users" in inspector.get_table_names():
        user_columns = {c["name"] for c in inspector.get_columns("users")}
        with engine.begin() as conn:
            if "full_name" not in user_columns:
                conn.execute(text("ALTER TABLE users ADD COLUMN full_name VARCHAR"))
            if "bio" not in user_columns:
                conn.execute(text("ALTER TABLE users ADD COLUMN bio VARCHAR"))

def init_qdrant():
    collections = client.get_collections().collections
    exists = any(c.name == COLLECTION_NAME for c in collections)
    
    if not exists:
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=384, distance=Distance.COSINE),
        )

    # Required for delete-by-filter on Qdrant Cloud.
    try:
        client.create_payload_index(
            collection_name=COLLECTION_NAME,
            field_name="document_id",
            field_schema=PayloadSchemaType.KEYWORD,
        )
    except Exception as e:
        # Index may already exist depending on prior initialization.
        if "already exists" not in str(e).lower():
            raise

    # Required for per-user vector filtering.
    try:
        client.create_payload_index(
            collection_name=COLLECTION_NAME,
            field_name="user_id",
            field_schema=PayloadSchemaType.KEYWORD,
        )
    except Exception as e:
        if "already exists" not in str(e).lower():
            raise

if __name__ == "__main__":
    print("Initializing databases...")
    init_postgres()
    init_qdrant()
    print("Databases initialized successfully.")
