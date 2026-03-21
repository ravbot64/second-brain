from pathlib import Path
import os
import shutil
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, EmailStr
from qdrant_client import models as qmodels
from sqlalchemy.exc import IntegrityError
import re

from core.auth import create_access_token, get_current_user, hash_password, verify_password
from core.config import settings
from core.database import SessionLocal
from core.models_db import DBDocument, DBUser, DBConversation, DBMessage
from core.qdrant import client
from ingestion.pipeline import IngestionPipeline
from ingestion.raw_text_connector import RawTextConnector
from ingestion.upload_connector import UploadFileConnector
from retrieval.retriever import retriever

router = APIRouter()
LEGACY_USER_ID = "legacy"
GUEST_RETENTION_HOURS = 24
SHARED_GUEST_USER_ID = "guest-shared"
SHARED_GUEST_EMAIL = "guest@secondbrain.local"


def visible_user_ids(current_user: DBUser) -> List[str]:
    ids = [current_user.id]
    if current_user.is_guest:
        ids.append(LEGACY_USER_ID)
    return ids


def cleanup_expired_guest_accounts(db, retention_hours: int = GUEST_RETENTION_HOURS) -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=retention_hours)
    expired_guest_rows = db.query(DBUser.id, DBUser.created_at).filter(DBUser.is_guest.is_(True)).all()

    expired_ids: List[str] = []
    for guest_id, created_at in expired_guest_rows:
        if guest_id == SHARED_GUEST_USER_ID:
            continue
        if created_at is None:
            continue
        created_at_utc = created_at if created_at.tzinfo else created_at.replace(tzinfo=timezone.utc)
        if created_at_utc < cutoff:
            expired_ids.append(guest_id)

    if not expired_ids:
        return

    try:
        client.delete(
            collection_name="second_brain_chunks",
            points_selector=qmodels.FilterSelector(
                filter=qmodels.Filter(
                    must=[
                        qmodels.FieldCondition(
                            key="user_id",
                            match=qmodels.MatchAny(any=expired_ids),
                        )
                    ]
                )
            ),
        )
    except Exception as e:
        print(f"Warning: Guest vector cleanup failed: {e}")

    db.query(DBDocument).filter(DBDocument.user_id.in_(expired_ids)).delete(synchronize_session=False)
    db.query(DBUser).filter(DBUser.id.in_(expired_ids)).delete(synchronize_session=False)
    db.commit()


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UpdateProfileRequest(BaseModel):
    full_name: str
    bio: str = ""


class DeleteAccountRequest(BaseModel):
    password: Optional[str] = None


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: Dict[str, Any]


class ChatRequest(BaseModel):
    query: str
    conversation_id: Optional[str] = None

    def validate(self):
        if not self.query or not self.query.strip():
            raise ValueError("Query cannot be empty")
        if len(self.query) > settings.MAX_QUERY_LENGTH:
            raise ValueError(f"Query exceeds maximum length of {settings.MAX_QUERY_LENGTH} characters")
        return self


class ChatResponse(BaseModel):
    answer: str
    sources: List[Dict[str, Any]]
    conversation_id: str
    conversation_title: str


class RawTextRequest(BaseModel):
    text: str
    title: str


def _serialize_message(message: DBMessage) -> Dict[str, Any]:
    return {
        "id": message.id,
        "role": message.role,
        "content": message.content,
        "sources": message.sources or [],
        "timestamp": message.created_at,
    }


def _serialize_conversation(db, conv: DBConversation) -> Dict[str, Any]:
    messages = (
        db.query(DBMessage)
        .filter(DBMessage.conversation_id == conv.id, DBMessage.user_id == conv.user_id)
        .order_by(DBMessage.created_at.asc())
        .all()
    )
    return {
        "id": conv.id,
        "title": conv.title,
        "created_at": conv.created_at,
        "updated_at": conv.updated_at,
        "messages": [_serialize_message(m) for m in messages],
    }


