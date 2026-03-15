import asyncio
from qdrant_client.http.models import Distance, VectorParams, PayloadSchemaType
from .database import engine, Base
from .qdrant import client
from .models_db import DBDocument

COLLECTION_NAME = "second_brain_chunks"

def init_postgres():
    Base.metadata.create_all(bind=engine)

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

if __name__ == "__main__":
    print("Initializing databases...")
    init_postgres()
    init_qdrant()
    print("Databases initialized successfully.")
