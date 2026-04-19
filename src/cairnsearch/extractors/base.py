"""Base extractor interface and result type."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class ExtractionResult:
    """Result from text extraction."""
    success: bool
    text: Optional[str] = None
    metadata: dict = field(default_factory=dict)
    error: Optional[str] = None
    extraction_method: str = "direct"

    @property
    def page_count(self) -> Optional[int]:
        return self.metadata.get("page_count")

    @property
    def title(self) -> Optional[str]:
        return self.metadata.get("title")

    @property
    def author(self) -> Optional[str]:
        return self.metadata.get("author")

    @property
    def created_date(self) -> Optional[str]:
        return self.metadata.get("created_date")

    @property
    def modified_date(self) -> Optional[str]:
        return self.metadata.get("modified_date")


class BaseExtractor(ABC):
    """Abstract base class for text extractors."""

    @property
    @abstractmethod
    def supported_extensions(self) -> list[str]:
        """Return list of supported file extensions (lowercase, with dot)."""
        pass

    @abstractmethod
    def extract(self, file_path: Path) -> ExtractionResult:
        """Extract text and metadata from file."""
        pass

    def can_handle(self, file_path: Path) -> bool:
        """Check if this extractor can handle the file."""
        return file_path.suffix.lower() in self.supported_extensions