@router.get("/history")
def list_conversations(current_user: DBUser = Depends(get_current_user)):
    db = SessionLocal()
    try:
        conversations = (
            db.query(DBConversation)
            .filter(DBConversation.user_id == current_user.id)
            .order_by(DBConversation.created_at.desc())
            .all()
        )
        return [_serialize_conversation(db, conv) for conv in conversations]
    finally:
        db.close()


@router.post("/history/conversations")
def create_conversation(current_user: DBUser = Depends(get_current_user)):
    db = SessionLocal()
    try:
        conv = DBConversation(
            id=str(uuid.uuid4()),
            user_id=current_user.id,
            title="New conversation",
        )
        db.add(conv)
        db.commit()
        db.refresh(conv)
        return _serialize_conversation(db, conv)
    finally:
        db.close()


@router.delete("/history/conversations/{conversation_id}")
def delete_conversation(conversation_id: str, current_user: DBUser = Depends(get_current_user)):
    db = SessionLocal()
    try:
        conv = db.query(DBConversation).filter(
            DBConversation.id == conversation_id,
            DBConversation.user_id == current_user.id,
        ).first()
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")

        db.query(DBMessage).filter(
            DBMessage.conversation_id == conversation_id,
            DBMessage.user_id == current_user.id,
        ).delete(synchronize_session=False)
        db.delete(conv)
        db.commit()
        return {"status": "success"}
    finally:
        db.close()


@router.post("/auth/register", response_model=AuthResponse)
def register(request: RegisterRequest):
    email = str(request.email).strip().lower()
    if not email:
        raise HTTPException(status_code=400, detail="Email is required")
    if len(request.full_name.strip()) < 2:
        raise HTTPException(status_code=400, detail="Full name must be at least 2 characters")
    if len(request.full_name) > 80:
        raise HTTPException(status_code=400, detail="Full name must be <= 80 characters")
    if len(request.password) < 8 or len(request.password) > 128:
        raise HTTPException(status_code=400, detail="Password must be between 8 and 128 characters")
    if not re.search(r"[A-Z]", request.password):
        raise HTTPException(status_code=400, detail="Password must include an uppercase letter")
    if not re.search(r"[a-z]", request.password):
        raise HTTPException(status_code=400, detail="Password must include a lowercase letter")
    if not re.search(r"\d", request.password):
        raise HTTPException(status_code=400, detail="Password must include a number")
    if not re.search(r"[^A-Za-z0-9]", request.password):
        raise HTTPException(status_code=400, detail="Password must include a special character")

    db = SessionLocal()
    try:
        existing = db.query(DBUser).filter(DBUser.email == email).first()
        if existing:
            raise HTTPException(status_code=409, detail="Email already registered")

        user = DBUser(
            id=str(uuid.uuid4()),
            email=email,
            password_hash=hash_password(request.password),
            full_name=request.full_name.strip(),
            is_guest=False,
        )
        db.add(user)
        db.commit()

        token = create_access_token(user.id)
        return AuthResponse(
            access_token=token,
            user={
                "id": user.id,
                "email": user.email,
                "is_guest": user.is_guest,
                "full_name": user.full_name,
                "bio": user.bio or "",
            },
        )
    finally:
        db.close()


@router.post("/auth/login", response_model=AuthResponse)
def login(request: LoginRequest):
    email = str(request.email).strip().lower()
    db = SessionLocal()
    try:
        user = db.query(DBUser).filter(DBUser.email == email).first()
        if not user or not verify_password(request.password, user.password_hash):
            raise HTTPException(status_code=401, detail="Invalid credentials")

        token = create_access_token(user.id)
        return AuthResponse(
            access_token=token,
            user={
                "id": user.id,
                "email": user.email,
                "is_guest": user.is_guest,
                "full_name": user.full_name,
                "bio": user.bio or "",
            },
        )
    finally:
        db.close()


