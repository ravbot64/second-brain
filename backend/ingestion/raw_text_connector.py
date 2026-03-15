from typing import List
import uuid
import datetime
from models.document import Document
from .connectors import BaseConnector

class RawTextConnector(BaseConnector):
    def __init__(self, text_content: str, title: str):
        self.text_content = text_content
        self.title = title
        
    def fetch_documents(self) -> List[Document]:
        return [
            Document(
                id=str(uuid.uuid4()),
                content=self.text_content,
                source="raw_note",
                metadata={"title": self.title, "source": "raw_note"},
                created_at=datetime.datetime.utcnow()
            )
        ]
