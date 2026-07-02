from pathlib import Path
import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterator, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, EmailStr
from qdrant_client import models as qmodels
from sqlalchemy.exc import IntegrityError
import re

from core.auth import create_access_token, get_current_user, hash_password, verify_password
from core.config import settings
from core.database import SessionLocal
from core.embeddings import embedder
from core.models_db import DBDocument, DBUser, DBConversation, DBMessage
from core.qdrant import client
from ingestion.pipeline import IngestionPipeline, chunk_text
from ingestion.raw_text_connector import RawTextConnector
from ingestion.upload_connector import UploadFileConnector
from retrieval.retriever import retriever

router = APIRouter()
LEGACY_USER_ID = "legacy"
GUEST_RETENTION_HOURS = 24
SHARED_GUEST_USER_ID = "guest-shared"
SHARED_GUEST_EMAIL = "guest@secondbrain.local"

# Allow-list of accepted upload types. Extension-less files are permitted because
# the connector sniffs them for printable text and rejects binary content.
ALLOWED_UPLOAD_EXTENSIONS = {".txt", ".md", ".csv", ".pdf"}
UPLOAD_CHUNK_SIZE = 1024 * 1024  # 1 MB streaming chunks

# Chat model fallbacks: the configured model is tried first, then progressively
# older free-tier models, so a model that is unavailable in the current
# project/region degrades gracefully instead of dropping to raw snippets.
LLM_FALLBACK_MODELS = ["gemini-3-flash", "gemini-2.5-flash", "gemini-2.0-flash"]
_working_llm_model: Optional[str] = None


def generate_llm_answer(prompt: str) -> Optional[str]:
    """Return a grounded answer from Gemini, or None if no model produced text."""
    global _working_llm_model

    api_key = settings.GOOGLE_API_KEY
    if not api_key:
        return None

    from google import genai

    client_gen = genai.Client(api_key=api_key)

    candidates = [settings.LLM_MODEL] + [m for m in LLM_FALLBACK_MODELS if m != settings.LLM_MODEL]
    if _working_llm_model:
        candidates = [_working_llm_model] + [m for m in candidates if m != _working_llm_model]

    last_error = None
    for model_name in candidates:
        try:
            response = client_gen.models.generate_content(model=model_name, contents=prompt)
            text = (response.text or "").strip()
            if text:
                _working_llm_model = model_name
                return text
        except Exception as e:
            last_error = e
            continue

    if last_error:
        print(f"LLM Error (all candidate models failed): {last_error}")
    return None


def stream_llm_answer(prompt: str) -> Iterator[str]:
    """Yield answer text deltas from Gemini, with model fallback before first token."""
    global _working_llm_model

    api_key = settings.GOOGLE_API_KEY
    if not api_key:
        return

    from google import genai

    client_gen = genai.Client(api_key=api_key)

    candidates = [settings.LLM_MODEL] + [m for m in LLM_FALLBACK_MODELS if m != settings.LLM_MODEL]
    if _working_llm_model:
        candidates = [_working_llm_model] + [m for m in candidates if m != _working_llm_model]

    last_error = None
    for model_name in candidates:
        emitted = False
        try:
            stream = client_gen.models.generate_content_stream(model=model_name, contents=prompt)
            for chunk in stream:
                text = getattr(chunk, "text", None)
                if text:
                    emitted = True
                    yield text
        except Exception as e:
            last_error = e
            if emitted:
                # Never switch models mid-answer; a partial response was already sent.
                _working_llm_model = model_name
                return
            continue

        if emitted:
            _working_llm_model = model_name
            return

    if last_error:
        print(f"LLM stream error (all candidate models failed): {last_error}")


CHAT_HISTORY_TURNS = 10
CHAT_HISTORY_MSG_MAX_CHARS = 1500


def build_history_text(db, conversation_id: str, user_id: str) -> str:
    """Recent prior turns of a conversation, oldest first, bounded for prompt size."""
    msgs = (
        db.query(DBMessage)
        .filter(DBMessage.conversation_id == conversation_id, DBMessage.user_id == user_id)
        .order_by(DBMessage.created_at.asc())
        .all()
    )
    if not msgs:
        return ""

    lines = []
    for m in msgs[-CHAT_HISTORY_TURNS:]:
        role = "User" if m.role == "user" else "Assistant"
        content = (m.content or "").strip()
        if len(content) > CHAT_HISTORY_MSG_MAX_CHARS:
            content = content[:CHAT_HISTORY_MSG_MAX_CHARS] + "…"
        lines.append(f"{role}: {content}")
    return "\n".join(lines)


