"""RAG configuration."""
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class LLMProvider(str, Enum):
    """LLM provider options."""
    NONE = "none"
    OLLAMA = "ollama"
    ANTHROPIC = "anthropic"
    OPENAI = "openai"


class EmbeddingProvider(str, Enum):
    """Embedding provider options."""
    LOCAL = "local"  # sentence-transformers
    OLLAMA = "ollama"
    OPENAI = "openai"


@dataclass
class RAGConfig:
    """RAG system configuration."""
    
    # Feature toggles
    enabled: bool = True
    
    # Chunking settings
    chunk_size: int = 500  # tokens
    chunk_overlap: int = 50  # tokens
    
    # Embedding settings - Ollama by default
    embedding_provider: EmbeddingProvider = EmbeddingProvider.OLLAMA
    embedding_model: str = "nomic-embed-text"  # Ollama embedding model
    embedding_dimension: int = 768  # nomic-embed-text dimension
    
    # Vector store settings
    vector_store_path: str = "~/.local/share/cairnsearch/vectors"
    collection_name: str = "documents"
    
    # Retrieval settings
    top_k: int = 5  # Number of chunks to retrieve
    hybrid_search: bool = True  # Combine BM25 + vector search
    bm25_weight: float = 0.3  # Weight for BM25 in hybrid search
    vector_weight: float = 0.7  # Weight for vector search
    
    # Reranking settings - disabled by default for speed
    reranker_enabled: bool = False  # Disable for faster responses
    reranker_model: str = "ollama"
    rerank_top_k: int = 10  # Retrieve this many before reranking
    
    # LLM settings
    llm_provider: LLMProvider = LLMProvider.OLLAMA
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b"
    anthropic_model: str = "claude-sonnet-4-20250514"
    openai_model: str = "gpt-4o-mini"
    openai_embedding_model: str = "text-embedding-3-small"  # OpenAI embedding model
    
    # Generation settings
    max_context_tokens: int = 4000
    temperature: float = 0.1
    
    # API keys (prefer environment variables)
    anthropic_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None


# Global RAG config
_rag_config: Optional[RAGConfig] = None


def get_rag_config() -> RAGConfig:
    """Get global RAG config."""
    global _rag_config
    if _rag_config is None:
        _rag_config = RAGConfig()
    return _rag_config


def set_rag_config(config: RAGConfig) -> None:
    """Set global RAG config."""
    global _rag_config
    _rag_config = config
