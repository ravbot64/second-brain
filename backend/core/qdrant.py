from qdrant_client import QdrantClient
from .config import settings

def get_qdrant_client() -> QdrantClient:
    """
    Initialize Qdrant client for either local or cloud.
    
    Local: Uses path (e.g., ./qdrant_data)
    Cloud: Uses URL + API key (e.g., https://xxx.qdrant.io:6333)
    """
    if settings.QDRANT_URL and settings.QDRANT_URL.startswith("http"):
        # Cloud Qdrant: use URL and API key
        return QdrantClient(
            url=settings.QDRANT_URL,
            api_key=settings.QDRANT_API_KEY,
            timeout=30.0,
        )
    else:
        # Local Qdrant: use file path
        return QdrantClient(path=settings.QDRANT_PATH)

client = get_qdrant_client()
