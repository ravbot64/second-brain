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

            def read_plain_text(path: str) -> str:
                """Read text files robustly, including extension-less UTF-8 files."""
                with open(path, "rb") as f:
                    raw = f.read()

                # Reject likely-binary files early.
                if b"\x00" in raw:
                    raise ValueError("Unsupported file type")

                try:
                    text = raw.decode("utf-8")
                except UnicodeDecodeError:
                    # Fallback for common Windows-encoded text files.
                    text = raw.decode("cp1252")

                printable = sum(1 for ch in text if ch.isprintable() or ch in "\n\r\t")
                ratio = (printable / len(text)) if text else 0
                if text and ratio < 0.85:
                    raise ValueError("Unsupported file type")
                return text
            
            # Basic text parsing
            if filename_lower.endswith((".txt", ".md", ".csv")):
                content = read_plain_text(self.file_path)
            
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
                # Allow extension-less (or unknown extension) uploads if content is plain text.
                content = read_plain_text(self.file_path)

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
