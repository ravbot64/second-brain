from core.qdrant import client
from core.embeddings import embedder
from core.config import settings
from typing import List, Dict, Any, Optional, Set
from qdrant_client import models as qmodels

class Retriever:
    def __init__(self, collection_name: str = "second_brain_chunks"):
        self.collection_name = collection_name
        
    def search(
        self,
        query: str,
        top_k: int = 0,
        user_id: Optional[str] = None,
        allowed_document_ids: Optional[Set[str]] = None,
    ) -> List[Dict[str, Any]]:
        if top_k <= 0:
            top_k = settings.RETRIEVAL_TOP_K
        query_vector = embedder.get_embedding(query)

        if allowed_document_ids is not None:
            if not allowed_document_ids:
                return []

            search_result = client.query_points(
                collection_name=self.collection_name,
                query=query_vector,
                limit=top_k,
                query_filter=qmodels.Filter(
                    must=[
                        qmodels.FieldCondition(
                            key="document_id",
                            match=qmodels.MatchAny(any=list(allowed_document_ids)),
                        )
                    ]
                ),
            )
        elif user_id:
            search_result = client.query_points(
                collection_name=self.collection_name,
                query=query_vector,
                limit=top_k,
                query_filter=qmodels.Filter(
                    must=[
                        qmodels.FieldCondition(
                            key="user_id",
                            match=qmodels.MatchValue(value=user_id),
                        )
                    ]
                ),
            )
        else:
            search_result = client.query_points(
                collection_name=self.collection_name,
                query=query_vector,
                limit=top_k,
            )
        
        results = []
        for scored_point in search_result.points:
            document_id = scored_point.payload.get("document_id", "")
            results.append({
                "score": scored_point.score,
                "content": scored_point.payload.get("content", ""),
                "source": scored_point.payload.get("source", "unknown"),
                "document_id": document_id,
            })

            if len(results) >= top_k:
                break
            
        return results

retriever = Retriever()
