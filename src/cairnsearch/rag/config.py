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

    # Privacy: when True (the default), cairnsearch makes NO external network
    # calls. Only local providers (Ollama, local sentence-transformers) are
    # permitted, and any attempt to use a cloud provider (OpenAI, Anthropic)
    # is refused before a request is sent. This is the behaviour described in
    # the published paper: "nothing leaves the machine". Set to False only if
    # you explicitly want to opt in to cloud providers.
    strict_local: bool = True
    
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
    
    # Reranking settings - disabled by default for speed.
    # The default reranker is LLM-based (listwise scoring via the local Ollama
    # model named below). See rag/reranker.py for details and how to plug in a
    # true cross-encoder model instead.
    reranker_enabled: bool = False  # Disable for faster responses
    reranker_model: str = "ollama"  # "ollama" = listwise LLM reranker (local)
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


# --- Privacy / locality helpers -------------------------------------------

# Providers that run entirely on the local machine (no external network egress)
LOCAL_LLM_PROVIDERS = {LLMProvider.NONE, LLMProvider.OLLAMA}
LOCAL_EMBEDDING_PROVIDERS = {EmbeddingProvider.LOCAL, EmbeddingProvider.OLLAMA}


class CloudProviderBlocked(RuntimeError):
    """Raised when a cloud provider is requested while strict_local is on."""


def is_local_llm_provider(provider: "LLMProvider") -> bool:
    """Return True if the LLM provider makes no external network calls."""
    return provider in LOCAL_LLM_PROVIDERS


def is_local_embedding_provider(provider: "EmbeddingProvider") -> bool:
    """Return True if the embedding provider makes no external network calls."""
    return provider in LOCAL_EMBEDDING_PROVIDERS


def ensure_local_or_allowed(provider, kind: str, config: Optional[RAGConfig] = None) -> None:
    """
    Guard used before any provider that could make an external network call.

    When ``strict_local`` is enabled (the default), this refuses cloud
    providers up front so that no request is ever sent off the machine.
    Pass ``kind="llm"`` or ``kind="embedding"``.
    """
    config = config or get_rag_config()
    if not config.strict_local:
        return  # user has explicitly opted in to cloud providers

    if kind == "llm":
        local = is_local_llm_provider(provider)
    elif kind == "embedding":
        local = is_local_embedding_provider(provider)
    else:
        local = False

    if not local:
        raise CloudProviderBlocked(
            f"Cloud {kind} provider '{getattr(provider, 'value', provider)}' is "
            f"blocked because strict_local mode is enabled (the default). "
            f"cairnsearch makes no external network calls by default. To use a "
            f"cloud provider, explicitly set strict_local = false in your config."
        )
