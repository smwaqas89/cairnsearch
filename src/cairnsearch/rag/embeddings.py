"""Embedding generation for RAG."""
import os
from abc import ABC, abstractmethod
from typing import Optional
import logging
import hashlib

from .config import get_rag_config, EmbeddingProvider


logger = logging.getLogger(__name__)


class BaseEmbedder(ABC):
    """Abstract base class for embedding providers."""
    
    @abstractmethod
    def embed(self, text: str) -> list[float]:
        """Generate embedding for single text."""
        pass
    
    @abstractmethod
    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts."""
        pass
    
    @property
    @abstractmethod
    def dimension(self) -> int:
        """Embedding dimension."""
        pass


class LocalEmbedder(BaseEmbedder):
    """Local embeddings using sentence-transformers."""
    
    def __init__(self, model_name: Optional[str] = None):
        config = get_rag_config()
        self.model_name = model_name or config.embedding_model
        self._model = None
        self._dimension = config.embedding_dimension
    
    @property
    def model(self):
        """Lazy load the model."""
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                logger.info(f"Loading embedding model: {self.model_name}")
                self._model = SentenceTransformer(self.model_name)
                self._dimension = self._model.get_sentence_embedding_dimension()
            except ImportError:
                raise ImportError(
                    "sentence-transformers not installed. "
                    "Run: pip install sentence-transformers"
                )
        return self._model
    
    def embed(self, text: str) -> list[float]:
        """Generate embedding for single text."""
        embedding = self.model.encode(text, convert_to_numpy=True)
        return embedding.tolist()
    
    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts."""
        embeddings = self.model.encode(texts, convert_to_numpy=True)
        return embeddings.tolist()
    
    @property
    def dimension(self) -> int:
        return self._dimension


class OllamaEmbedder(BaseEmbedder):
    """Embeddings using Ollama."""
    
    def __init__(
        self,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        config = get_rag_config()
        self.model = model or "nomic-embed-text"
        self.base_url = base_url or config.ollama_base_url
        self._dimension = 768  # nomic-embed-text dimension
    
    def embed(self, text: str) -> list[float]:
        """Generate embedding for single text."""
        import httpx
        
        logger.info(f"[EMBEDDING REQUEST] Provider: Ollama, Model: {self.model}")
        
        response = httpx.post(
            f"{self.base_url}/api/embeddings",
            json={"model": self.model, "prompt": text},
            timeout=60.0,
        )
        response.raise_for_status()
        result = response.json()["embedding"]
        logger.info(f"[EMBEDDING RESPONSE] Ollama returned {len(result)}-dim vector")
        return result
    
    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts."""
        logger.info(f"[EMBEDDING BATCH] Provider: Ollama, Model: {self.model}, Count: {len(texts)}")
        return [self.embed(text) for text in texts]
    
    @property
    def dimension(self) -> int:
        return self._dimension


class SimpleEmbedder(BaseEmbedder):
    """
    Simple hash-based embeddings for environments without ML libraries.
    Not as good as neural embeddings, but works offline with no dependencies.
    """
    
    def __init__(self, dimension: int = 384):
        self._dimension = dimension
    
    def embed(self, text: str) -> list[float]:
        """Generate simple hash-based embedding."""
        words = text.lower().split()
        embedding = [0.0] * self._dimension
        
        for i, word in enumerate(words):
            h = int(hashlib.md5(word.encode()).hexdigest(), 16)
            for j in range(3):
                pos = (h + j * 7919) % self._dimension
                val = ((h >> (j * 8)) & 0xFF) / 255.0 - 0.5
                embedding[pos] += val
        
        # Normalize
        norm = sum(x*x for x in embedding) ** 0.5
        if norm > 0:
            embedding = [x / norm for x in embedding]
        
        return embedding
    
    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts."""
        return [self.embed(text) for text in texts]
    
    @property
    def dimension(self) -> int:
        return self._dimension


class OpenAIEmbedder(BaseEmbedder):
    """Embeddings using OpenAI API."""
    
    def __init__(
        self,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
    ):
        config = get_rag_config()
        self.model = model or config.openai_embedding_model
        self.api_key = api_key or config.openai_api_key or os.getenv("OPENAI_API_KEY")
        # text-embedding-3-small = 1536, text-embedding-3-large = 3072
        self._dimension = 1536 if "small" in self.model else 3072
    
    def embed(self, text: str) -> list[float]:
        """Generate embedding for single text."""
        import httpx
        
        if not self.api_key:
            raise ValueError("OpenAI API key required. Set OPENAI_API_KEY environment variable.")
        
        logger.info(f"[EMBEDDING REQUEST] Provider: OpenAI, Model: {self.model}")
        
        response = httpx.post(
            "https://api.openai.com/v1/embeddings",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "input": text,
            },
            timeout=60.0,
        )
        response.raise_for_status()
        result = response.json()["data"][0]["embedding"]
        logger.info(f"[EMBEDDING RESPONSE] OpenAI returned {len(result)}-dim vector")
        return result
    
    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts."""
        import httpx
        
        if not self.api_key:
            raise ValueError("OpenAI API key required. Set OPENAI_API_KEY environment variable.")
        
        logger.info(f"[EMBEDDING BATCH] Provider: OpenAI, Model: {self.model}, Count: {len(texts)}")
        
        # OpenAI supports batch embeddings natively
        response = httpx.post(
            "https://api.openai.com/v1/embeddings",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "input": texts,
            },
            timeout=120.0,
        )
        response.raise_for_status()
        data = response.json()["data"]
        # Sort by index to ensure correct order
        sorted_data = sorted(data, key=lambda x: x["index"])
        logger.info(f"[EMBEDDING RESPONSE] OpenAI returned {len(sorted_data)} vectors")
        return [item["embedding"] for item in sorted_data]
    
    @property
    def dimension(self) -> int:
        return self._dimension


def get_embedder(provider: Optional[EmbeddingProvider] = None) -> BaseEmbedder:
    """Get embedder based on configuration."""
    config = get_rag_config()
    provider = provider or config.embedding_provider
    
    if provider == EmbeddingProvider.LOCAL:
        try:
            import sentence_transformers
            return LocalEmbedder()
        except ImportError:
            logger.warning("sentence-transformers not available, using simple embedder")
            return SimpleEmbedder(config.embedding_dimension)
    elif provider == EmbeddingProvider.OLLAMA:
        return OllamaEmbedder()
    elif provider == EmbeddingProvider.OPENAI:
        return OpenAIEmbedder()
    else:
        return SimpleEmbedder(config.embedding_dimension)
