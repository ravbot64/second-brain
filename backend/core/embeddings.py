from typing import List

class EmbeddingService:
    def __init__(self):
        self._client = None

    def _load(self):
        if self._client is None:
            from google import genai
            from google.genai import types
            from .config import settings
            self._client = genai.Client(
                api_key=settings.GOOGLE_API_KEY,
                http_options=types.HttpOptions(api_version='v1')
            )

    def get_embedding(self, text: str) -> List[float]:
        self._load()
        from google.genai import types
        result = self._client.models.embed_content(
            model="text-embedding-004",
            contents=text,
            config=types.EmbedContentConfig(output_dimensionality=384)
        )
        return list(result.embeddings[0].values)

    def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        return [self.get_embedding(t) for t in texts]

embedder = EmbeddingService()