@router.post("/auth/guest", response_model=AuthResponse)
def guest_login():
    db = SessionLocal()
    try:
        # Prevent unbounded guest-account growth.
        cleanup_expired_guest_accounts(db)

        user = db.query(DBUser).filter(DBUser.id == SHARED_GUEST_USER_ID).first()
        if not user:
            user = db.query(DBUser).filter(DBUser.email == SHARED_GUEST_EMAIL).first()

        if not user:
            user = DBUser(
                id=SHARED_GUEST_USER_ID,
                email=SHARED_GUEST_EMAIL,
                password_hash=hash_password(str(uuid.uuid4())),
                full_name="Guest User",
                bio="Shared guest account",
                is_guest=True,
            )
            db.add(user)
            try:
                db.commit()
            except IntegrityError:
                db.rollback()
                user = db.query(DBUser).filter(DBUser.id == SHARED_GUEST_USER_ID).first()
                if not user:
                    user = db.query(DBUser).filter(DBUser.email == SHARED_GUEST_EMAIL).first()
                if not user:
                    raise HTTPException(status_code=500, detail="Failed to provision guest account")

        token = create_access_token(user.id, expires_minutes=60 * 24)
        return AuthResponse(
            access_token=token,
            user={
                "id": user.id,
                "email": user.email,
                "is_guest": user.is_guest,
                "full_name": user.full_name,
                "bio": user.bio or "",
            },
        )
    finally:
        db.close()


@router.get("/auth/me")
def me(current_user: DBUser = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "email": current_user.email,
        "is_guest": current_user.is_guest,
        "full_name": current_user.full_name,
        "bio": current_user.bio or "",
    }


