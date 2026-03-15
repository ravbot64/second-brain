import os
from typing import List
import uuid
import datetime
from fastapi import UploadFile
from models.document import Document
from .connectors import BaseConnector
import pypdf

class UploadFileConnector(BaseConnector):
    def __init__(self, file_path: str, filename: str):
        self.file_path = file_path
        self.filename = filename
        
    def fetch_documents(self) -> List[Document]:
        try:
            content = ""
            filename_lower = self.filename.lower()
            
            # Basic text parsing
            if filename_lower.endswith((".txt", ".md", ".csv")):
                with open(self.file_path, "r", encoding="utf-8") as f:
                    content = f.read()
            
            # PDF parsing
            elif filename_lower.endswith(".pdf"):
                with open(self.file_path, "rb") as f:
                    reader = pypdf.PdfReader(f)
                    page_texts = []
                    for page in reader.pages:
                        text = page.extract_text() or ""
                        text = text.strip()
                        if text:
                            page_texts.append(text)

                    content = "\n\n".join(page_texts)
            else:
                raise ValueError("Unsupported file type")

            if not content.strip():
                raise ValueError(
                    "No extractable text found in file. If this is a scanned PDF/image-based PDF, OCR is required before ingestion."
                )
                
            return [
                Document(
                    id=str(uuid.uuid4()),
                    content=content,
                    source="file_upload",
                    metadata={"filename": self.filename, "file_path": self.file_path},
                    created_at=datetime.datetime.utcnow()
                )
            ]
        except Exception as e:
            print(f"Error reading file {self.file_path}: {e}")
            return []
