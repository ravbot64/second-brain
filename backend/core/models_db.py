from sqlalchemy import Column, String, JSON, DateTime, Boolean
from sqlalchemy.sql import func
from .database import Base


class DBUser(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    full_name = Column(String, nullable=True)
    bio = Column(String, nullable=True)
    is_guest = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

class DBDocument(Base):
    __tablename__ = "documents"

    id = Column(String, primary_key=True, index=True)
    user_id = Column(String, nullable=False, index=True)
    source = Column(String, nullable=False, index=True)
    content = Column(String, nullable=False)
    metadata_ = Column("metadata", JSON, default={})
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class DBConversation(Base):
    __tablename__ = "conversations"

    id = Column(String, primary_key=True, index=True)
    user_id = Column(String, nullable=False, index=True)
    title = Column(String, nullable=False, default="New conversation")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class DBMessage(Base):
    __tablename__ = "messages"

    id = Column(String, primary_key=True, index=True)
    conversation_id = Column(String, nullable=False, index=True)
    user_id = Column(String, nullable=False, index=True)
    role = Column(String, nullable=False)
    content = Column(String, nullable=False)
    sources = Column(JSON, default=[])
    created_at = Column(DateTime(timezone=True), server_default=func.now())
