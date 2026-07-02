from typing import List
import hashlib
import math
import time


class EmbeddingService:
    """Produces 384-dim embeddings via Google Gemini.

    Consistency is critical: every vector stored in Qdrant and every query vector
    must come from the *same* embedding space. Silently falling back to a
    hash-based vector (a different space) corrupts retrieval, so when an API key
    is configured we only ever use the real API and raise on failure instead of
    poisoning the index. The local hash embedding is used only for fully offline
    development (no API key configured).
    """

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
                http_options=types.HttpOptions(api_version="v1"),
            )

    def _local_fallback_embedding(self, text: str) -> List[float]:
        # Deterministic hash-based embedding. OFFLINE-DEV ONLY (no API key).
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

    def _remote_embedding(self, text: str, retries: int = 3) -> List[float]:
        self._load()
        from google.genai import types

        # Try known model names across API versions/projects.
        candidate_models = [
            "gemini-embedding-001",
            "text-embedding-004",
            "models/gemini-embedding-001",
            "models/text-embedding-004",
        ]
        # Pin the first model that succeeds so every embedding stays in one space.
        if self._model:
            candidate_models = [self._model] + [m for m in candidate_models if m != self._model]

        last_error = None
        for attempt in range(retries):
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
            # Brief backoff before retrying the whole candidate list.
            if attempt < retries - 1:
                time.sleep(0.5 * (attempt + 1))

        raise RuntimeError(f"Remote embedding failed for all candidate models: {last_error}")

    def get_embedding(self, text: str) -> List[float]:
        from .config import settings

        if not settings.GOOGLE_API_KEY:
            # No API key: offline dev mode only. This vector space is NOT
            # compatible with real Gemini vectors — never mix the two.
            return self._local_fallback_embedding(text)

        # With a key configured, always use the real API and fail loudly rather
        # than silently storing an incompatible hash vector.
        return self._remote_embedding(text)

    def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        return [self.get_embedding(t) for t in texts]


embedder = EmbeddingService()
