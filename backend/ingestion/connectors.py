from abc import ABC, abstractmethod
from typing import List, Optional
import uuid
import datetime
from models.document import Document

class BaseConnector(ABC):
    @abstractmethod
    def fetch_documents(self) -> List[Document]:
        """Fetch documents from the data source"""
        pass
        
class TextFileConnector(BaseConnector):
    def __init__(self, file_path: str, source_name: str = "local_file"):
        self.file_path = file_path
        self.source_name = source_name
        
    def fetch_documents(self) -> List[Document]:
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                content = f.read()
            return [
                Document(
                    id=str(uuid.uuid4()),
                    content=content,
                    source=self.source_name,
                    metadata={"file_path": self.file_path},
                    created_at=datetime.datetime.utcnow()
                )
            ]
        except Exception as e:
            print(f"Error reading file {self.file_path}: {e}")
            return []
