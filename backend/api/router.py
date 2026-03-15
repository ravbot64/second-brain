from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import List, Dict, Any
import os
import uuid
from pathlib import Path

from ingestion.pipeline import IngestionPipeline
from retrieval.retriever import retriever
from core.config import settings

router = APIRouter()

class ChatRequest(BaseModel):
    query: str
    
    def validate(self):
        if not self.query or not self.query.strip():
            raise ValueError("Query cannot be empty")
        if len(self.query) > settings.MAX_QUERY_LENGTH:
            raise ValueError(f"Query exceeds maximum length of {settings.MAX_QUERY_LENGTH} characters")
        return self
    
class ChatResponse(BaseModel):
    answer: str
    sources: List[Dict[str, Any]]

@router.post("/chat", response_model=ChatResponse)
def handle_chat(request: ChatRequest):
    try:
        request.validate()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    # 1. Retrieve context
    results = retriever.search(request.query)
    
    if not results:
        return ChatResponse(answer="I couldn't find any relevant information in your Second Brain.", sources=[])
        
    context = "\n\n".join([f"Source ({r['source']}):\n{r['content']}" for r in results])
    
    # 2. Generate Answer using Gemini
    api_key = settings.GOOGLE_API_KEY
    if api_key:
        from google import genai
        client = genai.Client(api_key=api_key)
        try:
            response = client.models.generate_content(
                model=settings.LLM_MODEL,
                contents=f"You are a helpful assistant. Use the provided context to answer the user's question accurately. If the context doesn't contain the answer, say so.\n\nContext:\n{context}\n\nQuestion: {request.query}"
            )
            answer = response.text
        except Exception as e:
            print(f"LLM Error: {e}")
            answer = f"Based on your notes: " + results[0]['content']
    else:
        # Fallback to pure retrieval logic for demo
        answer = f"Based on your notes, here is the most relevant snippet:\n\n\"{results[0]['content']}\""

    return ChatResponse(answer=answer, sources=results)

from fastapi import UploadFile, File
from ingestion.upload_connector import UploadFileConnector
import shutil

@router.post("/ingest/upload")
async def upload_file(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    # Save the file temporarily
    temp_dir = "./temp_uploads"
    os.makedirs(temp_dir, exist_ok=True)

    safe_name = Path(file.filename or "upload.bin").name
    if not safe_name:
        raise HTTPException(status_code=400, detail="Invalid file name")
    
    if file.size and file.size > settings.MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail=f"File size exceeds {settings.MAX_FILE_SIZE / 1024 / 1024:.0f}MB limit")

    temp_path = os.path.join(temp_dir, f"{uuid.uuid4()}_{safe_name}")
    
    with open(temp_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    def process_upload_background():
        try:
            connector = UploadFileConnector(temp_path, safe_name)
            pipeline = IngestionPipeline(connector)
            pipeline.process()
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        
    background_tasks.add_task(process_upload_background)
    return {"status": "processing", "message": f"Ingesting {safe_name} in the background"}

from core.database import SessionLocal
from core.models_db import DBDocument
from qdrant_client import models as qmodels

@router.get("/documents")
def list_documents():
    db = SessionLocal()
    try:
        docs = db.query(DBDocument).all()
        return [
            {
                "id": d.id,
                "source": d.source,
                "title": (d.metadata_ or {}).get("title", (d.metadata_ or {}).get("filename", "Unknown")),
                "content_snippet": (d.content[:100] + "...") if len(d.content) > 100 else d.content,
                "created_at": d.created_at,
            }
            for d in docs
        ]
    finally:
        db.close()

@router.get("/stats")
def get_stats():
    """Get statistics about documents and vectors in the brain."""
    db = SessionLocal()
    try:
        doc_count = db.query(DBDocument).count()
        
        # Get Qdrant collection info
        from core.qdrant import client
        try:
            collection_info = client.get_collection("second_brain_chunks")
            chunk_count = collection_info.points_count
        except Exception as e:
            print(f"Warning: Could not get Qdrant info: {e}")
            chunk_count = 0
        
        return {"document_count": doc_count, "chunk_count": chunk_count, "avg_chunks_per_doc": (chunk_count // doc_count) if doc_count > 0 else 0}
    finally:
        db.close()

@router.delete("/documents/{doc_id}")
def delete_document(doc_id: str):
    db = SessionLocal()
    try:
        doc = db.query(DBDocument).filter(DBDocument.id == doc_id).first()
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
        
        # Delete from Qdrant first to avoid orphaning vectors
        from core.qdrant import client
        try:
            client.delete(
                collection_name="second_brain_chunks",
                points_selector=qmodels.FilterSelector(
                    filter=qmodels.Filter(
                        must=[
                            qmodels.FieldCondition(
                                key="document_id",
                                match=qmodels.MatchValue(value=doc_id)
                            )
                        ]
                    )
                )
            )
        except Exception as e:
            err_text = str(e)
            if "Index required but not found" in err_text and "document_id" in err_text:
                # Backfill index on older collections, then retry the delete once.
                try:
                    client.create_payload_index(
                        collection_name="second_brain_chunks",
                        field_name="document_id",
                        field_schema=qmodels.PayloadSchemaType.KEYWORD,
                    )
                    client.delete(
                        collection_name="second_brain_chunks",
                        points_selector=qmodels.FilterSelector(
                            filter=qmodels.Filter(
                                must=[
                                    qmodels.FieldCondition(
                                        key="document_id",
                                        match=qmodels.MatchValue(value=doc_id),
                                    )
                                ]
                            )
                        ),
                    )
                except Exception as retry_err:
                    print(f"Warning: Qdrant deletion retry failed for doc {doc_id}: {retry_err}")
                    raise HTTPException(status_code=500, detail="Failed to delete from vector store")
            else:
                print(f"Warning: Qdrant deletion failed for doc {doc_id}: {e}")
                raise HTTPException(status_code=500, detail="Failed to delete from vector store")
        
        # Delete from SQLite after vector deletion succeeds
        db.delete(doc)
        db.commit()
        return {"status": "success", "message": f"Deleted document {doc_id}"}
    finally:
        db.close()

class RawTextRequest(BaseModel):
    text: str
    title: str

from ingestion.raw_text_connector import RawTextConnector

@router.post("/ingest/text")
def ingest_text(request: RawTextRequest, background_tasks: BackgroundTasks):
    if not request.title or not request.title.strip():
        raise HTTPException(status_code=400, detail="Title cannot be empty")
    if len(request.title) > 500:
        raise HTTPException(status_code=400, detail="Title exceeds 500 character limit")
    if not request.text or not request.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty")
    if len(request.text.encode("utf-8")) > settings.MAX_CONTENT_LENGTH:
        raise HTTPException(
            status_code=413,
            detail=f"Text exceeds {settings.MAX_CONTENT_LENGTH // 1024 // 1024}MB limit"
        )

    def process_background():
        connector = RawTextConnector(request.text, request.title)
        pipeline = IngestionPipeline(connector)
        pipeline.process()

    background_tasks.add_task(process_background)
    return {"status": "processing", "message": f"Ingesting text '{request.title}' in the background"}
