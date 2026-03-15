from typing import List
import uuid
from models.document import Document
from core.embeddings import embedder
from core.qdrant import client
from core.database import SessionLocal
from core.models_db import DBDocument
from .connectors import BaseConnector
from qdrant_client import models as qmodels

class IngestionPipeline:
    def __init__(self, connector: BaseConnector):
        self.connector = connector
        self.db = SessionLocal()

    def chunk_text(self, text: str) -> List[str]:
        """Simple sliding window chunking."""
        from core.config import settings
        chunk_size = settings.CHUNK_SIZE
        overlap = settings.CHUNK_OVERLAP
        chunks = []
        if not text:
            return chunks
        
        words = text.split()
        for i in range(0, len(words), chunk_size - overlap):
            chunk_words = words[i:i + chunk_size]
            chunks.append(" ".join(chunk_words))
            if i + chunk_size >= len(words):
                break
        return chunks

    def process(self):
        print(f"Starting ingestion with {self.connector.__class__.__name__}")
        try:
            documents = self.connector.fetch_documents()
        except Exception as e:
            print(f"Failed to fetch documents: {e}")
            self.db.close()
            return
        
        total_chunks_saved = 0
        for doc in documents:
            inserted_point_ids: List[str] = []
            try:
                # 1. Chunk + embed before any persistence side effects.
                text_chunks = self.chunk_text(doc.content)
                if not text_chunks:
                    raise ValueError("Document has no chunkable text; skipping ingestion")

                points: List[qmodels.PointStruct] = []

                embeddings = embedder.get_embeddings(text_chunks)

                # 2. Save vectors first so DB does not reference missing vectors.
                for i, (text, embedding) in enumerate(zip(text_chunks, embeddings)):
                    chunk_id = str(uuid.uuid4())
                    inserted_point_ids.append(chunk_id)
                    points.append(
                        qmodels.PointStruct(
                            id=chunk_id,
                            vector=embedding,
                            payload={
                                "document_id": doc.id,
                                "source": doc.source,
                                "chunk_index": i,
                                "content": text,
                                **doc.metadata
                            }
                        )
                    )

                client.upsert(
                    collection_name="second_brain_chunks",
                    points=points
                )

                # 3. Commit document metadata only after vector write succeeds.
                db_doc = DBDocument(
                    id=doc.id,
                    source=doc.source,
                    content=doc.content,
                    metadata_=doc.metadata
                )
                self.db.add(db_doc)
                self.db.commit()
                total_chunks_saved += len(inserted_point_ids)
            except Exception as e:
                self.db.rollback()

                # Best-effort compensation if DB commit fails after vector upsert.
                if inserted_point_ids:
                    try:
                        client.delete(
                            collection_name="second_brain_chunks",
                            points_selector=qmodels.PointIdsList(points=inserted_point_ids)
                        )
                    except Exception as cleanup_err:
                        print(f"Qdrant cleanup failed for doc {doc.id}: {cleanup_err}")

                print(f"Failed to ingest document {doc.id}: {e}")
                
        print(f"Ingestion complete: {len(documents)} docs and {total_chunks_saved} chunks saved.")
        self.db.close()
