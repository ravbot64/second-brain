from sentence_transformers import SentenceTransformer
from typing import List

class EmbeddingService:
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self._model_name = model_name
        self._model = None

    def _load(self):
        if self._model is None:
            self._model = SentenceTransformer(self._model_name)

    def get_embedding(self, text: str) -> List[float]:
        self._load()
        return self._model.encode(text).tolist()

    def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        self._load()
        embeddings = self._model.encode(texts)
        return [emb.tolist() for emb in embeddings]

embedder = EmbeddingService()
