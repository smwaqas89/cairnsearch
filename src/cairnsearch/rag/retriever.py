"""Hybrid retriever combining BM25 and vector search with reranking."""
from dataclasses import dataclass
from typing import Optional
import logging

from cairnsearch.db import Database
from cairnsearch.search import SearchEngine
from .config import get_rag_config
from .embeddings import get_embedder
from .vector_store import VectorStore


logger = logging.getLogger(__name__)


@dataclass
class RetrievalResult:
    """Combined retrieval result."""
    chunk_id: str
    doc_id: int
    file_path: str
    filename: str
    content: str
    score: float
    source: str  # "vector", "bm25", or "hybrid"
    metadata: dict


class HybridRetriever:
    """Hybrid retriever combining BM25 keyword search with vector similarity and reranking."""
    
    def __init__(
        self,
        db: Optional[Database] = None,
        vector_store: Optional[VectorStore] = None,
    ):
        config = get_rag_config()
        self.config = config
        self.db = db or Database()
        self.vector_store = vector_store or VectorStore()
        self.embedder = get_embedder()
        self.search_engine = SearchEngine(self.db)
        self._reranker = None
    
    @property
    def reranker(self):
        """Lazy load reranker."""
        if self._reranker is None:
            from .reranker import get_reranker
            self._reranker = get_reranker()
        return self._reranker
    
    def retrieve(
        self,
        query: str,
        top_k: Optional[int] = None,
        file_path_filter: Optional[str] = None,
    ) -> list[RetrievalResult]:
        """Retrieve relevant chunks using hybrid search with optional reranking."""
        config = self.config
        top_k = top_k or config.top_k
        
        # Get more candidates if we're going to rerank
        initial_k = config.rerank_top_k if config.reranker_enabled else top_k
        
        if not config.hybrid_search:
            candidates = self._vector_search(query, initial_k, file_path_filter)
        else:
            vector_results = self._vector_search(query, initial_k, file_path_filter)
            bm25_results = self._bm25_search(query, initial_k)
            
            candidates = self._combine_results(
                vector_results, bm25_results,
                config.vector_weight, config.bm25_weight,
            )
        
        # Apply reranking if enabled
        if config.reranker_enabled and len(candidates) > top_k:
            candidates = self._rerank(query, candidates, top_k)
        
        return candidates[:top_k]
    
    def _rerank(
        self,
        query: str,
        candidates: list[RetrievalResult],
        top_k: int,
    ) -> list[RetrievalResult]:
        """Rerank candidates using cross-encoder."""
        if not candidates:
            return candidates
        
        try:
            # Extract texts for reranking
            texts = [c.content for c in candidates]
            
            # Rerank
            reranked = self.reranker.rerank(query, texts, top_k=top_k)
            
            # Map back to results
            results = []
            for r in reranked:
                original = candidates[r.index]
                results.append(RetrievalResult(
                    chunk_id=original.chunk_id,
                    doc_id=original.doc_id,
                    file_path=original.file_path,
                    filename=original.filename,
                    content=original.content,
                    score=r.score,
                    source="reranked",
                    metadata=original.metadata,
                ))
            
            logger.debug(f"Reranked {len(candidates)} candidates to {len(results)}")
            return results
        except Exception as e:
            logger.warning(f"Reranking failed: {e}, using original order")
            return candidates[:top_k]
    
    def _vector_search(
        self,
        query: str,
        top_k: int,
        file_path_filter: Optional[str] = None,
    ) -> list[RetrievalResult]:
        """Perform vector similarity search."""
        query_embedding = self.embedder.embed(query)
        results = self.vector_store.search(query_embedding, top_k=top_k, file_path_filter=file_path_filter)
        
        return [
            RetrievalResult(
                chunk_id=r.chunk_id, doc_id=r.doc_id, file_path=r.file_path,
                filename=r.filename, content=r.content, score=r.score,
                source="vector", metadata=r.metadata,
            )
            for r in results
        ]
    
    def _bm25_search(self, query: str, top_k: int) -> list[RetrievalResult]:
        """Perform BM25 keyword search."""
        search_result = self.search_engine.search(query, page=1, page_size=top_k)
        
        results = []
        for r in search_result.results:
            results.append(RetrievalResult(
                chunk_id=f"doc_{r.id}",
                doc_id=r.id,
                file_path=r.file_path,
                filename=r.filename,
                content=r.snippets[0] if r.snippets else "",
                score=r.score / 10.0,
                source="bm25",
                metadata={},
            ))
        
        return results
    
    def _combine_results(
        self,
        vector_results: list[RetrievalResult],
        bm25_results: list[RetrievalResult],
        vector_weight: float,
        bm25_weight: float,
    ) -> list[RetrievalResult]:
        """Combine and re-rank results from both sources."""
        combined: dict[str, RetrievalResult] = {}
        
        max_vector = max((r.score for r in vector_results), default=1.0)
        for r in vector_results:
            normalized_score = (r.score / max_vector) * vector_weight if max_vector > 0 else 0
            combined[r.chunk_id] = RetrievalResult(
                chunk_id=r.chunk_id, doc_id=r.doc_id, file_path=r.file_path,
                filename=r.filename, content=r.content, score=normalized_score,
                source="hybrid", metadata=r.metadata,
            )
        
        max_bm25 = max((r.score for r in bm25_results), default=1.0)
        for r in bm25_results:
            normalized_score = (r.score / max_bm25) * bm25_weight if max_bm25 > 0 else 0
            if r.chunk_id in combined:
                combined[r.chunk_id].score += normalized_score
            else:
                combined[r.chunk_id] = RetrievalResult(
                    chunk_id=r.chunk_id, doc_id=r.doc_id, file_path=r.file_path,
                    filename=r.filename, content=r.content, score=normalized_score,
                    source="hybrid", metadata=r.metadata,
                )
        
        results = list(combined.values())
        results.sort(key=lambda x: x.score, reverse=True)
        return results
