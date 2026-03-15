from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database: PostgreSQL (tested) or SQLite (local dev only)
    # For cloud: postgresql://user:password@host:5432/dbname
    # For local: sqlite:///./second_brain.db
    DB_URL: str = "sqlite:///./second_brain.db"
    
    # Qdrant: Cloud or local path
    # For cloud: https://xxx.qdrant.io:6333
    # For local: ./qdrant_data
    QDRANT_URL: str = ""  # If empty, uses local path
    QDRANT_PATH: str = "./qdrant_data"
    QDRANT_API_KEY: str = ""  # Required if using cloud Qdrant
    
    GOOGLE_API_KEY: str = ""  # Google Gemini API key
    
    CORS_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"
    CORS_ALLOW_CREDENTIALS: bool = True
    MAX_FILE_SIZE: int = 50 * 1024 * 1024  # 50MB
    MAX_CONTENT_LENGTH: int = 10 * 1024 * 1024  # 10MB per document
    MAX_QUERY_LENGTH: int = 5000  # characters
    CHUNK_SIZE: int = 500  # words per chunk
    CHUNK_OVERLAP: int = 50  # word overlap between chunks
    LLM_MODEL: str = "gemini-2.5-flash"
    RETRIEVAL_TOP_K: int = 5  # top K chunks to retrieve
    
    @property
    def cors_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

settings = Settings()
