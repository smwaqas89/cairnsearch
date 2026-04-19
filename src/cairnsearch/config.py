"""Configuration management for cairnsearch."""
from pathlib import Path
from typing import Any
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings

try:
    import tomli
except ImportError:
    import tomllib as tomli


class GeneralConfig(BaseModel):
    data_dir: str = "~/.local/share/cairnsearch"
    log_level: str = "INFO"


class WatcherConfig(BaseModel):
    debounce_ms: int = 500
    folders: list[str] = Field(default_factory=lambda: ["~/Documents"])
    ignore_patterns: list[str] = Field(default_factory=lambda: [
        "*.tmp", "~$*", ".git", "__pycache__", "node_modules", ".DS_Store", "Thumbs.db"
    ])


class IndexerConfig(BaseModel):
    workers: int = 3
    hash_algorithm: str = "sha256"
    max_file_size_mb: int = 500  # Increased to handle larger files


class OCRConfig(BaseModel):
    enabled: bool = True
    language: str = "eng"
    scanned_threshold_chars_per_page: int = 50
    cache_enabled: bool = True


class SearchConfig(BaseModel):
    default_page_size: int = 20
    max_page_size: int = 100
    snippet_length: int = 150
    highlight_tag: str = "mark"


class APIConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8080
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])


class RAGConfigSection(BaseModel):
    """RAG configuration section."""
    enabled: bool = True
    chunk_size: int = 500
    chunk_overlap: int = 50
    embedding_provider: str = "ollama"  # Use Ollama by default
    embedding_model: str = "nomic-embed-text"  # Ollama embedding model
    embedding_dimension: int = 768  # nomic-embed-text dimension
    top_k: int = 5
    # Reranking
    reranker_enabled: bool = True
    reranker_model: str = "ollama"  # Use Ollama for reranking
    rerank_top_k: int = 20  # Initial retrieval count before reranking
    # Hybrid search
    hybrid_search: bool = True
    bm25_weight: float = 0.3
    vector_weight: float = 0.7
    # LLM
    llm_provider: str = "ollama"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b"
    anthropic_model: str = "claude-sonnet-4-20250514"
    openai_model: str = "gpt-4o-mini"
    max_context_tokens: int = 4000
    temperature: float = 0.1


class Config(BaseSettings):
    general: GeneralConfig = Field(default_factory=GeneralConfig)
    watcher: WatcherConfig = Field(default_factory=WatcherConfig)
    indexer: IndexerConfig = Field(default_factory=IndexerConfig)
    ocr: OCRConfig = Field(default_factory=OCRConfig)
    search: SearchConfig = Field(default_factory=SearchConfig)
    api: APIConfig = Field(default_factory=APIConfig)
    rag: RAGConfigSection = Field(default_factory=RAGConfigSection)

    @classmethod
    def load(cls, config_path: Path | None = None) -> "Config":
        """Load config from TOML file or use defaults."""
        if config_path is None:
            config_path = Path.home() / ".config" / "cairnsearch" / "config.toml"
        
        if config_path.exists():
            with open(config_path, "rb") as f:
                data = tomli.load(f)
            return cls(**data)
        return cls()

    def get_data_dir(self) -> Path:
        """Get expanded data directory path."""
        return Path(self.general.data_dir).expanduser()

    def get_db_path(self) -> Path:
        """Get database file path."""
        return self.get_data_dir() / "cairnsearch.db"

    def get_watch_folders(self) -> list[Path]:
        """Get expanded watch folder paths."""
        return [Path(f).expanduser() for f in self.watcher.folders]


# Global config instance
_config: Config | None = None


def get_config() -> Config:
    """Get the global config instance."""
    global _config
    if _config is None:
        _config = Config.load()
    return _config


def set_config(config: Config) -> None:
    """Set the global config instance."""
    global _config
    _config = config
