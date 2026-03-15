from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, List
from datetime import datetime

class Document(BaseModel):
    id: Optional[str] = None
    content: str
    source: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
class Chunk(BaseModel):
    id: Optional[str] = None
    document_id: str
    content: str
    embedding: Optional[List[float]] = None
    chunk_index: int
    metadata: Dict[str, Any] = Field(default_factory=dict)
