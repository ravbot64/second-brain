from core.qdrant import client
from core.embeddings import embedder
from core.config import settings
from typing import List, Dict, Any

class Retriever:
    def __init__(self, collection_name: str = "second_brain_chunks"):
        self.collection_name = collection_name
        
    def search(self, query: str, top_k: int = 0) -> List[Dict[str, Any]]:
        if top_k <= 0:
            top_k = settings.RETRIEVAL_TOP_K
        query_vector = embedder.get_embedding(query)
        
        search_result = client.query_points(
            collection_name=self.collection_name,
            query=query_vector,
            limit=top_k
        )
        
        results = []
        for scored_point in search_result.points:
            results.append({
                "score": scored_point.score,
                "content": scored_point.payload.get("content", ""),
                "source": scored_point.payload.get("source", "unknown"),
                "document_id": scored_point.payload.get("document_id", "")
            })
            
        return results

retriever = Retriever()
