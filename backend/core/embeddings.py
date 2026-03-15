from sentence_transformers import SentenceTransformer
from typing import List

class EmbeddingService:
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        # This is a small, fast model generating 384-dimensional embeddings
        self.model = SentenceTransformer(model_name)
        
    def get_embedding(self, text: str) -> List[float]:
        return self.model.encode(text).tolist()
        
    def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        embeddings = self.model.encode(texts)
        return [emb.tolist() for emb in embeddings]
        
embedder = EmbeddingService()
