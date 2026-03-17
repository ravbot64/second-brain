from typing import List
import hashlib
import math

class EmbeddingService:
    def __init__(self):
        self._client = None
        self._model = None
        self._dim = 384

    def _load(self):
        if self._client is None:
            from google import genai
            from google.genai import types
            from .config import settings
            self._client = genai.Client(
                api_key=settings.GOOGLE_API_KEY,
                http_options=types.HttpOptions(api_version='v1')
            )

    def _local_fallback_embedding(self, text: str) -> List[float]:
        # Deterministic hash-based embedding used only when remote embedding API is unavailable.
        vec = [0.0] * self._dim
        for token in text.lower().split():
            if not token:
                continue
            h = hashlib.sha256(token.encode("utf-8")).hexdigest()
            idx = int(h[:8], 16) % self._dim
            sign = 1.0 if (int(h[8:10], 16) % 2 == 0) else -1.0
            vec[idx] += sign

        norm = math.sqrt(sum(v * v for v in vec))
        if norm == 0.0:
            return vec
        return [v / norm for v in vec]

    def _remote_embedding(self, text: str) -> List[float]:
        self._load()
        from google.genai import types

        # Try known model names across API versions/projects.
        candidate_models = [
            "gemini-embedding-001",
            "text-embedding-004",
            "models/gemini-embedding-001",
            "models/text-embedding-004",
        ]

        # Reuse the first model that succeeds to avoid repeated retries.
        if self._model:
            candidate_models = [self._model] + [m for m in candidate_models if m != self._model]

        last_error = None
        for model_name in candidate_models:
            try:
                result = self._client.models.embed_content(
                    model=model_name,
                    contents=text,
                    config=types.EmbedContentConfig(output_dimensionality=self._dim),
                )
                self._model = model_name
                return list(result.embeddings[0].values)
            except Exception as e:
                last_error = e

        raise RuntimeError(f"Remote embedding failed for all candidate models: {last_error}")

    def get_embedding(self, text: str) -> List[float]:
        try:
            return self._remote_embedding(text)
        except Exception as e:
            print(f"Embedding API unavailable, using local fallback: {e}")
            return self._local_fallback_embedding(text)

    def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        return [self.get_embedding(t) for t in texts]

embedder = EmbeddingService()
