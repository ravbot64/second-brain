from typing import List
import hashlib
import math
import time


# Gemini embed_content accepts multiple inputs per call. Batching avoids free-tier
# rate limits (one call per chunk was the cause of reindex failures) and is faster.
EMBED_BATCH_SIZE = 100


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
            from .config import settings
            # Use the SDK's default API version (broad model support) rather than
            # pinning v1, where some embedding models return 404 NOT_FOUND.
            self._client = genai.Client(api_key=settings.GOOGLE_API_KEY)

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

    def _candidate_models(self) -> List[str]:
        from .config import settings
        candidates: List[str] = []
        for name in (settings.EMBEDDING_MODEL, "gemini-embedding-001", "models/gemini-embedding-001"):
            if name and name not in candidates:
                candidates.append(name)
        # Try the last known-good model first so all vectors stay in one space.
        if self._model:
            candidates = [self._model] + [m for m in candidates if m != self._model]
        return candidates

    def _embed_batch_remote(self, texts: List[str], max_attempts: int = 4) -> List[List[float]]:
        self._load()
        from google.genai import types

        errors = {}
        for attempt in range(max_attempts):
            for model_name in self._candidate_models():
                try:
                    result = self._client.models.embed_content(
                        model=model_name,
                        contents=texts,
                        config=types.EmbedContentConfig(output_dimensionality=self._dim),
                    )
                    self._model = model_name
                    return [list(e.values) for e in result.embeddings]
                except Exception as e:
                    errors[model_name] = str(e)
            # Back off before retrying — handles transient errors and rate limits.
            if attempt < max_attempts - 1:
                time.sleep(min(2 ** attempt, 15))

        raise RuntimeError(f"Remote embedding failed for all candidate models: {errors}")

    def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        from .config import settings

        if not texts:
            return []

        if not settings.GOOGLE_API_KEY:
            # No API key: offline dev mode only. This vector space is NOT
            # compatible with real Gemini vectors — never mix the two.
            return [self._local_fallback_embedding(t) for t in texts]

        out: List[List[float]] = []
        for i in range(0, len(texts), EMBED_BATCH_SIZE):
            out.extend(self._embed_batch_remote(texts[i:i + EMBED_BATCH_SIZE]))
        return out

    def get_embedding(self, text: str) -> List[float]:
        from .config import settings

        if not settings.GOOGLE_API_KEY:
            return self._local_fallback_embedding(text)

        # With a key configured, always use the real API and fail loudly rather
        # than silently storing an incompatible hash vector.
        return self._embed_batch_remote([text])[0]


embedder = EmbeddingService()
