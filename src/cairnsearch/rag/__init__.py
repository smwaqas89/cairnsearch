"""RAG (Retrieval-Augmented Generation) module."""
from .config import RAGConfig, get_rag_config, set_rag_config, LLMProvider, EmbeddingProvider
from .chunker import DocumentChunker, Chunk
from .embeddings import get_embedder, BaseEmbedder
from .vector_store import VectorStore, VectorSearchResult
from .retriever import HybridRetriever, RetrievalResult
from .reranker import get_reranker, BaseReranker, OllamaReranker
from .llm import get_llm, BaseLLM
from .engine import RAGEngine, RAGResponse, create_rag_engine

__all__ = [
    # Config
    "RAGConfig", "get_rag_config", "set_rag_config",
    "LLMProvider", "EmbeddingProvider",
    # Components
    "DocumentChunker", "Chunk",
    "get_embedder", "BaseEmbedder",
    "VectorStore", "VectorSearchResult",
    "HybridRetriever", "RetrievalResult",
    "get_reranker", "BaseReranker", "OllamaReranker",
    "get_llm", "BaseLLM",
    # Main engine
    "RAGEngine", "RAGResponse", "create_rag_engine",
]
