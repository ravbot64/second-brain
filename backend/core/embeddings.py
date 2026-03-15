from typing import List

class EmbeddingService:
    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2"):
        self._model_name = model_name
        self._model = None

    def _load(self):
        if self._model is None:
            from fastembed import TextEmbedding
            self._model = TextEmbedding(self._model_name)

    def get_embedding(self, text: str) -> List[float]:
        self._load()
        return list(list(self._model.embed([text]))[0])

    def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        self._load()
        return [list(emb) for emb in self._model.embed(texts)]

embedder = EmbeddingService()
