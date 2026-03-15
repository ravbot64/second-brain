from sqlalchemy import Column, String, JSON, DateTime
from sqlalchemy.sql import func
from .database import Base

class DBDocument(Base):
    __tablename__ = "documents"

    id = Column(String, primary_key=True, index=True)
    source = Column(String, nullable=False, index=True)
    content = Column(String, nullable=False)
    metadata_ = Column("metadata", JSON, default={})
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
