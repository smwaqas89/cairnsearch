"""Reranking for improved retrieval accuracy using Ollama."""
import logging
from abc import ABC, abstractmethod
from typing import Optional
from dataclasses import dataclass

from .config import get_rag_config


logger = logging.getLogger(__name__)


@dataclass
class RerankResult:
    """Result from reranking."""
    index: int
    score: float
    text: str


class BaseReranker(ABC):
    """Abstract base class for rerankers."""
    
    @abstractmethod
    def rerank(
        self, 
        query: str, 
        documents: list[str], 
        top_k: int = 5
    ) -> list[RerankResult]:
        """Rerank documents by relevance to query."""
        pass
    
    @property
    @abstractmethod
    def is_available(self) -> bool:
        """Check if reranker is available."""
        pass


class OllamaReranker(BaseReranker):
    """Use Ollama LLM for reranking with batch scoring."""
    
    def __init__(self, model: Optional[str] = None, base_url: Optional[str] = None):
        config = get_rag_config()
        self.model = model or config.ollama_model
        self.base_url = base_url or config.ollama_base_url
        self._available = None
    
    @property
    def is_available(self) -> bool:
        if self._available is None:
            try:
                import httpx
                response = httpx.get(f"{self.base_url}/api/tags", timeout=5.0)
                self._available = response.status_code == 200
            except:
                self._available = False
        return self._available
    
    def rerank(
        self, 
        query: str, 
        documents: list[str], 
        top_k: int = 5
    ) -> list[RerankResult]:
        """Rerank using Ollama to score relevance in batches."""
        if not self.is_available or not documents:
            return [
                RerankResult(index=i, score=1.0 - (i * 0.1), text=doc)
                for i, doc in enumerate(documents[:top_k])
            ]
        
        import httpx
        
        # Batch score documents (more efficient)
        scored = self._batch_score(query, documents)
        
        # Sort by score
        scored.sort(key=lambda x: x[1], reverse=True)
        
        return [
            RerankResult(index=idx, score=score, text=text)
            for idx, score, text in scored[:top_k]
        ]
    
    def _batch_score(self, query: str, documents: list[str]) -> list[tuple[int, float, str]]:
        """Score all documents in a single LLM call for efficiency."""
        import httpx
        
        # Truncate documents for scoring
        doc_summaries = []
        for i, doc in enumerate(documents):
            truncated = doc[:500] if len(doc) > 500 else doc
            doc_summaries.append(f"[{i}] {truncated}")
        
        docs_text = "\n\n".join(doc_summaries)
        
        prompt = f"""Rate the relevance of each document to the query. 
Return ONLY a JSON array of scores from 0-10, one per document, in order.
Example response: [8, 3, 9, 5, 2]

Query: {query}

Documents:
{docs_text}

Relevance scores (JSON array only):"""
        
        try:
            response = httpx.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0}
                },
                timeout=60.0
            )
            
            if response.status_code == 200:
                result = response.json().get("response", "").strip()
                scores = self._parse_scores(result, len(documents))
                return [(i, scores[i] / 10.0, documents[i]) for i in range(len(documents))]
        except Exception as e:
            logger.warning(f"Batch reranking failed: {e}")
        
        # Fallback: return original order with decreasing scores
        return [(i, 1.0 - (i * 0.05), doc) for i, doc in enumerate(documents)]
    
    def _parse_scores(self, result: str, expected_count: int) -> list[float]:
        """Parse JSON array of scores from LLM response."""
        import json
        import re
        
        # Try to extract JSON array
        match = re.search(r'\[[\d\s,\.]+\]', result)
        if match:
            try:
                scores = json.loads(match.group())
                if len(scores) >= expected_count:
                    return [float(s) for s in scores[:expected_count]]
            except:
                pass
        
        # Fallback: extract individual numbers
        numbers = re.findall(r'\d+(?:\.\d+)?', result)
        if len(numbers) >= expected_count:
            return [float(n) for n in numbers[:expected_count]]
        
        # Default scores
        return [5.0] * expected_count


class NoOpReranker(BaseReranker):
    """Pass-through reranker that doesn't change order."""
    
    @property
    def is_available(self) -> bool:
        return True
    
    def rerank(
        self, 
        query: str, 
        documents: list[str], 
        top_k: int = 5
    ) -> list[RerankResult]:
        """Return documents in original order."""
        return [
            RerankResult(index=i, score=1.0 - (i * 0.05), text=doc)
            for i, doc in enumerate(documents[:top_k])
        ]


def get_reranker() -> BaseReranker:
    """Get the best available reranker."""
    config = get_rag_config()
    
    if not config.reranker_enabled:
        return NoOpReranker()
    
    # Use Ollama reranker
    ollama = OllamaReranker()
    if ollama.is_available:
        logger.info("Using Ollama reranker")
        return ollama
    
    # No reranking available
    logger.warning("Ollama not available for reranking, using pass-through")
    return NoOpReranker()