@router.patch("/auth/profile")
def update_profile(request: UpdateProfileRequest, current_user: DBUser = Depends(get_current_user)):
    if current_user.is_guest:
        raise HTTPException(status_code=403, detail="Guest profiles cannot be edited")

    name = request.full_name.strip()
    if len(name) < 2:
        raise HTTPException(status_code=400, detail="Full name must be at least 2 characters")
    if len(name) > 80:
        raise HTTPException(status_code=400, detail="Full name must be <= 80 characters")
    if len(request.bio) > 280:
        raise HTTPException(status_code=400, detail="Bio must be <= 280 characters")

    db = SessionLocal()
    try:
        user = db.query(DBUser).filter(DBUser.id == current_user.id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        user.full_name = name
        user.bio = request.bio.strip()
        db.commit()
        return {
            "id": user.id,
            "email": user.email,
            "is_guest": user.is_guest,
            "full_name": user.full_name,
            "bio": user.bio or "",
        }
    finally:
        db.close()


@router.post("/auth/delete-account")
def delete_account(request: DeleteAccountRequest, current_user: DBUser = Depends(get_current_user)):
    # Registered users must confirm password before destructive account deletion.
    if not current_user.is_guest:
        if not request.password:
            raise HTTPException(status_code=400, detail="Password is required to delete account")
        if not verify_password(request.password, current_user.password_hash):
            raise HTTPException(status_code=401, detail="Invalid password")

    try:
        client.delete(
            collection_name="second_brain_chunks",
            points_selector=qmodels.FilterSelector(
                filter=qmodels.Filter(
                    must=[
                        qmodels.FieldCondition(
                            key="user_id",
                            match=qmodels.MatchValue(value=current_user.id),
                        )
                    ]
                )
            ),
        )
    except Exception as e:
        print(f"Warning: Qdrant delete-account cleanup failed for user {current_user.id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to clean vector data")

    db = SessionLocal()
    try:
        db.query(DBMessage).filter(DBMessage.user_id == current_user.id).delete(synchronize_session=False)
        db.query(DBConversation).filter(DBConversation.user_id == current_user.id).delete(synchronize_session=False)
        db.query(DBDocument).filter(DBDocument.user_id == current_user.id).delete(synchronize_session=False)
        db.query(DBUser).filter(DBUser.id == current_user.id).delete(synchronize_session=False)
        db.commit()
        return {"status": "success", "message": "Account deleted"}
    finally:
        db.close()


@router.post("/chat", response_model=ChatResponse)
def handle_chat(request: ChatRequest, current_user: DBUser = Depends(get_current_user)):
    try:
        request.validate()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    db = SessionLocal()
    try:
        visible_ids = visible_user_ids(current_user)
        docs = db.query(DBDocument.id).filter(DBDocument.user_id.in_(visible_ids)).all()
        allowed_document_ids = {d[0] for d in docs}

        if request.conversation_id:
            conversation = db.query(DBConversation).filter(
                DBConversation.id == request.conversation_id,
                DBConversation.user_id == current_user.id,
            ).first()
            if not conversation:
                raise HTTPException(status_code=404, detail="Conversation not found")
        else:
            conversation = DBConversation(
                id=str(uuid.uuid4()),
                user_id=current_user.id,
                title="New conversation",
            )
            db.add(conversation)
            db.flush()

        trimmed_query = request.query.strip()
        first_user_message = db.query(DBMessage.id).filter(
            DBMessage.conversation_id == conversation.id,
            DBMessage.user_id == current_user.id,
            DBMessage.role == "user",
        ).first()
        if not first_user_message:
            conversation.title = trimmed_query[:42] + ("…" if len(trimmed_query) > 42 else "")

        if not allowed_document_ids:
            results: List[Dict[str, Any]] = []
            answer = "I couldn't find any relevant information in your Second Brain."
        else:
            results = retriever.search(request.query, allowed_document_ids=allowed_document_ids)
            if not results:
                answer = "I couldn't find any relevant information in your Second Brain."
            else:
                context = "\n\n".join([f"Source ({r['source']}):\n{r['content']}" for r in results])

                api_key = settings.GOOGLE_API_KEY
                if api_key:
                    from google import genai

                    client_gen = genai.Client(api_key=api_key)
                    try:
                        response = client_gen.models.generate_content(
                            model=settings.LLM_MODEL,
                            contents=f"You are a helpful assistant. Use the provided context to answer the user's question accurately. If the context doesn't contain the answer, say so.\n\nContext:\n{context}\n\nQuestion: {request.query}",
                        )
                        answer = response.text
                    except Exception as e:
                        print(f"LLM Error: {e}")
                        answer = "Based on your notes: " + results[0]["content"]
                else:
                    answer = f"Based on your notes, here is the most relevant snippet:\n\n\"{results[0]['content']}\""

        user_msg = DBMessage(
            id=str(uuid.uuid4()),
            conversation_id=conversation.id,
            user_id=current_user.id,
            role="user",
            content=request.query,
            sources=[],
        )
        assistant_msg = DBMessage(
            id=str(uuid.uuid4()),
            conversation_id=conversation.id,
            user_id=current_user.id,
            role="assistant",
            content=answer,
            sources=results,
        )
        db.add(user_msg)
        db.add(assistant_msg)
        conversation.updated_at = datetime.now(timezone.utc)
        db.commit()

        return ChatResponse(
            answer=answer,
            sources=results,
            conversation_id=conversation.id,
            conversation_title=conversation.title,
        )
    finally:
        db.close()


@router.post("/ingest/upload")
async def upload_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    current_user: DBUser = Depends(get_current_user),
):
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

    user_id = current_user.id

    def process_upload_background():
        try:
            connector = UploadFileConnector(temp_path, safe_name)
            pipeline = IngestionPipeline(connector, user_id=user_id)
            pipeline.process()
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    background_tasks.add_task(process_upload_background)
    return {"status": "processing", "message": f"Ingesting {safe_name} in the background"}


@router.post("/ingest/text")
def ingest_text(request: RawTextRequest, background_tasks: BackgroundTasks, current_user: DBUser = Depends(get_current_user)):
    if not request.title or not request.title.strip():
        raise HTTPException(status_code=400, detail="Title cannot be empty")
    if len(request.title) > 500:
        raise HTTPException(status_code=400, detail="Title exceeds 500 character limit")
    if not request.text or not request.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty")
    if len(request.text.encode("utf-8")) > settings.MAX_CONTENT_LENGTH:
        raise HTTPException(
            status_code=413,
            detail=f"Text exceeds {settings.MAX_CONTENT_LENGTH // 1024 // 1024}MB limit",
        )

    user_id = current_user.id

    def process_background():
        connector = RawTextConnector(request.text, request.title)
        pipeline = IngestionPipeline(connector, user_id=user_id)
        pipeline.process()

    background_tasks.add_task(process_background)
    return {"status": "processing", "message": f"Ingesting text '{request.title}' in the background"}