def build_chat_prompt(history_text: str, context: str, query: str) -> str:
    parts = [
        "You are a helpful assistant for the user's personal knowledge base. Use the "
        "provided context to answer accurately and concisely. If the context doesn't "
        "contain the answer, say so. Use Markdown formatting (lists, code blocks, bold) "
        "when it improves readability.",
    ]
    if history_text:
        parts.append(f"Conversation so far:\n{history_text}")
    parts.append(f"Context:\n{context}")
    parts.append(f"Question: {query}")
    return "\n\n".join(parts)


def slim_sources(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Compact citation payload for the wire and history (no full chunk text)."""
    return [
        {
            "score": r.get("score"),
            "title": r.get("title") or "Untitled",
            "source": r.get("source", "unknown"),
            "document_id": r.get("document_id", ""),
        }
        for r in results
    ]


def _sse(data: Dict[str, Any]) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


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


def _prepare_chat(db, current_user: DBUser, request: ChatRequest):
    """Resolve/create the conversation, set its title, and retrieve context.

    Returns (conversation, results, history_text). Raises LookupError if a
    referenced conversation does not belong to the user. Does not persist the
    incoming user message (callers do that).
    """
    visible_ids = visible_user_ids(current_user)
    docs = db.query(DBDocument.id).filter(DBDocument.user_id.in_(visible_ids)).all()
    allowed_document_ids = {d[0] for d in docs}

    if request.conversation_id:
        conversation = db.query(DBConversation).filter(
            DBConversation.id == request.conversation_id,
            DBConversation.user_id == current_user.id,
        ).first()
        if not conversation:
            raise LookupError("Conversation not found")
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

    # History is captured before the current user message is stored.
    history_text = build_history_text(db, conversation.id, current_user.id)

    if not allowed_document_ids:
        results: List[Dict[str, Any]] = []
    else:
        results = retriever.search(request.query, allowed_document_ids=allowed_document_ids)

    return conversation, results, history_text


def _compose_answer(results: List[Dict[str, Any]], history_text: str, query: str) -> str:
    if not results:
        return "I couldn't find any relevant information in your Second Brain."

    context = "\n\n".join(f"Source ({r['source']}):\n{r['content']}" for r in results)
    if settings.GOOGLE_API_KEY:
        prompt = build_chat_prompt(history_text, context, query)
        return generate_llm_answer(prompt) or ("Based on your notes: " + results[0]["content"])
    return f"Based on your notes, here is the most relevant snippet:\n\n\"{results[0]['content']}\""


@router.post("/chat", response_model=ChatResponse)
def handle_chat(request: ChatRequest, current_user: DBUser = Depends(get_current_user)):
    try:
        request.validate()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    db = SessionLocal()
    try:
        try:
            conversation, results, history_text = _prepare_chat(db, current_user, request)
        except LookupError:
            raise HTTPException(status_code=404, detail="Conversation not found")

        answer = _compose_answer(results, history_text, request.query)
        sources = slim_sources(results)

        db.add(DBMessage(
            id=str(uuid.uuid4()),
            conversation_id=conversation.id,
            user_id=current_user.id,
            role="user",
            content=request.query,
            sources=[],
        ))
        db.add(DBMessage(
            id=str(uuid.uuid4()),
            conversation_id=conversation.id,
            user_id=current_user.id,
            role="assistant",
            content=answer,
            sources=sources,
        ))
        conversation.updated_at = datetime.now(timezone.utc)
        db.commit()

        return ChatResponse(
            answer=answer,
            sources=sources,
            conversation_id=conversation.id,
            conversation_title=conversation.title,
        )
    finally:
        db.close()


@router.post("/chat/stream")
def handle_chat_stream(request: ChatRequest, current_user: DBUser = Depends(get_current_user)):
    """Server-Sent Events variant of /chat that streams the answer token-by-token."""
    try:
        request.validate()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    def event_stream() -> Iterator[str]:
        db = SessionLocal()
        try:
            try:
                conversation, results, history_text = _prepare_chat(db, current_user, request)
            except LookupError:
                yield _sse({"type": "error", "detail": "Conversation not found"})
                return

            sources = slim_sources(results)
            yield _sse({
                "type": "meta",
                "conversation_id": conversation.id,
                "conversation_title": conversation.title,
                "sources": sources,
            })

            db.add(DBMessage(
                id=str(uuid.uuid4()),
                conversation_id=conversation.id,
                user_id=current_user.id,
                role="user",
                content=request.query,
                sources=[],
            ))
            db.flush()

            chunks: List[str] = []
            if not results:
                text = "I couldn't find any relevant information in your Second Brain."
                chunks.append(text)
                yield _sse({"type": "delta", "text": text})
            elif settings.GOOGLE_API_KEY:
                context = "\n\n".join(f"Source ({r['source']}):\n{r['content']}" for r in results)
                prompt = build_chat_prompt(history_text, context, request.query)
                for delta in stream_llm_answer(prompt):
                    chunks.append(delta)
                    yield _sse({"type": "delta", "text": delta})
                if not "".join(chunks).strip():
                    fallback = "Based on your notes: " + results[0]["content"]
                    chunks.append(fallback)
                    yield _sse({"type": "delta", "text": fallback})
            else:
                text = f"Based on your notes, here is the most relevant snippet:\n\n\"{results[0]['content']}\""
                chunks.append(text)
                yield _sse({"type": "delta", "text": text})

            answer = "".join(chunks).strip()
            db.add(DBMessage(
                id=str(uuid.uuid4()),
                conversation_id=conversation.id,
                user_id=current_user.id,
                role="assistant",
                content=answer,
                sources=sources,
            ))
            conversation.updated_at = datetime.now(timezone.utc)
            db.commit()

            yield _sse({
                "type": "done",
                "conversation_id": conversation.id,
                "conversation_title": conversation.title,
            })
        except Exception as e:
            print(f"Chat stream error: {e}")
            try:
                db.rollback()
            except Exception:
                pass
            yield _sse({"type": "error", "detail": "Failed to generate response"})
        finally:
            db.close()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


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

    ext = Path(safe_name).suffix.lower()
    if ext and ext not in ALLOWED_UPLOAD_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type '{ext}'. Allowed: {', '.join(sorted(ALLOWED_UPLOAD_EXTENSIONS))} or plain text.",
        )

    # Enforce the size limit while streaming to disk. file.size is advisory and can
    # be None, so we count bytes ourselves and abort early to avoid filling the disk.
    max_size = settings.MAX_FILE_SIZE
    if file.size is not None and file.size > max_size:
        raise HTTPException(status_code=413, detail=f"File size exceeds {max_size / 1024 / 1024:.0f}MB limit")

    temp_path = os.path.join(temp_dir, f"{uuid.uuid4()}_{safe_name}")
    bytes_written = 0
    try:
        with open(temp_path, "wb") as buffer:
            while True:
                chunk = await file.read(UPLOAD_CHUNK_SIZE)
                if not chunk:
                    break
                bytes_written += len(chunk)
                if bytes_written > max_size:
                    raise HTTPException(
                        status_code=413,
                        detail=f"File size exceeds {max_size / 1024 / 1024:.0f}MB limit",
                    )
                buffer.write(chunk)
    except HTTPException:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise
    except Exception:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise HTTPException(status_code=400, detail="Failed to read uploaded file")

    if bytes_written == 0:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

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


@router.post("/reindex")
def reindex(current_user: DBUser = Depends(get_current_user)):
    """Rebuild all of the current user's vectors from the text stored in Postgres.

    Use this to repair an index whose vectors became inconsistent (e.g. mixed
    embedding spaces). It deletes the user's existing chunks and re-embeds every
    document through the current embedding path, so all vectors end up in one
    consistent space. Failures are reported per document instead of silently
    corrupting the index.
    """
    if not settings.GOOGLE_API_KEY:
        raise HTTPException(status_code=503, detail="Embedding API is not configured")

    db = SessionLocal()
    try:
        docs = db.query(DBDocument).filter(DBDocument.user_id == current_user.id).all()
        if not docs:
            return {"status": "success", "documents": 0, "chunks": 0, "failed": 0}

        # Remove this user's existing vectors so we don't leave stale/mismatched points.
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
            print(f"Reindex: failed to clear existing vectors for {current_user.id}: {e}")
            raise HTTPException(status_code=500, detail="Failed to clear existing vectors")

        total_chunks = 0
        failed = 0
        for doc in docs:
            try:
                chunks = chunk_text(doc.content)
                if not chunks:
                    continue
                embeddings = embedder.get_embeddings(chunks)
                points = [
                    qmodels.PointStruct(
                        id=str(uuid.uuid4()),
                        vector=embedding,
                        payload={
                            "document_id": doc.id,
                            "user_id": current_user.id,
                            "source": doc.source,
                            "chunk_index": i,
                            "content": text,
                            **(doc.metadata_ or {}),
                        },
                    )
                    for i, (text, embedding) in enumerate(zip(chunks, embeddings))
                ]
                client.upsert(collection_name="second_brain_chunks", points=points)
                total_chunks += len(points)
            except Exception as e:
                failed += 1
                print(f"Reindex: document {doc.id} failed: {e}")

        return {
            "status": "success" if failed == 0 else "partial",
            "documents": len(docs),
            "chunks": total_chunks,
            "failed": failed,
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