@router.get("/documents")
def list_documents(current_user: DBUser = Depends(get_current_user)):
    db = SessionLocal()
    try:
        docs = db.query(DBDocument).filter(DBDocument.user_id.in_(visible_user_ids(current_user))).all()
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


@router.get("/documents/{doc_id}")
def get_document(doc_id: str, current_user: DBUser = Depends(get_current_user)):
    db = SessionLocal()
    try:
        doc = db.query(DBDocument).filter(
            DBDocument.id == doc_id,
            DBDocument.user_id.in_(visible_user_ids(current_user)),
        ).first()
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        return {
            "id": doc.id,
            "source": doc.source,
            "title": (doc.metadata_ or {}).get("title", (doc.metadata_ or {}).get("filename", "Unknown")),
            "content": doc.content,
            "created_at": doc.created_at,
        }
    finally:
        db.close()


@router.get("/stats")
def get_stats(current_user: DBUser = Depends(get_current_user)):
    db = SessionLocal()
    try:
        scoped_user_ids = visible_user_ids(current_user)
        doc_count = db.query(DBDocument).filter(DBDocument.user_id.in_(scoped_user_ids)).count()
        scoped_doc_rows = db.query(DBDocument.id).filter(DBDocument.user_id.in_(scoped_user_ids)).all()
        scoped_doc_ids = [row[0] for row in scoped_doc_rows]

        try:
            if not scoped_doc_ids:
                chunk_count = 0
            else:
                count_result = client.count(
                    collection_name="second_brain_chunks",
                    count_filter=qmodels.Filter(
                        must=[
                            qmodels.FieldCondition(
                                key="document_id",
                                match=qmodels.MatchAny(any=scoped_doc_ids),
                            )
                        ]
                    ),
                    exact=True,
                )
                chunk_count = count_result.count
        except Exception as e:
            print(f"Warning: Could not get Qdrant info: {e}")
            chunk_count = 0

        return {
            "document_count": doc_count,
            "chunk_count": chunk_count,
            "avg_chunks_per_doc": (chunk_count // doc_count) if doc_count > 0 else 0,
        }
    finally:
        db.close()


@router.delete("/documents/{doc_id}")
def delete_document(doc_id: str, current_user: DBUser = Depends(get_current_user)):
    db = SessionLocal()
    try:
        doc = db.query(DBDocument).filter(
            DBDocument.id == doc_id,
            DBDocument.user_id.in_(visible_user_ids(current_user)),
        ).first()
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        if doc.user_id == LEGACY_USER_ID:
            raise HTTPException(status_code=403, detail="Sample legacy documents cannot be deleted")

        try:
            client.delete(
                collection_name="second_brain_chunks",
                points_selector=qmodels.FilterSelector(
                    filter=qmodels.Filter(
                        must=[
                            qmodels.FieldCondition(key="document_id", match=qmodels.MatchValue(value=doc_id)),
                            qmodels.FieldCondition(key="user_id", match=qmodels.MatchValue(value=current_user.id)),
                        ]
                    )
                ),
            )
        except Exception as e:
            err_text = str(e)
            if "Index required but not found" in err_text and "document_id" in err_text:
                try:
                    client.create_payload_index(
                        collection_name="second_brain_chunks",
                        field_name="document_id",
                        field_schema=qmodels.PayloadSchemaType.KEYWORD,
                    )
                    client.create_payload_index(
                        collection_name="second_brain_chunks",
                        field_name="user_id",
                        field_schema=qmodels.PayloadSchemaType.KEYWORD,
                    )
                    client.delete(
                        collection_name="second_brain_chunks",
                        points_selector=qmodels.FilterSelector(
                            filter=qmodels.Filter(
                                must=[
                                    qmodels.FieldCondition(key="document_id", match=qmodels.MatchValue(value=doc_id)),
                                    qmodels.FieldCondition(key="user_id", match=qmodels.MatchValue(value=current_user.id)),
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

        db.delete(doc)
        db.commit()
        return {"status": "success", "message": f"Deleted document {doc_id}"}
    finally:
        db.close()
